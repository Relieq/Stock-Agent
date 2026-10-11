"""Pipeline đọc và kiểm chứng một BCTC: chọn PDF -> định vị trang -> chép bảng -> chuẩn hóa -> kiểm tra ràng buộc.

Kết quả lưu vào:
  * Data/raw/extracted/<ticker>/<document_id>_<sha8>.json: toàn bộ đầu vào/đầu ra của mô hình, để xem lại và chấm điểm;
  * bảng line_items, validations; documents.template_ver và documents.status.

Phiên bản này chưa có bước đọc lại khi số liệu lệch (architecture.md mục 4.3); dòng lệch được ghi lại trong
validations để làm bước đó sau.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg

from services.extraction import prompts
from services.extraction.bank import canonicalize
from services.extraction.numbers import normalize_code, parse_amount
from services.extraction.sources import candidates, open_pdf, render_page
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

    _escalate(record, client, doc)
    record["usage"] = {k: v - usage_before[k] for k, v in asdict(client.usage).items()}
    return _finalize(conn, record)


REREAD_ROUNDS = 1
REREAD_LONG_SIDE = 3000
REEXTRACT_LONG_SIDE = 2600


def _escalate(record: dict, client: VisionClient, doc) -> None:
    """Thang leo thang khi ràng buộc bắt buộc bị lệch (architecture.md mục 4.3):
    1. đọc lại đúng các ô liên quan ở độ phân giải cao hơn;
    2. vẫn lệch thì chép lại cả báo cáo đó, mỗi trang một lần gọi (sửa lỗi bỏ sót dòng), giữ bản ít lệch hơn,
       rồi đọc lại ô thêm một lần.
    Trước đó: BCĐKT chưa kiểm được tổng tài sản = tổng nguồn vốn thì chép thêm trang kế tiếp (bước định vị trang có
    thể bỏ sót trang nguồn vốn). Bậc dùng mô hình mạnh hơn và duyệt tay chưa làm."""
    _extend_balance_sheet(record, client, doc)
    for _ in range(REREAD_ROUNDS):
        if not _reread_failed(record, client, doc):
            break
    if _reextract_failed_statements(record, client, doc):
        _reread_failed(record, client, doc)


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
    image = render_page(doc, page, EXTRACT_LONG_SIDE, _rotation(record, page))
    extra = client.json_from_images(prompts.extract_prompt("BS"), [(f"Trang {page}", image)],
                                    prompts.extract_schema("BS"), "statement_BS")
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
    failures = _gate_failures(record)
    if not failures:
        return False
    chosen = next(c for c in record["candidates"] if c["name"] == record["chosen"])
    st_pages = {k: [int(x) for x in v] for k, v in chosen["statement_pages"].items()}
    log = record.setdefault("reextracts", [])
    improved = False
    for st, n_failed in failures.items():
        pages = st_pages.get(st, [])
        if not pages:
            continue
        parts = []
        for page in pages:
            image = render_page(doc, page, REEXTRACT_LONG_SIDE, _rotation(record, page))
            parts.append(client.json_from_images(prompts.extract_prompt(st), [(f"Trang {page}", image)],
                                                 prompts.extract_schema(st), f"statement_{st}"))
        merged = {
            "unit_text": next((x["unit_text"] for x in parts if x.get("unit_text")), None),
            "columns": parts[0].get("columns", []),
            "rows": [r for x in parts for r in x.get("rows", [])],
        }
        before = record["raw"][st]
        passed_before = _gate_tally(record).get(st, (0, 0))[1]
        record["raw"][st] = merged
        after_failed, passed_after = _gate_tally(record).get(st, (0, 0))
        # Ít lệch hơn chưa đủ: bản chép lại có thể mất mã số hoặc mất dòng nên ít ràng buộc chạy được hơn
        # (TCX quý 2/2026: lệch 2 -> 0 nhưng số ràng buộc KQKD chạy được giảm từ 28 xuống 12)
        kept = after_failed < n_failed and passed_after >= passed_before
        if not kept:
            record["raw"][st] = before
        else:
            improved = True
        log.append({"statement": st, "pages": pages, "failed_before": n_failed, "failed_after": after_failed,
                    "rows_before": len(before.get("rows", [])), "rows_after": len(merged["rows"]),
                    "kept": kept, "model": client.cfg.model})
    return improved


def _rotation(record: dict, page: int) -> int:
    """Số độ cần xoay trang (theo kết quả định vị trang). Khóa có thể là số hoặc chuỗi sau khi đọc lại từ JSON."""
    chosen = next(c for c in record["candidates"] if c["name"] == record["chosen"])
    rotations = chosen.get("rotations", {})
    return int(rotations.get(page, rotations.get(str(page), 0)))


def _check(record: dict):
    extracted, statements, sep, template, checks = _check_variants(record)
    inferred = _infer_missing_codes(extracted, statements, sep, template, checks) if template else []
    record["codes_inferred"] = inferred
    if inferred:
        statements, sep = normalize(extracted)
        checks = validate(statements, template)
    return extracted, statements, sep, template, checks


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

    def evaluate(swapped: frozenset):
        raws = {st: _swap_stt_code(raw, {p for s_, p in swapped if s_ == st}) for st, raw in record["raw"].items()}
        extracted = [_to_extracted(st, raw) for st, raw in raws.items()]
        statements, sep = normalize(extracted)
        template = fixed_template or detect_template(statements)
        checks = validate(statements, template) if template else []
        failed = sum(c.gate and not c.passed for c in checks)
        passed = sum(c.gate and c.passed for c in checks)
        return (template is None, failed, -passed, len(swapped)), (extracted, statements, sep, template, checks)

    # Thử đảo cả báo cáo trước (tổng tài sản cần cả trang 100 lẫn trang 200 cùng đúng), rồi bật/tắt từng trang
    units = {st: [(st, page) for page in _pages_with_code_like_stt(raw)] for st, raw in record["raw"].items()}
    swapped: frozenset = frozenset()
    best_score, best = evaluate(swapped)
    moves = [frozenset(u) for u in units.values() if u] + [frozenset([u]) for us in units.values() for u in us]
    for move in moves:
        candidate = swapped ^ move
        score, result = evaluate(candidate)
        if score < best_score:
            swapped, best_score, best = candidate, score, result
    record["stt_code_swapped"] = sorted(f"{st}@{p}" for st, p in swapped)
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


def _swap_stt_code(raw: dict, pages: set) -> dict:
    if not pages:
        return raw
    return raw | {"rows": [r | {"stt": r.get("code"), "code": r.get("stt")} if r.get("page") in pages else r
                           for r in raw.get("rows", [])]}


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
    _escalate(record, client, doc)
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
        conn.execute("UPDATE documents SET template_ver = %s, status = %s, processed_at = COALESCE(processed_at, now())"
                     " WHERE id = %s", (template, status, document_id))
    return record
