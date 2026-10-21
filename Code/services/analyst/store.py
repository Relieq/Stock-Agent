"""Đọc CSDL cho agent báo cáo: tìm BCTC đã kiểm chứng của (mã, kỳ), kỳ gần nhất, phần còn thiếu, nạp số một mã và cả
nhóm. Chỉ BCTC công khai (không dùng file người dùng tải lên riêng, không dùng bản trùng)."""

from __future__ import annotations

from dataclasses import asdict

from services.analyst import catalog
from services.analyst.facts import Group, Pair, TickerData, build_sheet, chart_specs
from services.analyst.plan import Plan, label
from services.extraction.evidence import document_evidence
from services.extraction.pipeline import _load_record, _record_files
from services.metrics.card import Facts, Value

HIDDEN = {"conflict", "second_differs"}       # ô "cần xem lại": không đưa vào báo cáo
GROUP_NAMES = {"TCTD": "các ngân hàng đang theo dõi", "CTCK": "các công ty chứng khoán đang theo dõi",
               "corporate": "các doanh nghiệp đang theo dõi (trừ ngân hàng, chứng khoán)"}
PERIOD_DOCS = {"H1": [("fs_semiannual", "H1"), ("fs_quarter", "Q2")], "FY": [("fs_annual", "FY"), ("fs_quarter", "Q4")]}


def find_document(conn, ticker: str, year: int, period: str) -> tuple[int, str] | None:
    """BCTC dùng cho (mã, kỳ): quý -> BCTC quý; bán niên -> BCTC bán niên, chưa có thì lũy kế ở BCTC quý 2; năm -> BCTC
    năm, chưa có thì lũy kế ở BCTC quý 4. Ưu tiên hợp nhất."""
    for doc_type, per in PERIOD_DOCS.get(period, [("fs_quarter", period)]):
        row = conn.execute(
            """SELECT id FROM documents WHERE ticker = %s AND fiscal_year = %s AND fiscal_period = %s AND doc_type = %s
                 AND content_kind = 'full' AND scope IN ('consolidated', 'standalone')
                 AND status IN ('verified', 'approved') AND NOT is_amended AND owner_user_id IS NULL
                 AND duplicate_of IS NULL
               ORDER BY (scope = 'consolidated') DESC, source_listed_at DESC LIMIT 1""",
            (ticker, year, per, doc_type)).fetchone()
        if row:
            return row[0], doc_type
    return None


def reading_period(period: str) -> str:
    """Kỳ BCTC quý cần đọc thêm khi thiếu: bán niên -> quý 2, năm -> quý 4 (đường đọc theo yêu cầu chỉ nhận quý)."""
    return {"H1": "Q2", "FY": "Q4"}.get(period, period)


def latest(conn, tickers: list[str]) -> tuple[int, str] | None:
    """Quý gần nhất mà mọi mã đều có BCTC đã kiểm chứng; không có quý chung thì quý mới nhất trong kho (phần thiếu sẽ được
    đề nghị đọc thêm)."""
    row = conn.execute(
        """SELECT fiscal_year, fiscal_period FROM documents
           WHERE ticker = ANY(%s) AND doc_type = 'fs_quarter' AND content_kind = 'full' AND status IN ('verified', 'approved')
             AND owner_user_id IS NULL AND duplicate_of IS NULL AND scope IN ('consolidated', 'standalone')
           GROUP BY 1, 2 HAVING count(DISTINCT ticker) = %s ORDER BY 1 DESC, 2 DESC LIMIT 1""",
        (tickers, len(tickers))).fetchone()
    if row is None:
        row = conn.execute(
            """SELECT fiscal_year, fiscal_period FROM documents WHERE doc_type = 'fs_quarter' AND content_kind = 'full'
                 AND status IN ('verified', 'approved') AND owner_user_id IS NULL
               ORDER BY 1 DESC, 2 DESC LIMIT 1""").fetchone()
    return (row[0], row[1]) if row else None


