"""Đọc lại các ô có số khác giữa hai BCTC của cùng công ty để phân biệt đọc sai với số thật sự khác nhau.

Trong một BCTC, lệch cộng tổng chỉ có thể do đọc sai. Giữa hai BCTC (quý 2 với bán niên, quý này với quý trước), một
con số khác nhau có thể do đọc sai ở một bên hoặc do công ty đã sửa số (soát xét, kiểm toán, phân loại lại). Khi không
có phép cộng tổng nào làm chứng, hoặc hai số chỉ khác 1-2 chữ số (dạng đọc sai điển hình), ô được đánh dấu "cần xem
lại" (evidence.PeriodCheck.suspect_misread). Ở đây mỗi ô liên quan được đọc lại riêng ở ảnh nét hơn, trên cả hai BCTC:

  * đọc lại ra đúng như lần đầu ở mọi ô: hai lần đọc độc lập trùng nhau, nên chênh lệch là số thật (công ty đã sửa);
  * đọc lại ra số khác: lần đầu đọc sai; số mới được giữ nếu ràng buộc bắt buộc của BCTC đó không xấu đi.

Kết quả ghi vào record["cell_verifications"]; evidence.py dùng nó để xếp lại trạng thái ô.
"""

from __future__ import annotations

from datetime import datetime, timezone

import psycopg

from services.extraction import prompts
from services.extraction.evidence import cells_of, document_evidence
from services.extraction.numbers import parse_amount
from services.extraction.pipeline import (
    _finalize,
    _asked_column,
    _gate_tally,
    _label_on_page,
    _load_record,
    _reread_on_page,
    open_record_pdf,
    printed_code,
    track_usage,
)
from services.llm import VisionClient

Cell = tuple[str, str, str]          # (báo cáo, khóa ô, cột)


def cells_to_verify(conn: psycopg.Connection, document_ids: list[int]) -> dict[int, set[Cell]]:
    """Các ô thuộc những chỗ lệch "cần xem lại" của các tài liệu đã cho, gom theo tài liệu chứa ô (gồm cả BCTC đối
    chiếu). Bỏ qua ô đã được đọc lại."""
    out: dict[int, set[Cell]] = {}
    for doc_id in document_ids:
        ev = document_evidence(conn, doc_id)
        if ev is None:
            continue
        for pc in ev.period_checks:
            if pc.suspect_misread:
                for d, st, key, col in pc.cells:
                    out.setdefault(d, set()).add((st, key, col))
    for doc_id in list(out):
        done = {(v["statement"], v["key"], v["column_kind"]) for v in _load_record(conn, doc_id).get("cell_verifications", [])}
        out[doc_id] -= done
        if not out[doc_id]:
            del out[doc_id]
    return out


def _same_amount(a: str | None, b: str | None, sep: str) -> bool:
    x, y = parse_amount(a, sep), parse_amount(b, sep)
    return (x is None and y is None) or (x is not None and x == y)


def _row_index(c, record: dict, st: str, key: str, col: str) -> int | None:
    """Ô -> vị trí dòng trong bản chép: dòng thứ i của bảng đã chuẩn hóa là dòng thứ i của bản chép."""
    keys = c.item_keys.get(st, [])
    rows = record["raw"].get(st, {}).get("rows", [])
    i = keys.index(key) if key in keys else None
    if i is None or i >= len(rows) or col not in rows[i].get("values", {}) or not rows[i].get("page"):
        return None
    return i


