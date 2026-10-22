"""Đọc dữ liệu cho giao diện xem lại: danh sách BCTC, kết quả trích xuất, ảnh trang gốc."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from services.extraction.pipeline import _check, _read_text, _record_files, _rotation
from services.extraction.rules import BANK_INCOME_PARTS, RULESETS
from services.extraction.sources import candidates, open_pdf, render_page
from services.ingestion.registry import raw_data_dir
from services.extraction.evidence import CONFLICT_LABELS, STATUS_LABELS, cells_of, document_evidence
from services.metrics.canonical import code_for

COLUMNS = {
    "BS": [("end_period", "Cuối kỳ"), ("begin_year", "Đầu năm")],
    "IS": [("q_cur", "Quý này"), ("q_prev_year", "Cùng kỳ"), ("ytd_cur", "Lũy kế"), ("ytd_prev_year", "Lũy kế năm trước")],
    "CF": [("ytd_cur", "Lũy kế"), ("ytd_prev_year", "Lũy kế năm trước")],
}
PERIOD_KIND = {
    "bs_begin": "Số đầu năm khác với BCTC quý liền kề",
    "is_quarter": "Quý ≠ lũy kế kỳ này − lũy kế kỳ trước",
    "same_date": "Khác BCTC cùng ngày kết thúc kỳ (bán niên/năm)",
    "year_start": "Số đầu năm khác số cuối năm trước (BCTC quý 4)",
}
STATEMENT_NAMES = {"BS": "Cân đối kế toán", "IS": "Kết quả kinh doanh", "CF": "Lưu chuyển tiền tệ"}


def record_path(document_id: int) -> Path | None:
    files = _record_files(document_id)          # chỉ mục chung của pipeline, cũ -> mới
    return files[-1] if files else None


def load_record(document_id: int) -> dict | None:
    p = record_path(document_id)
    return json.loads(_read_text(p)) if p else None


def headline(record: dict) -> dict[str, Decimal | None]:
    """Doanh thu (ngân hàng: tổng thu nhập hoạt động) và LNST quý này, cùng kỳ. Đơn vị: đồng."""
    _, statements, _, template, _ = _check(record)
    out: dict[str, Decimal | None] = {}
    if not template or "IS" not in statements:
        return out
    is_values = statements["IS"].values
    rev_metric = "toi" if template == "TCTD" else "revenue"
    for key, metric in (("rev", rev_metric), ("npat", "npat")):
        code = code_for(template, "IS", metric)
        for col in ("q_cur", "q_prev_year"):
            out[f"{key}_{col}"] = is_values.get(code, {}).get(col) if code else None
            if out[f"{key}_{col}"] is None and metric == "toi" and "b.nii" in is_values:
                # Nhiều ngân hàng không in dòng tổng thu nhập hoạt động: cộng các khoản thu nhập thuần như ràng buộc IS_bank_ppop_parts
                out[f"{key}_{col}"] = sum((is_values.get(c, {}).get(col, Decimal(0)) for c in BANK_INCOME_PARTS),
                                          Decimal(0))
    return out


def _formula(template: str | None, rule_id: str) -> tuple[str, str | None, set[str]]:
    """(công thức dễ đọc, báo cáo, các mã liên quan) của một ràng buộc."""
    rs = RULESETS.get(template) if template else None
    if rs is None:
        return rule_id, None, set()
    for r in rs.rules:
        if r.id == rule_id:
            terms = " ".join(("+ " if s > 0 else "− ") + c for s, c in r.rhs).removeprefix("+ ")
            return f"[{r.lhs}] = {terms}", r.statement, {r.lhs, *(c for _, c in r.rhs)}
    for x in rs.cross_rules:
        if x.id == rule_id:
            (ls, lc, lcol), (rs_, rc, rcol) = x.left, x.right
            return f"{ls} [{lc}] {lcol} = {rs_} [{rc}] {rcol}", None, set()
    return rule_id, None, set()


def _printed(v: Decimal, mult: Decimal) -> str:
    """Số theo đơn vị in trên BCTC, dấu chấm ngăn nghìn như bảng."""
    p = v / mult
    s = f"{abs(p):,.0f}" if p == p.to_integral() else f"{abs(p):,.2f}"
    return ("−" if p < 0 else "") + s.replace(",", "X").replace(".", ",").replace("X", ".")


def _period_text(pc, mult: Decimal, period_of: dict[int, str]) -> str:
    """Một chỗ lệch giữa hai BCTC, viết cho người duyệt, số theo đơn vị in của BCTC đang xem."""
    later = period_of.get(pc.cells[0][0], "này")
    other = period_of.get(pc.cells[-1][0], "kia")
    f = lambda v: _printed(v, mult)        # noqa: E731
    if pc.kind == "is_quarter" and pc.base is not None:
        year = "năm trước" if pc.column == "q_prev_year" else "năm nay"
        return (f"Cột {year}: số quý phải bằng lũy kế {later} trừ lũy kế {other}, tức {f(pc.base)} − "
                f"{f(pc.base - pc.expected)} (BCTC {other}) = {f(pc.expected)}; BCTC {later} in {f(pc.later)}, "
                f"lệch {f(pc.diff)}")
    what = {"bs_begin": "Số đầu năm", "same_date": "Cùng ngày kết thúc kỳ",
            "year_start": "Số đầu năm (bằng cuối năm trước)"}.get(pc.kind, pc.kind)
    return f"{what}: BCTC {later} in {f(pc.later)}, BCTC {other} in {f(pc.expected)}, lệch {f(pc.diff)}"


def cell_reasons(evidence, template: str | None) -> dict[tuple[str, str, str], list[str]]:
    """Vì sao từng ô của tài liệu đang xem cần xem ảnh, bằng lời và có số."""
    if evidence is None:
        return {}
    cells = evidence.cells
    period_of = {cells.document_id: cells.period, **{d: p for d, p, _ in evidence.peers}}
    out: dict[tuple[str, str, str], list[str]] = {}
    for pc in evidence.period_checks:
        if not pc.suspect_misread:
            continue
        text = _period_text(pc, cells.multiplier.get(pc.statement, Decimal(1)), period_of)
        for d, st, key, col in pc.cells:
            if d == cells.document_id:
                out.setdefault((st, key, col), []).append(text)
    for cell, rules in cells.sum_conflicts.items():
        out.setdefault(cell, []).extend(f"Phép cộng không khớp: {_formula(template, r)[0]}" for r in rules)
    for cell, e in evidence.status.items():
        if "Q1: quý ≠ lũy kế" in e.get("conflict", []):
            out.setdefault(cell, []).append("Quý 1: số quý phải bằng số lũy kế nhưng hai cột in khác nhau")
    return out


def cell_label(e: dict) -> str:
    return CONFLICT_LABELS.get(e.get("reason"), STATUS_LABELS["conflict"]) if e["status"] == "conflict" \
        else STATUS_LABELS[e["status"]]


def evidence_chips(evidence) -> list[tuple[str, str, int]]:
    """(lớp màu, nhãn, số ô) cho dòng tóm tắt; ô cần xem ảnh tách theo lý do."""
    if evidence is None:
        return []
    out = []
    for k, v in evidence.counts().items():
        if k == "conflict":
            for reason, label in CONFLICT_LABELS.items():
                n = sum(1 for e in evidence.status.values() if e["status"] == "conflict" and e.get("reason") == reason)
                if n:
                    out.append(("conflict", label, n))
        elif v:
            out.append((k, STATUS_LABELS[k], v))
    return out


@dataclass
class Row:
    stt: str | None
    code: str | None
    label: str
    note: str | None
    page: int | None
    values: dict[str, str | None]
    flagged: bool
    evidence: dict[str, dict] = field(default_factory=dict)   # cột -> {"status", "sum", "period", "conflict"}
    index: int = 0            # vị trí dòng trong bản chép (để sửa tay: verify.apply_manual_fix)


def detail(record: dict, evidence=None) -> dict:
    """`evidence`: kết quả services.extraction.evidence.document_evidence của chính tài liệu này (có thể None)."""
    extracted, statements, sep, template, checks = _check(record)
    flagged: dict[str, set[str]] = {}
    check_rows = []
    for c in checks:
        formula, st, codes = _formula(template, c.rule_id)
        if c.gate and not c.passed and st:
            flagged.setdefault(st, set()).update(codes)
        check_rows.append({"rule_id": c.rule_id, "column": c.column_kind, "passed": c.passed, "gate": c.gate,
                           "formula": formula, "lhs": c.lhs, "rhs": c.rhs, "diff": c.diff, "missing": c.missing})
    check_rows.sort(key=lambda c: (c["passed"], not c["gate"], c["rule_id"]))

    chosen = next(c for c in record["candidates"] if c["name"] == record["chosen"])
    tables = []
    # Ô cần xem ảnh (phép cộng không khớp, lệch với BCTC kỳ khác, hai lần đọc ra hai số): người duyệt xem ảnh rồi bấm
    # "đúng như ảnh" hoặc sửa tay
    review = []
    reasons = cell_reasons(evidence, template)
    period_of = {d: p for d, p, _ in evidence.peers} if evidence else {}
    other_docs: dict[tuple, set[int]] = {}
    for pc in evidence.period_checks if evidence else []:
        if pc.suspect_misread and any(d == evidence.cells.document_id for d, *_ in pc.cells):
            for d, st, key, col in pc.cells:
                if d == evidence.cells.document_id:
                    other_docs.setdefault((st, key, col), set()).update(x for x, *_ in pc.cells if x != d)
    for st in extracted:
        keys = evidence.cells.item_keys.get(st.statement, []) if evidence else []
        rows = []
        for i, it in enumerate(st.items):
            key = keys[i] if i < len(keys) else None
            ev = {col: dict(evidence.status[(st.statement, key, col)]) for col in it.values_raw
                  if key and (st.statement, key, col) in evidence.status} if evidence else {}
            for col, e in ev.items():
                e["label"], e["why"] = cell_label(e), reasons.get((st.statement, key, col), [])
                if e["status"] == "second_differs":
                    e["why"] = [f"Lần đọc thứ hai (nhà cung cấp mô hình khác) ra {e.get('second_printed')}"]
                if e["status"] in ("conflict", "second_differs"):
                    review.append({"statement": st.statement, "name": STATEMENT_NAMES[st.statement],
                                   "key": key, "column": col, "column_name": dict(COLUMNS[st.statement]).get(col, col),
                                   "label": it.label, "value": it.values_raw.get(col), "kind": e["label"],
                                   "why": e["why"], "page": it.page, "index": i,
                                   "others": [(d, period_of.get(d, "")) for d in sorted(other_docs.get(
                                       (st.statement, key, col), ()))]})
            rows.append(Row(it.stt, it.code, it.label, it.note, it.page, it.values_raw,
                            bool(it.code) and it.code in flagged.get(st.statement, set()), ev, i))
        tables.append({"statement": st.statement, "name": STATEMENT_NAMES[st.statement], "unit": st.unit_raw,
                       "columns": COLUMNS[st.statement], "rows": rows,
                       "pages": chosen["statement_pages"].get(st.statement, [])})
    period_rows = []
    if evidence:
        for pc in evidence.period_checks:
            if not pc.passed:
                period_rows.append({"kind": PERIOD_KIND[pc.kind], "statement": pc.statement, "column": pc.column,
                                    "label": evidence.cells.labels.get((pc.statement, pc.key), pc.key),
                                    "key": pc.key, "value": pc.later, "expected": pc.expected, "diff": pc.diff,
                                    "restated": pc.restated, "suspect": pc.suspect_misread,
                                    "verdict": ("BCTC ghi trình bày lại" if pc.restated else
                                                "Cần xem lại" if pc.suspect_misread else
                                                "Đọc lại hoặc đối chiếu ảnh vẫn vậy: hai BCTC in khác nhau" if pc.verified else
                                                "Cộng tổng hai bên đều khớp: hai BCTC in khác nhau" if pc.consistent else
                                                "Chênh lớn, không phải dạng đọc sai: nhiều khả năng soát xét sửa số")})
    return {"template": template, "sep": sep, "tables": tables, "checks": check_rows, "period_conflicts": period_rows,
            "evidence_counts": evidence.counts() if evidence else None,
            "peers": evidence.peers if evidence else [],
            "missing": [m.describe() for m in evidence.missing] if evidence else [],
            "review": review, "evidence_chips": evidence_chips(evidence),
            "duplicate_codes": record.get("duplicate_codes") or {},
            "rereads": record.get("rereads", []), "reextracts": record.get("reextracts", []),
            "page_count": chosen["page_count"], "chosen": record["chosen"]}


@lru_cache(maxsize=8)
def _open(storage_key: str, member: str):
    for cand in candidates(raw_data_dir() / storage_key):
        if cand.name == member:
            return open_pdf(cand)
    raise FileNotFoundError(member)


@lru_cache(maxsize=256)
def page_png(storage_key: str, member: str, page: int, rotate: int, long_side: int = 1700) -> bytes:
    return render_page(_open(storage_key, member), page, long_side, rotate)


def page_image(record: dict, storage_key: str, page: int) -> bytes:
    return page_png(storage_key, record["chosen"], page, _rotation(record, page))


def page_etag(record: dict, storage_key: str, page: int) -> str:
    key = f"{storage_key}|{record['chosen']}|{page}|{_rotation(record, page)}"
    return '"' + hashlib.sha1(key.encode()).hexdigest()[:16] + '"'


def evidence(conn, document_id: int):
    """Bằng chứng từng ô (services.extraction.evidence); phần tốn thời gian (_check) đã được pipeline lưu tạm."""
    return document_evidence(conn, document_id, load=load_record)