def missing(conn, plan: Plan) -> list[dict]:
    """(mã, kỳ) chưa có BCTC đã kiểm chứng. can_read: đọc thêm được (BCTC đang chờ duyệt tay thì không)."""
    out = []
    for t in plan.tickers:
        if find_document(conn, t, plan.year, plan.period) is not None:
            continue
        per = reading_period(plan.period)
        review = conn.execute(
            """SELECT 1 FROM documents WHERE ticker = %s AND fiscal_year = %s AND fiscal_period = %s
                 AND doc_type = 'fs_quarter' AND content_kind = 'full' AND status IN ('needs_review', 'extracting')
                 AND owner_user_id IS NULL LIMIT 1""", (t, plan.year, per)).fetchone()
        out.append({"ticker": t, "year": plan.year, "period": per, "can_read": review is None,
                    "note": "BCTC đang chờ duyệt tay" if review else ""})
    return out


def columns(doc_type: str, basis: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Cột kỳ này, cùng kỳ (thử lần lượt). BCTC bán niên/năm in một cặp cột cả kỳ, có khi chép vào q_*."""
    if doc_type != "fs_quarter" or basis == "ytd":
        return ("ytd_cur", "q_cur"), ("ytd_prev_year", "q_prev_year")
    return ("q_cur",), ("q_prev_year",)


def _first(f: Facts, key: str, cols: tuple[str, ...], hidden: set[tuple[str, str, str]]) -> Value:
    for col in cols:
        v = f.metric("IS", key, col)
        if v.value is None:
            continue
        if v.source is not None and ("IS", v.source.code, col) in hidden:
            return Value(None)
        return v
    return Value(None)


def load_ticker(conn, ticker: str, year: int, period: str, basis: str, with_flags: bool = True) -> TickerData | None:
    found = find_document(conn, ticker, year, period)
    if found is None:
        return None
    doc_id, doc_type = found
    record = _load_record(conn, doc_id)
    ev = document_evidence(conn, doc_id)
    f = Facts(doc_id, record, {(m.statement, m.key) for m in ev.missing} if ev else None)
    kind = catalog.KIND_OF_TEMPLATE.get(f.template)
    if kind is None:
        return None
    hidden = {k for k, v in (ev.status.items() if ev else []) if v["status"] in HIDDEN}
    cur_cols, prev_cols = columns(doc_type, basis)
    values = {}
    for key in catalog.METRICS[kind]:
        cur, prev = _first(f, key, cur_cols, hidden), _first(f, key, prev_cols, hidden)
        values[key] = Pair(cur.value, prev.value, [asdict(s) for s in (cur.source, prev.source) if s is not None])
    flags: list[tuple[str, str]] = []
    if with_flags and doc_type == "fs_quarter":
        from services.metrics.service import card_for
        got = card_for(conn, doc_id)
        if got is not None:
            flags = [(fl.title, fl.detail) for fl in got[0].flags]
    return TickerData(ticker, kind, label(year, period, basis), values, flags, doc_id)


def load_group(conn, kind: str, year: int, period: str, basis: str) -> Group:
    company = {v: k for k, v in catalog.KIND_OF_COMPANY.items()}[kind]
    tickers = [t for (t,) in conn.execute(
        "SELECT ticker FROM companies WHERE tracked AND template = %s ORDER BY ticker", (company,))]
    members = [d for t in tickers if (d := load_ticker(conn, t, year, period, basis, with_flags=False)) is not None]
    return Group(GROUP_NAMES[kind], members)


def record_version(doc_id: int) -> str:
    """Phiên bản kết quả trích xuất (file mới nhất và thời điểm sửa): sửa tay một ô thì phiên bản đổi."""
    files = _record_files(doc_id)
    if not files:
        return ""
    p = files[-1]
    return f"{p.name}:{p.stat().st_mtime_ns}"


def sheet_for_plan(conn, plan: Plan):
    """(bảng số, BCTC nguồn kèm phiên bản, ghi chú, đặc tả biểu đồ)."""
    data, notes = [], []
    for t in plan.tickers:
        d = load_ticker(conn, t, plan.year, plan.period, plan.basis)
        if d is None:
            notes.append(f"Chưa có BCTC đã kiểm chứng của {t} cho {plan.label()}: báo cáo không có số của mã này.")
            continue
        data.append(d)
    groups = {k: load_group(conn, k, plan.year, plan.period, plan.basis) for k in {d.kind for d in data}} \
        if plan.kind == "rank" else {}
    sheet = build_sheet(plan.kind, data, plan.metrics, groups)
    docs = sorted({d.document_id for d in data} | {m.document_id for g in groups.values() for m in g.members})
    sources = [{"document_id": i, "version": record_version(i)} for i in docs]
    return sheet, sources, notes, chart_specs(plan.kind, data, plan.metrics, groups)