def verify_document(conn: psycopg.Connection, document_id: int, cells: set[Cell], client: VisionClient) -> list[dict]:
    """Đọc lại từng ô ở ảnh nét hơn, mỗi trang một lần gọi. Trả về các dòng ghi nhận đã thêm vào bản ghi."""
    record = _load_record(conn, document_id)
    period = conn.execute("SELECT fiscal_period FROM documents WHERE id = %s", (document_id,)).fetchone()[0]
    c = cells_of(document_id, period, record)
    sep = record.get("thousands_sep") or "."

    by_page: dict[tuple[str, int], list[tuple[str, int, str, str]]] = {}
    for st, key, col in sorted(cells):
        i = _row_index(c, record, st, key, col)
        if i is not None:
            row = record["raw"][st]["rows"][i]
            by_page.setdefault((st, int(row["page"])), []).append((key, i, col, c.labels.get((st, key), "")))

    doc = open_record_pdf(conn, record)
    added: list[dict] = []
    with track_usage(record, client):
        for (st, page), items in by_page.items():
            ids = {f"o{n}": item for n, item in enumerate(items, 1)}
            rows = record["raw"][st]["rows"]
            # Mã số lấy theo khóa ô (đã qua bước sửa đảo cột), không theo bản chép gốc
            asked = lambda sub, st=st, rows=rows: prompts.verify_prompt(st, [
                (cid, printed_code(key),
                 _label_on_page(record, st, i, rows[i].get("label") or label), _asked_column(record, col))
                for cid, (key, i, col, label) in sub.items()])
            # Kết luận "công ty sửa số" dựa vào việc đọc lại ra như lần đầu, nên lần đọc lại phải khác hãng với lần đọc
            # đầu: cùng một mô hình thì lỗi có hệ thống (hai dòng tên gần giống bị đổi chỗ) lặp lại y hệt.
            answers = _reread_on_page(client, doc, record, st, page, ids, asked, "verify_cells", lambda item: item[1],
                                      provider=client.other_than(record.get("provider")))
            for cid, after in answers.items():
                key, i, col, label = ids[cid]
                before = rows[i]["values"][col]
                added.append({"statement": st, "key": key, "label": label, "column_kind": col,
                              "page": int(rows[i]["page"]), "row": i,
                              "before": before, "after": after, "same": _same_amount(before, after, sep),
                              "applied": False, "model": client.last_model or client.cfg.model,
                              "at": datetime.now(timezone.utc).isoformat()})
    record.setdefault("cell_verifications", []).extend(added)
    decide(conn, document_id, record)
    _finalize(conn, record)
    return added


def decide(conn: psycopg.Connection, document_id: int, record: dict) -> None:
    """Chọn số đọc lại nào được giữ. Ô không thuộc phép cộng tổng nào thì không có gì chặn một lần đọc lại nhầm dòng,
    nên chỉ giữ số đọc lại khi nó làm khớp phép đối chiếu với BCTC khác mà ô đó đang lệch, và ràng buộc bắt buộc của
    BCTC không xấu đi (lệch không tăng, số ràng buộc đạt không giảm). Gọi lại được: trả các số đã giữ trước đó về
    số cũ rồi chọn lại."""
    entries = record.get("cell_verifications", [])
    period = conn.execute("SELECT fiscal_period FROM documents WHERE id = %s", (document_id,)).fetchone()[0]
    current = cells_of(document_id, period, record)
    for e in entries:
        if e.get("row") is None:
            e["row"] = _row_index(current, record, e["statement"], e["key"], e["column_kind"])
        if e.get("applied") and e["row"] is not None:
            record["raw"][e["statement"]]["rows"][e["row"]]["values"][e["column_kind"]] = e["before"]
        e["applied"] = False
    c = cells_of(document_id, period, record)
    changes = []
    for e in entries:
        if e["same"] or e["after"] is None:
            continue
        if e.get("row") is None:
            e["row"] = _row_index(c, record, e["statement"], e["key"], e["column_kind"])
        if e["row"] is not None:
            changes.append(e)
    if not changes:
        return

    def value(e: dict, v: str) -> None:
        record["raw"][e["statement"]]["rows"][e["row"]]["values"][e["column_kind"]] = v

    gate_before = _gate_tally(record)
    for e in changes:
        value(e, e["after"])

    def load(doc_id: int) -> dict | None:
        if doc_id == document_id:
            return record
        try:
            return _load_record(conn, doc_id)
        except RuntimeError:
            return None

    ev = document_evidence(conn, document_id, load=load)
    resolved = {(st, key, col) for pc in (ev.period_checks if ev else []) if pc.passed
                for d, st, key, col in pc.cells if d == document_id}
    kept = [e for e in changes if (e["statement"], e["key"], e["column_kind"]) in resolved]
    for e in changes:
        if e not in kept:
            value(e, e["before"])
    gate_after = _gate_tally(record)
    if any(gate_after.get(st, (0, 0))[0] > f or gate_after.get(st, (0, 0))[1] < p for st, (f, p) in gate_before.items()):
        for e in kept:
            value(e, e["before"])
        kept = []
    for e in kept:
        e["applied"] = True


