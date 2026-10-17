"""Pipeline đọc và kiểm chứng một BCTC: chọn PDF -> định vị trang -> chép bảng -> chuẩn hóa -> kiểm tra ràng buộc.

Kết quả lưu vào:
  * Data/raw/extracted/<ticker>/<document_id>_<sha8>.json: toàn bộ đầu vào/đầu ra của mô hình, để xem lại và chấm điểm;
  * bảng line_items, validations; documents.template_ver và documents.status.

Phiên bản này chưa có bước đọc lại khi số liệu lệch (architecture.md mục 4.3); dòng lệch được ghi lại trong
validations để làm bước đó sau.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg

from services.extraction import prompts
from services.extraction.bank import canonicalize
from services.extraction.numbers import normalize_code, parse_amount
from services.extraction.sources import candidates, is_low_dpi, open_pdf, render_page, render_sharp, render_strips
from services.extraction.repair import agrees, cross_proposals, localize, proposal_dict
from services.extraction.rules import RULESETS
from services.extraction.validate import (
    ExtractedItem,
    ExtractedStatement,
    detect_template,
    expenses_printed_negative,
    normalize,
    summarize,
    validate,
)
from services.ingestion.registry import raw_data_dir
from services.llm import VisionClient, usage_delta

PIPELINE_VER = "0.1.0"
LOCATE_MAX_PAGES = 30
LOCATE_LONG_SIDE = 900
EXTRACT_LONG_SIDE = 2000


def _extract_image(doc, page: int, rotation: int) -> bytes:
    """Ảnh để chép cả trang: scan mờ (<= 100 dpi) dùng ảnh nét ngay từ lần đầu (sources.render_sharp), còn lại giữ ảnh
    cạnh dài 2000 như cũ (scan nét hơn không đọc tốt hơn khi dùng ảnh nét, đo 14/10/2026)."""
    if is_low_dpi(doc, [page]):
        return render_sharp(doc, page, rotation)
    return render_page(doc, page, EXTRACT_LONG_SIDE, rotation)


def _extract_detail(doc, pages) -> str | None:
    return "original" if is_low_dpi(doc, pages) else None


def _locate(client: VisionClient, doc, max_pages: int) -> list[dict]:
    """Phân loại trang theo từng đoạn `max_pages` trang; dừng khi đã thấy đủ BCĐKT, KQKD, LCTT tiếng Việt.

    Phần lớn BCTC có báo cáo trong 30 trang đầu; một số file ghép bản tiếng Anh lên trước (VHM quý 1/2026: 142 trang,
    bản tiếng Việt nằm sau trang 70) nên phải quét tiếp.
    """
    pages: list[dict] = []
    for start in range(1, doc.page_count + 1, max_pages):
        end = min(doc.page_count, start + max_pages - 1)
        images = [(f"Trang {p}", render_page(doc, p, LOCATE_LONG_SIDE)) for p in range(start, end + 1)]
        result = client.json_from_images(prompts.LOCATE_PROMPT, images, prompts.LOCATE_SCHEMA, "page_classification")
        pages += result["pages"]
        if {"BS", "IS", "CF"} <= set(_statement_pages(sorted(pages, key=lambda x: x["page"]))):
            break
    return sorted(pages, key=lambda x: x["page"])


def _statement_pages(pages: list[dict]) -> dict[str, list[int]]:
    """Gom các trang tiếng Việt theo loại báo cáo. Chỉ lấy khối trang liên tiếp đầu tiên của mỗi loại."""
    out: dict[str, list[int]] = {}
    for p in pages:
        st = prompts.STATEMENT_OF_KIND.get(p["kind"])
        if st is None or p["language"] != "vi":
            continue
        block = out.setdefault(st, [])
        if not block or p["page"] == block[-1] + 1:
            block.append(p["page"])
    return out


def _to_extracted(statement: str, raw: dict) -> ExtractedStatement:
    return ExtractedStatement(
        statement=statement,
        unit_raw=raw.get("unit_text"),
        items=[
            ExtractedItem(code=r.get("code"), label=r.get("label", ""), values_raw=r.get("values", {}),
                          note=r.get("note"), page=r.get("page"), stt=r.get("stt"))
            for r in raw.get("rows", [])
        ],
    )


def _json_default(o):
    if isinstance(o, Decimal):
        return str(o)
    raise TypeError(type(o))


def extract_document(conn: psycopg.Connection, document_id: int, client: VisionClient) -> dict:
    row = conn.execute(
        """
        SELECT d.ticker, d.title_raw, c.template, f.id, f.sha256, f.storage_key, d.doc_type
        FROM documents d JOIN companies c ON c.ticker = d.ticker
        JOIN document_files f ON f.document_id = d.id
        WHERE d.id = %s ORDER BY f.downloaded_at DESC LIMIT 1
        """,
        (document_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Tài liệu {document_id} chưa có file đã tải")
    ticker, title, company_template, file_id, sha256, storage_key, doc_type = row
    path = raw_data_dir() / storage_key

    usage_before = asdict(client.usage)   # client dùng chung cho nhiều tài liệu: chỉ tính phần của tài liệu này
    steps_before = client.steps_snapshot()
    switches_before = len(client.switches)
    record: dict = {
        "document_id": document_id, "ticker": ticker, "title": title, "doc_type": doc_type, "file_id": file_id,
        "sha256": sha256,
        "pipeline_ver": PIPELINE_VER, "model": client.cfg.model, "provider": client.cfg.provider,
        "started_at": datetime.now(timezone.utc).isoformat(), "candidates": [],
    }

    # 1. Chọn PDF và định vị trang. Nhiều ứng viên (ví dụ bản Việt và bản Anh cùng tên) thì chọn bản có nhiều
    #    trang báo cáo tiếng Việt nhất.
    best = None
    for cand in candidates(path):
        doc = open_pdf(cand)
        pages = _locate(client, doc, LOCATE_MAX_PAGES)
        st_pages = _statement_pages(pages)
        record["candidates"].append({"name": cand.name, "note": cand.note, "page_count": doc.page_count,
                                     "pages": pages, "statement_pages": st_pages,
                                     "rotations": {p["page"]: p.get("rotation", 0) for p in pages}})
        score = sum(len(v) for v in st_pages.values())
        if best is None or score > best[0]:
            best = (score, cand, doc, st_pages)
    _, cand, doc, st_pages = best
    record["chosen"] = cand.name

    # 2. Chép bảng từng báo cáo
    record["raw"] = {}
    for st in ("BS", "IS", "CF"):
        pages = st_pages.get(st)
        if not pages:
            continue
        images = [(f"Trang {p}", _extract_image(doc, p, _rotation(record, p))) for p in pages]
        raw = client.json_from_images(prompts.extract_prompt(st), images, prompts.extract_schema(st), f"statement_{st}",
                                      detail=_extract_detail(doc, pages))
        record["raw"][st] = raw
    record["company_template"] = company_template

    _escalate(record, client, doc, conn)
    record["usage"] = {k: v - usage_before[k] for k, v in asdict(client.usage).items()}
    record["usage_by_step"] = usage_delta(client.steps_snapshot(), steps_before)
    if client.switches[switches_before:]:
        record["llm_switches"] = client.switches[switches_before:]
    return _finalize(conn, record)


REREAD_ROUNDS = 1
# Các bước đọc lại và chép lại dùng ảnh nét (sources.render_sharp) kèm detail="original": trước đây vẽ trang cạnh dài
# 3000/2600 nhưng API thu về khoảng 1340x1908, đúng bằng ảnh lần chép đầu, nên đọc lại hay lặp đúng lỗi cũ.
ORIGINAL = "original"


def _escalate(record: dict, client: VisionClient, doc, conn: psycopg.Connection | None = None) -> None:
    """Thang leo thang khi ràng buộc bắt buộc bị lệch (architecture.md mục 4.3):
    1. đọc lại đúng các ô liên quan ở độ phân giải cao hơn;
    2. vẫn lệch thì chép lại cả báo cáo đó, mỗi trang một lần gọi (sửa lỗi bỏ sót dòng), giữ bản ít lệch hơn,
       rồi đọc lại ô thêm một lần.
    Trước đó: BCĐKT chưa kiểm được tổng tài sản = tổng nguồn vốn thì chép thêm trang kế tiếp (bước định vị trang có
    thể bỏ sót trang nguồn vốn). Bậc dùng mô hình mạnh hơn và duyệt tay chưa làm."""
    _extend_balance_sheet(record, client, doc)
    _repair_by_constraints(record, client, doc, conn)
    for _ in range(REREAD_ROUNDS):
        if not _reread_failed(record, client, doc):
            break
    if _reextract_failed_statements(record, client, doc):
        _reread_failed(record, client, doc)


def _repair_by_constraints(record: dict, client: VisionClient, doc, conn: psycopg.Connection | None = None) -> bool:
    """Định vị ô đọc sai bằng ràng buộc kế toán (repair.localize), đọc lại riêng các ô đó và chỉ nhận số mới khi lần
    đọc lại ra đúng số mà ràng buộc đòi hỏi: hai nguồn độc lập (phép cộng và ảnh) cùng chỉ một số.

    Nhóm phương án ngang nhau (một ràng buộc lệch, nhiều số hạng đều sửa được) thì đọc lại cả nhóm và nhận ô duy nhất
    khớp. Đọc lại vẫn ra số cũ ở mọi ô của nhóm thì ghi nhận nghi chính BCTC in lệch (record["filing_mismatch"])."""
    extracted, statements, sep, template, _ = _check(record)
    loc = localize(extracted, statements, sep, template)
    groups = [[p] for p in loc.proposals if not any(p is q.partner for q in loc.proposals)] + loc.ambiguous
    if conn is not None:
        # Thêm đề xuất từ đối chiếu với BCTC kỳ khác (ô không làm lệch phép cộng nào trong chính BCTC này)
        from services.extraction.evidence import document_evidence
        taken = {(q.statement, q.row, q.column_kind) for g in groups for q in g}
        load_self = lambda d: record if d == record["document_id"] else _try_load(conn, d)
        try:
            ev = document_evidence(conn, record["document_id"], load=load_self)
        except Exception:       # tài liệu mới chưa có trong CSDL đầy đủ: bỏ qua phần đối chiếu
            ev = None
        groups += cross_proposals(ev, extracted, statements, sep, template, taken)
    if not groups:
        return False
    cells = {}
    for group in groups:
        for p in group:
            for q in (p, p.partner):
                if q is not None:
                    cells[(q.statement, q.row, q.column_kind)] = q
    by_page: dict[tuple[str, int], list] = {}
    for (st, row, col), q in cells.items():
        page = record["raw"][st]["rows"][row].get("page")
        if page:
            by_page.setdefault((st, int(page)), []).append(q)
    reread: dict[tuple[str, int, str], str | None] = {}
    for (st, page), qs in by_page.items():
        ids = {f"o{n}": q for n, q in enumerate(qs, 1)}
        answers = _reread_on_page(client, doc, record, st, page, ids,
                                  lambda sub, st=st: prompts.verify_prompt(st, _asked_cells(record, sub)),
                                  "repair_cells", lambda q: q.row)
        for cid, value in answers.items():
            q = ids[cid]
            reread[(q.statement, q.row, q.column_kind)] = value

    mult = {name: st.multiplier for name, st in statements.items()}
    zoomed: dict[tuple[str, int, str], list[str | None]] = {}

    escalated: dict[tuple[str, int, str], str | None] = {}

    def confirmed(q) -> bool:
        key = (q.statement, q.row, q.column_kind)
        return ((key in reread and agrees(q, reread[key], sep, mult[q.statement]))
                or any(agrees(q, v, sep, mult[q.statement]) for v in zoomed.get(key, []))
                or (key in escalated and agrees(q, escalated[key], sep, mult[q.statement])))

    # Đọc lại cả trang mà vẫn ra đúng số cũ ở mọi ô của nhóm: có thể mô hình lặp cùng một lỗi vì chữ số quá nhỏ (VHM quý
    # 4/2025: 34.276.497 đọc hai lần đều ra 34.276.197). Đọc thêm một lần trên các dải phóng to trước khi kết luận
    # chính BCTC in lệch.
    pending = [q for group in groups if not any(confirmed(p) for p in group)
               and all(_same_raw(reread.get((p.statement, p.row, p.column_kind)), p.before, sep) for p in group)
               for p in group for q in (p, p.partner) if q is not None]
    zoom_pages: dict[tuple[str, int], list] = {}
    for q in pending:
        page = record["raw"][q.statement]["rows"][q.row].get("page")
        if page:
            zoom_pages.setdefault((q.statement, int(page)), []).append(q)
    for (st, page), qs in zoom_pages.items():
        ids = {f"o{n}": q for n, q in enumerate(qs, 1)}
        asked = _asked_cells(record, ids)
        for strip in render_strips(doc, page, _rotation(record, page)):
            result = client.json_from_images(
                prompts.verify_prompt(st, asked) + "\nẢnh chỉ là một dải của trang: ô nào không có trong ảnh thì trả null.",
                [(f"Trang {page} (một phần)", strip)], prompts.REREAD_SCHEMA, "reread_cells", step="repair_zoom",
                detail=ORIGINAL)
            for ans in result.get("cells", []):
                q = ids.get((ans.get("code") or "").strip())
                if q is not None and ans.get("value"):
                    zoomed.setdefault((q.statement, q.row, q.column_kind), []).append(ans["value"])

    # Người đọc bậc cao (thang leo thang: mô hình mạnh hơn): nhóm vẫn chưa ô nào được ảnh xác nhận thì nhờ một mô hình
    # mạnh hơn đọc lại cả trang, chỉ khi người quản trị đã chọn mô hình cho bước repair_escalate (trang Chi phí). Đo
    # 17/10/2026: Claude Opus 5.5 đọc đúng ô FPT bị con dấu đè và ô VHM mà Haiku đọc lại vẫn nhầm.
    if any(k.startswith("repair_escalate") for k in getattr(client, "step_providers", {})):
        esc_pages: dict[tuple[str, int], list] = {}
        for group in groups:
            if any(confirmed(p) for p in group):
                continue
            for p in group:
                for q in (p, p.partner):
                    page = record["raw"][q.statement]["rows"][q.row].get("page") if q is not None else None
                    if page:
                        esc_pages.setdefault((q.statement, int(page)), []).append(q)
        for (st, page), qs in esc_pages.items():
            unique = list({(q.statement, q.row, q.column_kind): q for q in qs}.values())
            ids = {f"o{n}": q for n, q in enumerate(unique, 1)}
            result = client.json_from_images(prompts.verify_prompt(st, _asked_cells(record, ids)),
                                             [(f"Trang {page}", render_sharp(doc, page, _rotation(record, page)))],
                                             prompts.REREAD_SCHEMA, "reread_cells", step="repair_escalate",
                                             detail=ORIGINAL)
            for ans in result.get("cells", []):
                q = ids.get((ans.get("code") or "").strip())
                if q is not None:
                    escalated[(q.statement, q.row, q.column_kind)] = ans.get("value")

    log = record.setdefault("repairs", [])
    changed = False
    for group in groups:
        ok = [p for p in group if confirmed(p) and (p.partner is None or confirmed(p.partner))]
        accepted = ok[0] if len(ok) == 1 else None
        for p in group:
            for q in (p, p.partner):
                if q is None:
                    continue
                log.append(proposal_dict(q) | {"reread": reread.get((q.statement, q.row, q.column_kind)),
                                               "zoomed": zoomed.get((q.statement, q.row, q.column_kind)),
                                               "escalated": escalated.get((q.statement, q.row, q.column_kind)),
                                               "accepted": accepted is not None and q in (accepted, accepted.partner),
                                               "group_size": len(group), "model": client.cfg.model})
        if accepted is not None:
            for q in (accepted, accepted.partner):
                if q is not None:
                    record["raw"][q.statement]["rows"][q.row]["values"][q.column_kind] = q.after
            changed = True
        elif all(_same_raw(reread.get((p.statement, p.row, p.column_kind)), p.before, sep)
                 and all(_same_raw(v, p.before, sep) for v in zoomed.get((p.statement, p.row, p.column_kind), []))
                 and ((p.statement, p.row, p.column_kind) not in escalated
                      or _same_raw(escalated[(p.statement, p.row, p.column_kind)], p.before, sep))
                 for p in group):
            record.setdefault("filing_mismatch", []).append(sorted({f for p in group for f in p.fixes}))
    return changed


def _label_on_page(record: dict, statement: str, row: int, label: str | None = None) -> str:
    """Tên dòng để hỏi khi đọc lại. Trang có nhiều dòng cùng tên (TCX: hai dòng "Lợi nhuận đã thực hiện") thì nói rõ
    dòng thứ mấy có tên này trên trang, nếu không mô hình đọc đúng số nhưng của dòng kia."""
    rows = record["raw"][statement]["rows"]
    label = label if label is not None else rows[row].get("label") or ""
    norm = lambda x: re.sub(r"\s+", " ", unicodedata.normalize("NFC", x or "")).strip().casefold()
    page = rows[row].get("page")
    same = [i for i, r in enumerate(rows) if r.get("page") == page and norm(r.get("label")) == norm(label)]
    if len(same) < 2 or row not in same:
        return label
    return f"{label} (dòng thứ {same.index(row) + 1} trong {len(same)} dòng cùng tên này trên trang, tính từ trên xuống)"


def _asked_column(record: dict, col: str) -> str:
    """Tên cột để hỏi khi đọc lại. BCTC bán niên/năm chỉ in một cặp cột cả kỳ, mô tả cột trong lời nhắc gọi nó là
    ytd_cur/ytd_prev_year, nhưng bản chép có thể đã ghi vào q_cur/q_prev_year (BID, HPG, VHM... bán niên 2026); hỏi
    "q_cur" thì mô hình trả rỗng vì không thấy cột quý nào."""
    if record.get("doc_type") in ("fs_semiannual", "fs_annual"):
        return {"q_cur": "ytd_cur", "q_prev_year": "ytd_prev_year"}.get(col, col)
    return col


def _asked_cells(record: dict, ids: dict) -> list[tuple[str, str | None, str, str]]:
    return [(cid, None if q.code.startswith(("~", "b.")) else q.code, _label_on_page(record, q.statement, q.row, q.label),
             _asked_column(record, q.column_kind)) for cid, q in ids.items()]


def _reread_on_page(client: VisionClient, doc, record: dict, st: str, page: int, ids: dict, prompt, step: str,
                    row_of) -> dict[str, str | None]:
    """Hỏi các ô `ids` trên trang `page`; ô nào trả rỗng thì hỏi lại ở trang liền trước/sau của cùng báo cáo và, nếu
    thấy ở đó, ghi lại trang của dòng (row_of(ô) -> chỉ số dòng). Mô hình đôi khi đặt ranh giới trang lệch một khối
    (VPL bán niên 2026: mục II LCTT ghi trang 13, thật ra ở trang 12), khi đó đọc lại trên trang đã ghi luôn ra rỗng.
    prompt(ids con) -> lời nhắc. Trả {mã ô: giá trị}."""
    rows = record["raw"][st]["rows"]
    st_pages = {int(r["page"]) for r in rows if r.get("page")}
    out: dict[str, str | None] = {}
    todo = dict(ids)
    for p in [page] + [n for n in (page - 1, page + 1) if n in st_pages]:
        if not todo:
            break
        result = client.json_from_images(prompt(todo), [(f"Trang {p}", render_sharp(doc, p, _rotation(record, p)))],
                                         prompts.REREAD_SCHEMA, "reread_cells", step=step, detail=ORIGINAL)
        for ans in result.get("cells", []):
            cid = (ans.get("code") or "").strip()
            if cid in todo and (cid not in out or ans.get("value")):
                out[cid] = ans.get("value")
                if ans.get("value") and p != page:
                    rows[row_of(todo[cid])]["page"] = p
        todo = {cid: x for cid, x in todo.items() if not out.get(cid)}
    return out


def _try_load(conn, document_id: int) -> dict | None:
    try:
        return _load_record(conn, document_id)
    except RuntimeError:
        return None


def _same_raw(a: str | None, b: str | None, sep: str) -> bool:
    """Cùng dãy chữ số (lần đọc lại có thể viết dấu phân tách hay dấu ngoặc khác)."""
    da, db = re.sub(r"\D", "", a or ""), re.sub(r"\D", "", b or "")
    return bool(da) and da.lstrip("0") == db.lstrip("0")


def _extend_balance_sheet(record: dict, client: VisionClient, doc) -> bool:
    """Chép thêm trang ngay sau trang BCĐKT cuối cùng nếu chưa kiểm được tổng tài sản = tổng nguồn vốn.

    Ví dụ BSR quý 2/2026: bước định vị trang chỉ nhận trang 4 (tài sản) là BCĐKT, bỏ sót trang 5 (nguồn vốn).
    Giữ trang thêm khi nhờ nó kiểm được phương trình cân đối.
    """
    _, _, _, template, checks = _check(record)
    if not template or "BS" not in record["raw"] or any(BALANCE_RULE.search(c.rule_id) for c in checks):
        return False
    chosen = next(c for c in record["candidates"] if c["name"] == record["chosen"])
    used = {int(p) for pages in chosen["statement_pages"].values() for p in pages}
    page = max(int(p) for p in chosen["statement_pages"]["BS"]) + 1
    if page > doc.page_count or page in used:
        return False
    image = _extract_image(doc, page, _rotation(record, page))
    extra = client.json_from_images(prompts.extract_prompt("BS"), [(f"Trang {page}", image)],
                                    prompts.extract_schema("BS"), "statement_BS", step="extend_BS",
                                    detail=_extract_detail(doc, [page]))
    before = record["raw"]["BS"]
    record["raw"]["BS"] = before | {"rows": before.get("rows", []) + extra.get("rows", [])}
    _, _, _, _, checks = _check(record)
    kept = any(c.gate and BALANCE_RULE.search(c.rule_id) for c in checks)
    if kept:
        chosen["statement_pages"]["BS"] = [*chosen["statement_pages"]["BS"], page]
    else:
        record["raw"]["BS"] = before
    record.setdefault("extensions", []).append({"statement": "BS", "page": page, "rows": len(extra.get("rows", [])),
                                                "kept": kept, "model": client.cfg.model})
    return kept


def _gate_failures(record: dict) -> dict[str, int]:
    """Số ràng buộc bắt buộc bị lệch theo từng báo cáo."""
    return {st: f for st, (f, _) in _gate_tally(record).items() if f}


def _gate_tally(record: dict) -> dict[str, tuple[int, int]]:
    """(số ràng buộc bắt buộc lệch, số đạt) theo từng báo cáo."""
    _, _, _, template, checks = _check(record)
    if not template:
        return {}
    statement_of = {r.id: r.statement for r in RULESETS[template].rules}
    out: dict[str, tuple[int, int]] = {}
    for c in checks:
        if c.gate and c.rule_id in statement_of:
            f, p = out.get(statement_of[c.rule_id], (0, 0))
            out[statement_of[c.rule_id]] = (f + (not c.passed), p + c.passed)
    return out


def _reextract_failed_statements(record: dict, client: VisionClient, doc) -> bool:
    """Chép lại theo từng trang các báo cáo có ràng buộc bắt buộc lệch hoặc chưa có ràng buộc nào đạt.

    Lần 1 giữ hướng trang như bước định vị; vẫn chưa ổn thì xoay thêm 180 độ từng trang (VHM quý 1/2026 in ngược
    một trang mà bước định vị không nhận ra). Mỗi (trang, hướng) chỉ gọi mô hình một lần.
    """
    tally = _gate_tally(record)
    if not tally and not record.get("template_ver"):
        _, _, _, template, _ = _check(record)
        if not template:
            return False
    targets = {st: tally.get(st, (0, 0)) for st in record["raw"]
               if tally.get(st, (0, 0))[0] > 0 or (st in ("BS", "IS") and tally.get(st, (0, 0))[1] == 0)}
    if not targets:
        return False
    chosen = next(c for c in record["candidates"] if c["name"] == record["chosen"])
    st_pages = {k: [int(x) for x in v] for k, v in chosen["statement_pages"].items()}
    log = record.setdefault("reextracts", [])
    improved = False
    for st in targets:
        pages = st_pages.get(st, [])
        if not pages:
            continue
        base = {page: _rotation(record, page) for page in pages}
        cache: dict[tuple[int, int], dict] = {}

        def read(page: int, rotation: int) -> dict:
            if (page, rotation) not in cache:
                image = render_sharp(doc, page, rotation)
                cache[(page, rotation)] = client.json_from_images(
                    prompts.extract_prompt(st), [(f"Trang {page}", image)], prompts.extract_schema(st),
                    f"statement_{st}", step=f"reextract_{st}", detail=ORIGINAL)
            return cache[(page, rotation)]

        # Lần 1 giữ hướng trang như bước định vị; chưa ổn thì xoay thêm 180 độ TỪNG trang một (VHM quý 1/2026: chỉ
        # trang 86 in ngược, trang 87 cùng báo cáo vẫn đúng chiều; xoay cả hai thì trang 87 hỏng theo)
        variants = [(0, base)] + [(180, {**base, p: (base[p] + 180) % 360}) for p in pages]
        for extra_rotation, rotations in variants:
            n_failed, passed_before = _gate_tally(record).get(st, (0, 0))
            if extra_rotation and n_failed == 0 and passed_before > 0:
                break
            parts = [read(page, rotations[page]) for page in pages]
            merged = {
                "unit_text": next((x["unit_text"] for x in parts if x.get("unit_text")), None),
                "columns": parts[0].get("columns", []),
                "rows": [r for x in parts for r in x.get("rows", [])],
            }
            before = record["raw"][st]
            record["raw"][st] = merged
            after_failed, passed_after = _gate_tally(record).get(st, (0, 0))
            # Giữ khi số phép đạt trừ số phép lệch tăng và số phép đạt không giảm. Chỉ so số phép lệch thì sai cả hai
            # chiều: bản chép lại mất mã số chạy được ít ràng buộc hơn nên ít lệch hơn (TCX quý 2/2026: lệch 2 -> 0
            # nhưng ràng buộc KQKD chạy được giảm từ 28 xuống 12), còn bản đọc đúng chiều trang thì chạy được nhiều
            # ràng buộc hơn, có thể lộ thêm vài ô nhầm chữ số mà bước định vị sửa được sau đó (VHM quý 1/2026)
            net_after, net_before = passed_after - after_failed, passed_before - n_failed
            kept = passed_after >= passed_before and (net_after > net_before
                                                      or (net_after == net_before and passed_after > passed_before))
            if not kept:
                record["raw"][st] = before
            else:
                improved = True
                if extra_rotation:
                    saved = chosen.setdefault("rotations", {})
                    for p, r in rotations.items():   # khóa số (vừa định vị) hoặc chuỗi (đọc lại từ JSON)
                        saved.pop(p, None)
                        saved[str(p)] = r
            log.append({"statement": st, "pages": pages, "rotation_added": extra_rotation,
                        "rotations": {str(p): r for p, r in rotations.items()},
                        "failed_before": n_failed, "failed_after": after_failed,
                        "passed_before": passed_before, "passed_after": passed_after,
                        "rows_before": len(before.get("rows", [])), "rows_after": len(merged["rows"]),
                        "kept": kept, "model": client.cfg.model})
    return improved


def _rotation(record: dict, page: int) -> int:
    """Số độ cần xoay trang (theo kết quả định vị trang). Khóa có thể là số hoặc chuỗi sau khi đọc lại từ JSON."""
    chosen = next(c for c in record["candidates"] if c["name"] == record["chosen"])
    rotations = chosen.get("rotations", {})
    return int(rotations.get(page, rotations.get(str(page), 0)))


_CHECK_CACHE: dict[tuple, tuple] = {}


def _check_cached(record: dict):
    """_check cho chỗ chỉ đọc (thẻ, bằng chứng ô): dùng lại kết quả khi phần số đã chép và mẫu công ty không đổi. Khóa
    lấy theo nội dung nên bản ghi đang sửa dở trong bộ nhớ (đọc lại, bộ đo) không bao giờ nhận nhầm kết quả cũ. Kết
    quả dùng chung: người gọi không được sửa."""
    key = (record.get("company_template"),
           hashlib.sha1(json.dumps(record.get("raw"), sort_keys=True, ensure_ascii=False).encode()).hexdigest())
    got = _CHECK_CACHE.get(key)
    if got is None:
        if len(_CHECK_CACHE) > 2000:
            _CHECK_CACHE.clear()
        got = _CHECK_CACHE[key] = (_check(record), record.get("codes_inferred"))
    else:
        record["codes_inferred"] = got[1]
    return got[0]


# Dòng chia LNST theo công ty mẹ / cổ đông không kiểm soát mà BCTC không in mã số (VIC quý 1/2026): gán mã 61/62 theo
# tên để ràng buộc 61 + 62 = 60 kiểm được chúng. Thiếu bước này thì thẻ lấy nhầm dòng 60 (gồm cả phần cổ đông không
# kiểm soát) làm LNST công ty mẹ: VIC quý 1/2026 hiện 5.611 tỷ thay vì 7.276 tỷ.
_SPLIT_LABELS = (("61", re.compile(r"sau thuế (thu nhập doanh nghiệp )?(của )?(cổ đông )?(của )?công ty mẹ|chủ sở hữu (của )?công ty mẹ")),
                 ("62", re.compile(r"cổ đông không kiểm soát|cổ đông thiểu số|lợi ích (của )?cổ đông không")))


# Dòng đầu LCTT gián tiếp đôi khi mất cả số thứ tự lẫn mã số (VIC quý 4/2025: "Lợi nhuận trước thuế" không có "01"),
# và không suy được từ phép cộng 08 = 01 + ... + 07 vì dòng 07 cũng vắng mặt
_CF_PBT_LABEL = re.compile(r"^(1\.?\s*)?lợi nhuận (kế toán )?trước thuế")


def _label_split_codes(extracted, statements) -> list[dict]:
    """Gán mã theo tên dòng cho các dòng quan trọng mà BCTC không in mã: 61/62 trên KQKD, 01 trên LCTT gián tiếp."""
    out = []
    st = statements.get("IS")
    ex = next((e for e in extracted if e.statement == "IS"), None)
    if st is not None and ex is not None and "60" in st.values and "61" not in st.values and "62" not in st.values:
        for code, pattern in _SPLIT_LABELS:
            hit = next((it for it in ex.items if normalize_code(it.code) is None
                        and pattern.search(unicodedata.normalize("NFC", it.label or "").casefold())
                        and any(v not in (None, "", "-") for v in it.values_raw.values())), None)
            if hit is not None:
                hit.code = code
                out.append({"statement": "IS", "code": code, "label": hit.label, "rule": "label"})
    cf = statements.get("CF")
    ex = next((e for e in extracted if e.statement == "CF"), None)
    # Chỉ khi các dòng điều chỉnh 02-07 đã có mã: nếu chúng cũng mất mã (VPL quý 4/2025) thì gán riêng 01 làm phép kiểm
    # 08 = 01 + ... + 07 chạy với gần hết số hạng vắng mặt và báo lệch giả
    if (cf is not None and ex is not None and "08" in cf.values and "01" not in cf.values
            and any(c in cf.values for c in ("02", "03", "04", "05", "06", "07"))):
        hit = next((it for it in ex.items if normalize_code(it.code) is None
                    and _CF_PBT_LABEL.search(unicodedata.normalize("NFC", it.label or "").strip().casefold())
                    and any(v not in (None, "", "-") for v in it.values_raw.values())), None)
        if hit is not None:
            hit.code = "01"
            out.append({"statement": "CF", "code": "01", "label": hit.label, "rule": "label"})
    return out


def _check(record: dict):
    extracted, statements, sep, template, checks = _check_variants(record)
    if template in ("TT200", "TT99") and (labelled := _label_split_codes(extracted, statements)):
        statements, sep = normalize(extracted)
        checks = validate(statements, template)
        record["codes_from_labels"] = labelled
    inferred = _infer_missing_codes(extracted, statements, sep, template, checks) if template else []
    record["codes_inferred"] = inferred
    if inferred:
        statements, sep = normalize(extracted)
        checks = validate(statements, template)
    if template in ("TT200", "TT99") and (positional := _cf_positional_codes(extracted, sep)):
        statements, sep = normalize(extracted)
        checks = validate(statements, template)
        record["cf_positional"] = positional
    return extracted, statements, sep, template, checks


# Dòng tổng của LCTT gián tiếp theo tên dòng, dùng khi BCTC (hoặc bản chép) không có mã số (MSN quý 1/2026)
_CF_TOTAL_LABELS = (
    ("08", re.compile(r"(lợi nhuận|lãi)( thuần)? (từ )?hoạt động kinh doanh trước (những )?thay đổi vốn lưu động")),
    ("20", re.compile(r"^(lưu chuyển )?tiền thuần (từ |thu từ |sử dụng vào |\(sử dụng vào\)/thu từ )?(các )?hoạt động kinh doanh")),
    ("30", re.compile(r"^(lưu chuyển )?tiền thuần (từ |thu từ |sử dụng vào |\(sử dụng vào\)/thu từ )?(các )?hoạt động đầu tư")),
    ("40", re.compile(r"^(lưu chuyển )?tiền thuần (từ |thu từ |sử dụng vào |\(sử dụng vào\)/thu từ )?(các )?hoạt động tài chính")),
    ("50", re.compile(r"^(lưu chuyển )?tiền thuần (trong|tăng|giảm)")),
    ("60", re.compile(r"^tiền và (các khoản )?tương đương tiền (đầu|tại ngày 0?1)")),
    ("61", re.compile(r"ảnh hưởng .*tỷ giá")),
    ("70", re.compile(r"^tiền và (các khoản )?tương đương tiền (cuối|tại ngày 3)")),
)


def _cf_positional_codes(extracted, sep: str) -> list[dict]:
    """LCTT có dòng không mã số: gán mã dòng tổng theo tên (nếu dòng tổng cũng thiếu mã), rồi các dòng không mã nằm
    giữa hai dòng tổng thành thành phần của dòng tổng phía dưới (mã "20.1", "20.2"...), để kiểm "dòng tổng = tổng các
    dòng thành phần" (rules.TT200/TT99, group_statements). VPL quý 4/2025: dòng 01-07 không in mã; MSN bán niên 2026:
    bản chép không có cột mã. BCTC in đủ mã thì không đổi gì. Chỉ áp cho phương pháp gián tiếp (có dòng 08)."""
    ex = next((e for e in extracted if e.statement == "CF"), None)
    if ex is None:
        return []
    def has_values(it):
        return any(v not in (None, "", "-") for v in it.values_raw.values())
    loose = [it for it in ex.items if normalize_code(it.code) is None and has_values(it)]
    if not loose:
        return []
    def folded(it):
        return unicodedata.normalize("NFC", it.label or "").strip().casefold()
    out = []
    present = {normalize_code(it.code) for it in ex.items}
    if "08" not in present and not any(_CF_TOTAL_LABELS[0][1].search(folded(it)) for it in loose):
        return out   # phương pháp trực tiếp (SAB): các dòng 01-07 đứng riêng, không gán theo vị trí
    for code, pattern in _CF_TOTAL_LABELS:
        if code in present:
            continue
        hits = [it for it in ex.items if normalize_code(it.code) is None and has_values(it)
                and pattern.search(folded(it))]
        if hits:
            hit = hits[-1] if code == "20" else hits[0]
            hit.code = code
            present.add(code)
            out.append({"code": code, "label": hit.label, "rule": "label"})
    # Khúc nào lẫn dòng có số có mã và dòng không mã (trừ 01, đã tính qua group_extra) thì không gán: tổng các dòng
    # không mã sẽ thiếu phần của dòng có mã
    block, mixed = [], False
    for it in ex.items:
        code = normalize_code(it.code)
        if code in ("08", "20", "30", "40"):
            if not mixed:
                out += _number_block(code, block, ex.items, sep)
            block, mixed = [], False
        elif code is None:
            if has_values(it):
                block.append(it)
        elif code in ("50", "60", "61", "70"):
            block, mixed = [], False
        elif code != "01" and has_values(it):
            mixed = True
    return out


def _number_block(total: str, block: list, items: list, sep: str) -> list[dict]:
    """Đánh mã "{total}.k" cho các dòng thành phần. Dòng tổng tạm không tên (MSN: "Tiền từ hoạt động kinh doanh" =
    08 + các biến động vốn lưu động, đứng trước tiền lãi vay đã trả) thành "{total}.1", các dòng trước nó thành
    "{total}.1.j": nhận ra vì số của nó bằng tổng các dòng trước nó trong khúc (cộng 08 với khúc của 20) ở mọi cột."""
    def amounts(it):
        return {k: parse_amount(v, sep) for k, v in it.values_raw.items()}
    extra = next((amounts(it) for it in items if total == "20" and normalize_code(it.code) == "08"), {})
    subtotal = None
    running = {k: v or Decimal(0) for k, v in extra.items()}
    for i, it in enumerate(block):
        vals = amounts(it)
        filled = {k: v for k, v in vals.items() if v is not None}
        if i >= 2 and filled and any(filled.values()) and all(
                abs(v - running.get(k, Decimal(0))) <= i + 1 for k, v in filled.items()):
            subtotal = i
            break
        for k, v in vals.items():
            running[k] = running.get(k, Decimal(0)) + (v or Decimal(0))
    out = []
    def put(it, code):
        it.code = code
        out.append({"code": code, "label": it.label, "rule": "position"})
    if subtotal is None:
        for k, it in enumerate(block, 1):
            put(it, f"{total}.{k}")
        return out
    for j, it in enumerate(block[:subtotal], 1):
        put(it, f"{total}.1.{j}")
    put(block[subtotal], f"{total}.1")
    for k, it in enumerate(block[subtotal + 1:], 2):
        put(it, f"{total}.{k}")
    return out


def _infer_missing_codes(extracted, statements, sep, template, checks) -> list[dict]:
    """Gán mã cho dòng mô hình chép thiếu mã số, chỉ khi số liệu chứng minh được.

    Ràng buộc bắt buộc bị lệch và thiếu đúng một số hạng; một dòng chưa có mã trong cùng báo cáo có số bằng đúng phần
    còn thiếu ở mọi cột (ít nhất 2 cột) thì dòng đó là số hạng thiếu. Ví dụ SSI quý 2/2026: dòng "KẾT QUẢ HOẠT ĐỘNG"
    bị chép thiếu mã 70 nên ràng buộc 90 = 70 + 80 lệch; số của dòng đó khớp 90 - 80 ở cả 4 cột.
    """
    rs = RULESETS[template]
    failed = {c.rule_id for c in checks if c.gate and not c.passed}
    inferred: list[dict] = []
    for r in rs.rules:
        st = statements.get(r.statement)
        if r.id not in failed or st is None or r.statement == "IS" and expenses_printed_negative(st, rs.expense_codes):
            continue
        missing = [c for _, c in r.rhs if c not in st.values]
        if len(missing) != 1 or missing[0] in r.abs_codes:
            continue
        code = missing[0]
        sign = next(sg for sg, c in r.rhs if c == code)
        residual = {col: (lhs - sum(sg * st.values.get(c, {}).get(col, Decimal(0)) for sg, c in r.rhs if c != code)) * sign
                    for col, lhs in st.values[r.lhs].items()}
        tolerance = st.multiplier * (len(r.rhs) + 1)
        ex = next(e for e in extracted if e.statement == r.statement)
        for it in ex.items:
            if normalize_code(it.code) is not None:
                continue
            vals = {col: v * st.multiplier for col, raw in it.values_raw.items() if (v := parse_amount(raw, sep)) is not None}
            if len(vals) >= 2 and set(vals) == set(residual) and all(abs(vals[c] - residual[c]) <= tolerance for c in vals):
                it.code = code
                inferred.append({"statement": r.statement, "code": code, "label": it.label, "rule": r.id})
                break
    return inferred


def _check_variants(record: dict):
    company_template = record["company_template"]
    if company_template == "bank":
        # Hai phương án gán tên chỉ tiêu: nguyên văn mô hình chép, và có sửa lỗi lệch tên khi tên xuống nhiều dòng
        # (bank.repair_wrapped_labels). Ràng buộc kế toán chọn phương án ít lệch hơn; hòa thì giữ nguyên văn.
        best = None
        for repair in (False, True):
            extracted = [_to_extracted(st, raw) for st, raw in record["raw"].items()]
            unmapped = canonicalize(extracted, repair_labels=repair)
            statements, sep = normalize(extracted)
            checks = validate(statements, "TCTD")
            failed = sum(c.gate and not c.passed for c in checks)
            if best is None or failed < best[0]:
                best = (failed, repair, unmapped, extracted, statements, sep, checks)
        _, repair, record["bank_unmapped"], extracted, statements, sep, checks = best
        record["labels_repaired"] = repair
        return extracted, statements, sep, "TCTD", checks

    if company_template not in ("corporate", "securities"):
        extracted = [_to_extracted(st, raw) for st, raw in record["raw"].items()]
        statements, sep = normalize(extracted)
        return extracted, statements, sep, None, []

    # Cột mã số thường nằm sau tên chỉ tiêu, nhưng có BCTC in ở ngoài cùng bên trái, trước số thứ tự (ví dụ VIC quý
    # 2/2026), và mô hình có thể chép đảo hai cột, có khi chỉ ở một trang (TCX quý 2/2026 khi chép lại theo trang).
    # Thử đảo stt <-> code theo từng (báo cáo, trang) có cột stt trông giống mã số, lần lượt từng đơn vị, giữ khi
    # ràng buộc kế toán tốt hơn (nhận ra mẫu, ít lệch, nhiều ràng buộc đạt); hòa thì giữ nguyên văn.
    fixed_template = {"securities": "CTCK"}.get(company_template)

    baseline_checks = 0     # số ràng buộc bắt buộc được kiểm khi giữ nguyên văn

    def evaluate(swapped: frozenset):
        raws = {st: _swap_stt_code(raw, {p for s_, p in swapped if s_ == st and p != PROMOTE}, (st, PROMOTE) in swapped)
                for st, raw in record["raw"].items()}
        extracted = [_to_extracted(st, raw) for st, raw in raws.items()]
        statements, sep = normalize(extracted)
        template = fixed_template or detect_template(statements)
        checks = validate(statements, template) if template else []
        failed = sum(c.gate and not c.passed for c in checks)
        passed = sum(c.gate and c.passed for c in checks)
        # Phương án làm mất dòng tổng (mã bị thay bằng số thứ tự) thì ít ràng buộc được kiểm hơn nên cũng ít lệch hơn,
        # dù sai (VHM quý 4/2025: lấy stt làm mã còn 36 phép kiểm, giữ nguyên văn 80). Mỗi phép kiểm bị mất so với
        # bản nguyên văn tính như một lần lệch.
        lost = max(0, baseline_checks - failed - passed)
        return (template is None, failed + lost, -passed, len(swapped)), (extracted, statements, sep, template, checks)

    # Thử đảo cả báo cáo trước (tổng tài sản cần cả trang 100 lẫn trang 200 cùng đúng), rồi bật/tắt từng trang
    units = {st: [(st, page) for page in _pages_with_code_like_stt(raw)] for st, raw in record["raw"].items()}
    swapped: frozenset = frozenset()
    best_score, best = evaluate(swapped)
    baseline_checks = sum(c.gate for c in best[4])
    # Mốc "số phép kiểm" lấy thêm từ phương án đảo mọi trang: bản nguyên văn có khi không có mã ở cả một trang
    # (VHM quý 2/2026 trang 12), nếu chỉ lấy mốc nguyên văn thì bỏ mã trang đó không bị phạt, và một ô đọc sai trên
    # trang làm phương án bỏ mã thắng, mất cả trang khỏi kiểm tra
    every = frozenset(u for us in units.values() for u in us)
    if every:
        baseline_checks = max(baseline_checks, sum(c.gate for c in evaluate(every)[1][4]))
        best_score, best = evaluate(swapped)
    moves = [frozenset(u) for u in units.values() if u] + [frozenset([u]) for us in units.values() for u in us]
    # Mô hình chép lẫn lộn trong cùng một bảng: dòng thì mã số ở cột stt (cột code là số thuyết minh), dòng thì đúng
    # chỗ (MSN quý 1/2026). Phương án: dòng nào có stt dạng số thì lấy stt làm mã.
    moves += [frozenset([(st, PROMOTE)]) for st, raw in record["raw"].items()
              if any(re.fullmatch(r"\d{1,3}[a-z]?", str(r.get("stt") or "")) for r in raw.get("rows", []))]
    for move in moves:
        candidate = swapped ^ move
        score, result = evaluate(candidate)
        if score < best_score:
            swapped, best_score, best = candidate, score, result
    record["stt_code_swapped"] = sorted(f"{st}@{p}" for st, p in swapped if p != PROMOTE)
    record["stt_promoted"] = sorted(st for st, p in swapped if p == PROMOTE)
    return best


_CODE_LIKE = re.compile(r"\d{2,3}[a-z]?")


def _pages_with_code_like_stt(raw: dict) -> list:
    """Các trang mà cột stt giống mã số hơn cột code (đa số là số 2-3 chữ số như "10", "110", "411a")."""
    def share(rows, key: str) -> float:
        vals = [str(r[key]).strip() for r in rows if r.get(key)]
        return sum(bool(_CODE_LIKE.fullmatch(v)) for v in vals) / len(vals) if vals else 0.0
    pages = sorted({r.get("page") for r in raw.get("rows", [])}, key=lambda p: (p is None, p))
    out = []
    for page in pages:
        rows = [r for r in raw.get("rows", []) if r.get("page") == page]
        if share(rows, "stt") >= 0.5 and share(rows, "stt") > share(rows, "code"):
            out.append(page)
    return out


PROMOTE = "stt"   # đơn vị phương án "lấy stt dạng số làm mã" (khác với đảo theo trang)


def _swap_stt_code(raw: dict, pages: set, promote: bool = False) -> dict:
    """Đảo stt <-> code cho các dòng ở `pages`; `promote`: dòng có stt dạng số thì lấy stt làm mã, code cũ làm thuyết minh."""
    if not pages and not promote:
        return raw
    rows = []
    for r in raw.get("rows", []):
        if r.get("page") in pages:
            r = r | {"stt": r.get("code"), "code": r.get("stt")}
        elif promote and re.fullmatch(r"\d{1,3}[a-z]?", str(r.get("stt") or "")):
            r = r | {"code": r["stt"], "stt": None, "note": r.get("note") or r.get("code")}
        rows.append(r)
    return raw | {"rows": rows}


def _gate_score(record: dict) -> tuple[int, int]:
    """(tổng số ràng buộc bắt buộc lệch, tổng số đạt) của cả tài liệu."""
    tally = _gate_tally(record).values()
    return sum(f for f, _ in tally), sum(p for _, p in tally)


def _reread_failed(record: dict, client: VisionClient, doc) -> bool:
    """Đọc lại các ô thuộc ràng buộc bắt buộc bị lệch. Số đọc lại chỉ được giữ khi làm giảm số ràng buộc lệch mà không
    làm giảm số ràng buộc đạt (trước 12/10/2026 giữ mọi số đọc ra khác: một lần đọc lại nhầm dòng cũng được nhận).
    Trả về True nếu có ô được sửa."""
    _, statements, _, template, checks = _check(record)
    failed = [c for c in checks if c.gate and not c.passed]
    if not failed:
        return False

    rules = {r.id: r for r in RULESETS[template].rules}
    suspects: set[tuple[str, str, str]] = set()        # (statement, code, column_kind)
    for c in failed:
        r = rules.get(c.rule_id)
        if r is None:                                   # ràng buộc chéo giữa hai báo cáo
            continue
        for code in [r.lhs, *(code for _, code in r.rhs)]:
            if code in statements[r.statement].values:
                suspects.add((r.statement, code, c.column_kind))

    # Gom theo (báo cáo, trang) để mỗi trang chỉ gọi một lần
    by_page: dict[tuple[str, int], list[tuple[str, str, str]]] = {}
    for st, code, col in sorted(suspects):
        row = next((r for r in record["raw"][st]["rows"] if normalize_code(r.get("code")) == code), None)
        if row is None or not row.get("page"):
            continue
        by_page.setdefault((st, row["page"]), []).append((code, row.get("label", ""), col))

    changed = False
    log = record.setdefault("rereads", [])
    for (st, page), cells in by_page.items():
        image = render_sharp(doc, page, _rotation(record, page))
        result = client.json_from_images(prompts.reread_prompt(st, cells), [(f"Trang {page}", image)],
                                         prompts.REREAD_SCHEMA, "reread_cells", detail=ORIGINAL)
        for cell in result.get("cells", []):
            code, col, value = normalize_code(cell.get("code")), cell.get("column_kind"), cell.get("value")
            row = next((r for r in record["raw"][st]["rows"] if normalize_code(r.get("code")) == code), None)
            if row is None or col not in row["values"] or value is None:
                continue
            before = row["values"][col]
            kept = False
            if value != before:
                failed0, passed0 = _gate_score(record)
                row["values"][col] = value
                failed1, passed1 = _gate_score(record)
                kept = failed1 < failed0 and passed1 >= passed0
                if kept:
                    changed = True
                else:
                    row["values"][col] = before
            log.append({"statement": st, "code": code, "column_kind": col, "page": page,
                        "before": before, "after": value, "kept": kept, "model": client.cfg.model})
    return changed


def reread_document(conn: psycopg.Connection, document_id: int, client: VisionClient) -> dict:
    """Đọc lại các ô bị lệch cho một tài liệu đã trích xuất (không chép lại cả bảng)."""
    record = _load_record(conn, document_id)
    doc = open_record_pdf(conn, record)
    with track_usage(record, client):
        _escalate(record, client, doc, conn)
    return _finalize(conn, record)


def open_record_pdf(conn: psycopg.Connection, record: dict):
    """Mở đúng file PDF mà bản ghi trích xuất đã đọc."""
    path = raw_data_dir() / conn.execute(
        "SELECT storage_key FROM document_files WHERE id = %s", (record["file_id"],)).fetchone()[0]
    return open_pdf(next(c for c in candidates(path) if c.name == record["chosen"]))


@contextmanager
def track_usage(record: dict, client: VisionClient):
    """Cộng thêm chi phí các lần gọi mô hình trong khối lệnh vào usage và usage_by_step của bản ghi."""
    usage_before, steps_before, switches_before = asdict(client.usage), client.steps_snapshot(), len(client.switches)
    yield
    if client.switches[switches_before:]:
        record.setdefault("llm_switches", []).extend(client.switches[switches_before:])
    usage = record.get("usage") or {}
    for k, v in asdict(client.usage).items():
        usage[k] = usage.get(k, 0) + v - usage_before[k]
    record["usage"] = usage
    by_step = record.setdefault("usage_by_step", {})
    for step, d in usage_delta(client.steps_snapshot(), steps_before).items():
        cur = by_step.setdefault(step, {k: 0 for k in d})
        for k, v in d.items():
            cur[k] = cur.get(k, 0) + v


# Chỉ mục file kết quả theo mã tài liệu. Trước đây mỗi lần đọc là một lần glob cả thư mục extracted: trên ổ Windows gắn
# vào Docker, mỗi lần hỏi thông tin file mất ~0,3 ms nên trang mùa BCTC (vài trăm lần đọc) mất ~10 giây. Chỉ mục và nội
# dung file được dùng lại trong REFRESH_SECONDS; quá thời gian đó thì quét lại (bản ghi vừa ghi xong được thấy ngay vì
# _finalize xóa chỉ mục).
REFRESH_SECONDS = 2.0
_INDEX: dict = {"at": 0.0, "files": {}}
_TEXT: dict[Path, tuple[float, int, int, str]] = {}


def _invalidate_index() -> None:
    _INDEX["at"] = 0.0


def _record_files(document_id: int) -> list[Path]:
    now = time.monotonic()
    if now - _INDEX["at"] > REFRESH_SECONDS:
        root = raw_data_dir() / "extracted"
        files: dict[int, list[tuple[float, Path]]] = {}
        if root.exists():
            for d in os.scandir(root):
                if not d.is_dir():
                    continue
                for f in os.scandir(d.path):
                    head = f.name.split("_", 1)[0]
                    if f.name.endswith(".json") and head.isdigit():
                        files.setdefault(int(head), []).append((f.stat().st_mtime, Path(f.path)))
        _INDEX.update(at=now, files={k: [p for _, p in sorted(v)] for k, v in files.items()})
    return _INDEX["files"].get(document_id, [])


def _read_text(path: Path) -> str:
    """Nội dung file kết quả; dùng lại bản đã đọc nếu vừa kiểm trong REFRESH_SECONDS hoặc file không đổi."""
    now = time.monotonic()
    cached = _TEXT.get(path)
    if cached and now - cached[0] <= REFRESH_SECONDS:
        return cached[3]
    st = path.stat()
    if cached and cached[1:3] == (st.st_mtime_ns, st.st_size):
        _TEXT[path] = (now, *cached[1:])
        return cached[3]
    text = path.read_text(encoding="utf-8")
    _TEXT[path] = (now, st.st_mtime_ns, st.st_size, text)
    return text


def _load_record(conn: psycopg.Connection, document_id: int) -> dict:
    files = _record_files(document_id)       # cũ -> mới theo thời điểm sửa
    if not files:
        # Chỉ mục có thể cũ (file mới ghi đè cùng thư mục chưa đổi thời điểm): tìm lại kiểu cũ
        files = sorted((raw_data_dir() / "extracted").glob(f"*/{document_id}_*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise RuntimeError(f"Tài liệu {document_id} chưa có kết quả trích xuất")
    record = json.loads(_read_text(files[-1]))
    if "company_template" not in record:
        record["company_template"] = conn.execute(
            "SELECT c.template FROM documents d JOIN companies c ON c.ticker = d.ticker WHERE d.id = %s",
            (document_id,),
        ).fetchone()[0]
    if "doc_type" not in record:
        record["doc_type"] = conn.execute("SELECT doc_type FROM documents WHERE id = %s", (document_id,)).fetchone()[0]
    return record


def recheck_document(conn: psycopg.Connection, document_id: int) -> dict:
    """Chuẩn hóa và kiểm tra lại từ kết quả mô hình đã lưu, không gọi mô hình (dùng khi sửa bộ ràng buộc)."""
    return _finalize(conn, _load_record(conn, document_id))


BALANCE_RULE = re.compile(r"_eq_440$|_ta_eq_tle$")   # tổng tài sản = tổng nguồn vốn, theo từng mẫu


def statements_of_rule(rule_id: str) -> str:
    """Báo cáo của một ràng buộc theo tiền tố id ("BS_270" -> "BS"); ràng buộc chéo trả về "X"."""
    prefix = rule_id.split("_", 1)[0]
    return prefix if prefix in ("BS", "IS", "CF") else "X"


def _finalize(conn: psycopg.Connection, record: dict) -> dict:
    """Bước 3-4: chuẩn hóa, kiểm tra ràng buộc, lưu file kết quả và ghi CSDL."""
    document_id, ticker, file_id, sha256 = record["document_id"], record["ticker"], record["file_id"], record["sha256"]
    company_template = record["company_template"]

    # 3. Chuẩn hóa và kiểm tra
    extracted, statements, sep, template, checks = _check(record)
    summary = summarize(checks)
    # Phải có ràng buộc bắt buộc trên cả BCĐKT và KQKD: trước đây BCĐKT bị chép sai cột mã số thì không ràng buộc
    # nào chạy được trên BCĐKT mà tài liệu vẫn "đạt" nhờ KQKD (GVR, VHM, VRE quý 2/2026)
    # và phải kiểm được tổng tài sản = tổng nguồn vốn: thiếu trang nguồn vốn (BSR quý 2/2026, bước định vị trang
    # bỏ sót trang 5) thì vẫn có ràng buộc BCĐKT đạt nhưng nửa bảng chưa được đọc
    covered = {statements_of_rule(c.rule_id) for c in checks if c.gate}
    balanced = any(c.gate and BALANCE_RULE.search(c.rule_id) for c in checks)
    summary["gate_statements"] = sorted(covered)
    summary["balance_checked"] = balanced
    if (template and summary["gate_checks"] and summary["gate_failed"] == 0 and {"BS", "IS"} <= covered
            and balanced):
        status = "verified"
    elif record.get("approval"):
        status = "approved"     # người duyệt đã đối chiếu ảnh gốc và cho xuất bản (verify.approve_document)
    else:
        status = "needs_review"
    record.update({
        "thousands_sep": sep, "template_ver": template, "status": status, "summary": summary,
        "duplicate_codes": {k: v.duplicate_codes for k, v in statements.items() if v.duplicate_codes},
        "rules_checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": [asdict(c) | {"diff": c.diff} for c in checks],
    })
    record.pop("output_path", None)
    if template is None:
        record["note"] = f"Chưa có bộ ràng buộc cho mẫu {company_template}"
    else:
        record.pop("note", None)            # ghi chú cũ từ lần chạy trước khi có bộ ràng buộc cho mẫu này

    out_path = raw_data_dir() / "extracted" / ticker / f"{document_id}_{sha256[:8]}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record, ensure_ascii=False, indent=1, default=_json_default), encoding="utf-8")
    _invalidate_index()
    _TEXT.pop(out_path, None)
    record["output_path"] = str(out_path)

    # 4. Ghi CSDL (chạy lại cùng phiên bản pipeline thì thay kết quả cũ)
    with conn.transaction():
        conn.execute("DELETE FROM line_items WHERE file_id = %s AND pipeline_ver = %s", (file_id, PIPELINE_VER))
        conn.execute("DELETE FROM validations WHERE file_id = %s AND pipeline_ver = %s", (file_id, PIPELINE_VER))
        for st in extracted:
            values = statements[st.statement].values if st.statement in statements else {}
            for it in st.items:
                code = normalize_code(it.code)
                for col, raw_value in it.values_raw.items():
                    if raw_value is None:
                        continue
                    value = values.get(code, {}).get(col) if code else None
                    conn.execute(
                        "INSERT INTO line_items (file_id, statement, code, label_raw, note_ref, column_kind, value,"
                        " value_raw, page, method, pipeline_ver)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'vlm', %s)",
                        (file_id, st.statement, code, it.label, it.note, col, value, raw_value, it.page, PIPELINE_VER),
                    )
        for c in checks:
            conn.execute(
                "INSERT INTO validations (file_id, rule_id, column_kind, passed, lhs, rhs, details, pipeline_ver)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (file_id, c.rule_id, c.column_kind, c.passed, c.lhs, c.rhs,
                 json.dumps({"gate": c.gate, "tolerance": str(c.tolerance), "missing": c.missing}), PIPELINE_VER),
            )
        conn.execute("UPDATE documents SET template_ver = %s, status = %s, processed_at = COALESCE(processed_at, now())"
                     " WHERE id = %s", (template, status, document_id))
    return record
