"""Pipeline đọc và kiểm chứng một BCTC: chọn PDF -> định vị trang -> chép bảng -> chuẩn hóa -> kiểm tra ràng buộc.

Kết quả lưu vào:
  * Data/raw/extracted/<ticker>/<document_id>_<sha8>.json: toàn bộ đầu vào/đầu ra của mô hình, để xem lại và chấm điểm;
  * bảng line_items, validations; documents.template_ver và documents.status.

Phiên bản này chưa có bước đọc lại khi số liệu lệch (architecture.md mục 4.3); dòng lệch được ghi lại trong
validations để làm bước đó sau.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg

from services.extraction import prompts
from services.extraction.numbers import normalize_code
from services.extraction.sources import candidates, open_pdf, render_page
from services.extraction.rules import RULESETS
from services.extraction.validate import (
    ExtractedItem,
    ExtractedStatement,
    detect_template,
    normalize,
    summarize,
    validate,
)
from services.ingestion.registry import raw_data_dir
from services.llm import VisionClient

PIPELINE_VER = "0.1.0"
LOCATE_MAX_PAGES = 30
LOCATE_LONG_SIDE = 900
EXTRACT_LONG_SIDE = 2000


def _locate(client: VisionClient, doc, max_pages: int) -> list[dict]:
    n = min(doc.page_count, max_pages)
    images = [(f"Trang {p}", render_page(doc, p, LOCATE_LONG_SIDE)) for p in range(1, n + 1)]
    result = client.json_from_images(prompts.LOCATE_PROMPT, images, prompts.LOCATE_SCHEMA, "page_classification")
    return sorted(result["pages"], key=lambda x: x["page"])


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
                          note=r.get("note"), page=r.get("page"))
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
        SELECT d.ticker, d.title_raw, c.template, f.id, f.sha256, f.storage_key
        FROM documents d JOIN companies c ON c.ticker = d.ticker
        JOIN document_files f ON f.document_id = d.id
        WHERE d.id = %s ORDER BY f.downloaded_at DESC LIMIT 1
        """,
        (document_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Tài liệu {document_id} chưa có file đã tải")
    ticker, title, company_template, file_id, sha256, storage_key = row
    path = raw_data_dir() / storage_key

    usage_before = asdict(client.usage)   # client dùng chung cho nhiều tài liệu: chỉ tính phần của tài liệu này
    record: dict = {
        "document_id": document_id, "ticker": ticker, "title": title, "file_id": file_id, "sha256": sha256,
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
        images = [(f"Trang {p}", render_page(doc, p, EXTRACT_LONG_SIDE, _rotation(record, p))) for p in pages]
        raw = client.json_from_images(prompts.extract_prompt(st), images, prompts.extract_schema(st), f"statement_{st}")
        record["raw"][st] = raw
    record["company_template"] = company_template

    # 2b. Đọc lại các ô nằm trong ràng buộc bắt buộc bị lệch (architecture.md mục 4.3, bậc 1)
    for _ in range(REREAD_ROUNDS):
        if not _reread_failed(record, client, doc):
            break
    record["usage"] = {k: v - usage_before[k] for k, v in asdict(client.usage).items()}
    return _finalize(conn, record)


REREAD_ROUNDS = 1
REREAD_LONG_SIDE = 3000


def _rotation(record: dict, page: int) -> int:
    """Số độ cần xoay trang (theo kết quả định vị trang). Khóa có thể là số hoặc chuỗi sau khi đọc lại từ JSON."""
    chosen = next(c for c in record["candidates"] if c["name"] == record["chosen"])
    rotations = chosen.get("rotations", {})
    return int(rotations.get(page, rotations.get(str(page), 0)))


def _check(record: dict):
    extracted = [_to_extracted(st, raw) for st, raw in record["raw"].items()]
    statements, sep = normalize(extracted)
    template = detect_template(statements) if record["company_template"] == "corporate" else None
    checks = validate(statements, template) if template else []
    return extracted, statements, sep, template, checks


def _reread_failed(record: dict, client: VisionClient, doc) -> bool:
    """Đọc lại các ô thuộc ràng buộc bắt buộc bị lệch. Trả về True nếu có ô được đọc ra khác lần trước."""
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
        image = render_page(doc, page, REREAD_LONG_SIDE, _rotation(record, page))
        result = client.json_from_images(prompts.reread_prompt(st, cells), [(f"Trang {page}", image)],
                                         prompts.REREAD_SCHEMA, "reread_cells")
        for cell in result.get("cells", []):
            code, col, value = normalize_code(cell.get("code")), cell.get("column_kind"), cell.get("value")
            row = next((r for r in record["raw"][st]["rows"] if normalize_code(r.get("code")) == code), None)
            if row is None or col not in row["values"] or value is None:
                continue
            before = row["values"][col]
            log.append({"statement": st, "code": code, "column_kind": col, "page": page,
                        "before": before, "after": value, "model": client.cfg.model})
            if value != before:
                row["values"][col] = value
                changed = True
    return changed


def reread_document(conn: psycopg.Connection, document_id: int, client: VisionClient) -> dict:
    """Đọc lại các ô bị lệch cho một tài liệu đã trích xuất (không chép lại cả bảng)."""
    record = _load_record(conn, document_id)
    path = raw_data_dir() / conn.execute(
        "SELECT storage_key FROM document_files WHERE id = %s", (record["file_id"],)).fetchone()[0]
    cand = next(c for c in candidates(path) if c.name == record["chosen"])
    doc = open_pdf(cand)
    usage_before = asdict(client.usage)
    for _ in range(REREAD_ROUNDS):
        if not _reread_failed(record, client, doc):
            break
    usage = record.get("usage") or {}
    for k, v in asdict(client.usage).items():
        usage[k] = usage.get(k, 0) + v - usage_before[k]
    record["usage"] = usage
    return _finalize(conn, record)


def _load_record(conn: psycopg.Connection, document_id: int) -> dict:
    files = sorted((raw_data_dir() / "extracted").glob(f"*/{document_id}_*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise RuntimeError(f"Tài liệu {document_id} chưa có kết quả trích xuất")
    record = json.loads(files[-1].read_text(encoding="utf-8"))
    if "company_template" not in record:
        record["company_template"] = conn.execute(
            "SELECT c.template FROM documents d JOIN companies c ON c.ticker = d.ticker WHERE d.id = %s",
            (document_id,),
        ).fetchone()[0]
    return record


def recheck_document(conn: psycopg.Connection, document_id: int) -> dict:
    """Chuẩn hóa và kiểm tra lại từ kết quả mô hình đã lưu, không gọi mô hình (dùng khi sửa bộ ràng buộc)."""
    return _finalize(conn, _load_record(conn, document_id))


def _finalize(conn: psycopg.Connection, record: dict) -> dict:
    """Bước 3-4: chuẩn hóa, kiểm tra ràng buộc, lưu file kết quả và ghi CSDL."""
    document_id, ticker, file_id, sha256 = record["document_id"], record["ticker"], record["file_id"], record["sha256"]
    company_template = record["company_template"]

    # 3. Chuẩn hóa và kiểm tra
    extracted, statements, sep, template, checks = _check(record)
    summary = summarize(checks)
    if template and summary["gate_checks"] and summary["gate_failed"] == 0:
        status = "verified"
    else:
        status = "needs_review"
    record.update({
        "thousands_sep": sep, "template_ver": template, "status": status, "summary": summary,
        "duplicate_codes": {k: v.duplicate_codes for k, v in statements.items() if v.duplicate_codes},
        "rules_checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": [asdict(c) | {"diff": c.diff} for c in checks],
    })
    record.pop("output_path", None)
    if company_template != "corporate":
        record["note"] = f"Chưa có bộ ràng buộc cho mẫu {company_template}"

    out_path = raw_data_dir() / "extracted" / ticker / f"{document_id}_{sha256[:8]}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record, ensure_ascii=False, indent=1, default=_json_default), encoding="utf-8")
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
        conn.execute("UPDATE documents SET template_ver = %s, status = %s WHERE id = %s", (template, status, document_id))
    return record