def apply_manual_fix(conn: psycopg.Connection, document_id: int, statement: str, row: int, column_kind: str,
                     value: str, by: str, note: str = "") -> dict:
    """Sửa tay một ô sau khi người xem đối chiếu ảnh gốc. Ghi lại ai sửa, lúc nào, số cũ và số mới
    (record["manual_fixes"]); đây cũng là dữ liệu vàng để đo độ chính xác.

    column_kind "code" sửa mã số của dòng thay vì một ô số (GVR bán niên 2026: mô hình đọc 420a/420b thành 421/421a);
    ghi riêng vào record["manual_code_fixes"] để không lẫn vào dữ liệu vàng của các ô số (eval/repair.py)."""
    record = _load_record(conn, document_id)
    r = record["raw"][statement]["rows"][row]
    if column_kind == "code":
        entry = {"statement": statement, "row": row, "label": r.get("label"), "column_kind": "code",
                 "before": r.get("code"), "after": value, "by": by, "note": note,
                 "at": datetime.now(timezone.utc).isoformat()}
        r["code"] = value
        record.setdefault("manual_code_fixes", []).append(entry)
        _finalize(conn, record)
        return entry
    entry = {"statement": statement, "row": row, "label": r.get("label"), "column_kind": column_kind,
             "before": r["values"].get(column_kind), "after": value, "by": by, "note": note,
             "at": datetime.now(timezone.utc).isoformat()}
    r["values"][column_kind] = value
    record.setdefault("manual_fixes", []).append(entry)
    _finalize(conn, record)
    return entry


def confirm_reading(conn: psycopg.Connection, document_id: int, statement: str, key: str, column: str, by: str,
                    note: str = "") -> dict:
    """Người duyệt đối chiếu ảnh gốc một ô "hai lần đọc khác nhau" và thấy lần đọc đầu đúng: ghi lại để ô thôi ở trạng
    thái cần xem lại, không sửa số nên không tính là ô sửa tay. Xác nhận gắn với số lúc đó; ô đổi số thì hết hiệu lực."""
    record = _load_record(conn, document_id)
    cells = cells_of(document_id, "", record)
    value = cells.row(statement, key).get(column)
    if value is None:
        raise ValueError(f"Không có ô {statement} {key} {column}")
    entry = {"statement": statement, "key": key, "column": column, "value": str(value), "by": by, "note": note,
             "at": datetime.now(timezone.utc).isoformat()}
    record.setdefault("image_confirmed", []).append(entry)
    _finalize(conn, record)
    return entry


def approve_document(conn: psycopg.Connection, document_id: int, user_id: int | None, by: str, note: str = "") -> str:
    """Người duyệt đã đối chiếu các chỗ lệch với ảnh gốc và cho xuất bản BCTC chưa đạt kiểm chứng tự động. `note` ghi
    vì sao chỗ lệch còn lại không phải đọc sai (ví dụ chính BCTC cộng lệch)."""
    record = _load_record(conn, document_id)
    record["approval"] = {"by": by, "at": datetime.now(timezone.utc).isoformat(), "note": note}
    record = _finalize(conn, record)
    conn.execute("UPDATE documents SET reviewed_by = %s, reviewed_at = now() WHERE id = %s", (user_id, document_id))
    return record["status"]
