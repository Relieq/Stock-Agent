"""Đọc CSDL cho agent báo cáo: tìm BCTC đã kiểm chứng của (mã, kỳ), kỳ gần nhất, phần còn thiếu, nạp số một mã và cả
nhóm. Chỉ BCTC công khai (không dùng file người dùng tải lên riêng, không dùng bản trùng)."""

from __future__ import annotations

from dataclasses import asdict

from services.analyst import catalog
from services.analyst.facts import (GROUP_LABELS, SCREEN_ORDER, Group, Pair, TickerData, build_screen, build_sheet,
                                    chart_specs, screen_charts)
from services.analyst.plan import Plan, label
from services.extraction.evidence import document_evidence
from services.extraction.pipeline import _load_record, _record_files
from services.extraction.rules import BANK_INCOME_PARTS
from services.metrics.card import Facts, Value

HIDDEN = {"conflict", "second_differs"}       # ô "cần xem lại": không đưa vào báo cáo
GROUP_NAMES = {"TCTD": "các ngân hàng đang theo dõi", "CTCK": "các công ty chứng khoán đang theo dõi",
               "corporate": "các doanh nghiệp đang theo dõi (trừ ngân hàng, chứng khoán)"}
PERIOD_DOCS = {"H1": [("fs_semiannual", "H1"), ("fs_quarter", "Q2")], "FY": [("fs_annual", "FY"), ("fs_quarter", "Q4")]}


def _find(conn, ticker: str, year: int, period: str) -> tuple[int, str, str] | None:
    """(mã tài liệu, loại, kỳ của tài liệu): kỳ của tài liệu khác kỳ hỏi khi lấy lũy kế ở BCTC quý (bán niên -> Q2)."""
    for doc_type, per in PERIOD_DOCS.get(period, [("fs_quarter", period)]):
        row = conn.execute(
            """SELECT id FROM documents WHERE ticker = %s AND fiscal_year = %s AND fiscal_period = %s AND doc_type = %s
                 AND content_kind = 'full' AND scope IN ('consolidated', 'standalone')
                 AND status IN ('verified', 'approved') AND NOT is_amended AND owner_user_id IS NULL
                 AND duplicate_of IS NULL
               ORDER BY (scope = 'consolidated') DESC, source_listed_at DESC NULLS LAST LIMIT 1""",
            (ticker, year, per, doc_type)).fetchone()
        if row:
            return row[0], doc_type, per
    return None


def find_document(conn, ticker: str, year: int, period: str) -> tuple[int, str] | None:
    """BCTC dùng cho (mã, kỳ): quý -> BCTC quý; bán niên -> BCTC bán niên, chưa có thì lũy kế ở BCTC quý 2; năm -> BCTC
    năm, chưa có thì lũy kế ở BCTC quý 4. Ưu tiên hợp nhất."""
    found = _find(conn, ticker, year, period)
    return (found[0], found[1]) if found else None


def reading_period(period: str) -> str:
    """Kỳ BCTC quý cần đọc thêm khi thiếu: bán niên -> quý 2, năm -> quý 4 (đường đọc theo yêu cầu chỉ nhận quý)."""
    return {"H1": "Q2", "FY": "Q4"}.get(period, period)


def latest(conn, tickers: list[str]) -> tuple[int, str] | None:
    """Quý gần nhất mà mọi mã đều có BCTC đã kiểm chứng; không có quý chung thì quý mới nhất của các mã được hỏi (phần
    thiếu sẽ được đề nghị đọc thêm); không mã nào có thì None."""
    base = """SELECT fiscal_year, fiscal_period FROM documents
              WHERE ticker = ANY(%s) AND doc_type = 'fs_quarter' AND content_kind = 'full'
                AND status IN ('verified', 'approved') AND owner_user_id IS NULL AND duplicate_of IS NULL
                AND NOT is_amended AND scope IN ('consolidated', 'standalone')"""
    row = conn.execute(base + " GROUP BY 1, 2 HAVING count(DISTINCT ticker) = %s ORDER BY 1 DESC, 2 DESC LIMIT 1",
                       (tickers, len(tickers))).fetchone()
    if row is None:
        row = conn.execute(base + " ORDER BY 1 DESC, 2 DESC LIMIT 1", (tickers,)).fetchone()
    return (row[0], row[1]) if row else None


COVERAGE = 2 / 3      # loại screen: quý "gần nhất" là quý mà ít nhất chừng này phần các mã đang theo dõi đã có số


def sector_kinds(sector: str) -> list[str]:
    return list(SCREEN_ORDER) if sector == "all" else [sector]


def tracked(conn, kinds: list[str]) -> list[str]:
    company = [{v: k for k, v in catalog.KIND_OF_COMPANY.items()}[k] for k in kinds]
    return [t for (t,) in conn.execute("SELECT ticker FROM companies WHERE tracked AND template = ANY(%s) ORDER BY ticker",
                                       (company,))]


def latest_all(conn, sector: str) -> tuple[int, str] | None:
    """Quý gần nhất mà ít nhất 2/3 số mã đang theo dõi của nhóm đã có BCTC kiểm chứng (đầu mùa BCTC mới có vài mã thì
    vẫn xếp theo quý trước)."""
    tickers = tracked(conn, sector_kinds(sector))
    if not tickers:
        return None
    row = conn.execute(
        """SELECT fiscal_year, fiscal_period FROM documents
           WHERE ticker = ANY(%s) AND doc_type = 'fs_quarter' AND content_kind = 'full'
             AND status IN ('verified', 'approved') AND owner_user_id IS NULL AND duplicate_of IS NULL
             AND NOT is_amended AND scope IN ('consolidated', 'standalone')
           GROUP BY 1, 2 HAVING count(DISTINCT ticker) >= %s ORDER BY 1 DESC, 2 DESC LIMIT 1""",
        (tickers, max(1, -(-len(tickers) * 2 // 3)))).fetchone()
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


def columns(doc_type: str, doc_period: str, basis: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Cột kỳ này, cùng kỳ (thử lần lượt). BCTC bán niên/năm in một cặp cột cả kỳ, có khi chép vào q_*; BCTC quý 1 thì quý
    cũng là lũy kế. BCTC quý 2-4 lấy lũy kế: chỉ cột ytd_*, không lấy số quý thay vào."""
    if basis != "ytd":
        return ("q_cur",), ("q_prev_year",)
    if doc_type != "fs_quarter" or doc_period == "Q1":
        return ("ytd_cur", "q_cur"), ("ytd_prev_year", "q_prev_year")
    return ("ytd_cur",), ("ytd_prev_year",)


def _derived_inputs(f: Facts, key: str) -> list[str]:
    """Mã các dòng mà số tính (không có nguồn riêng) của chỉ tiêu này được cộng/trừ từ đó."""
    if key == "toi":
        return list(BANK_INCOME_PARTS)
    if key == "npat_parent":
        return [c for c in (f.code("IS", "npat"), f.code("IS", "minority")) if c]
    return []


PARENT_PROFIT_FLAGS = {"sign_change", "low_base"}    # cờ thẻ tính trên LNST mẹ riêng quý (kỳ này, cùng kỳ)


def visible_flags(flags, f: Facts, hidden: set[tuple[str, str, str]]) -> list[tuple[str, str]]:
    """(tên cờ, chi tiết) của các cờ thẻ KQKD không dựa trên ô "cần xem lại": bỏ cờ có ô nguồn bị ẩn, và bỏ cờ tính trên
    LNST mẹ khi số đó là số tính (NPAT − cổ đông không kiểm soát, không có nguồn riêng) từ một ô bị ẩn."""
    derived_hidden = any(
        (v := f.metric("IS", "npat_parent", col)).value is not None and v.source is None
        and any(("IS", c, col) in hidden for c in _derived_inputs(f, "npat_parent"))
        for col in ("q_cur", "q_prev_year"))
    return [(fl.title, fl.detail) for fl in flags
            if not any((s.statement, s.code, s.column) in hidden for s in fl.sources)
            and not (derived_hidden and fl.key in PARENT_PROFIT_FLAGS)]


def _first(f: Facts, key: str, cols: tuple[str, ...], hidden: set[tuple[str, str, str]]) -> Value:
    for col in cols:
        v = f.metric("IS", key, col)
        if v.value is None:
            continue
        if v.source is not None and ("IS", v.source.code, col) in hidden:
            return Value(None)
        if v.source is None and any(("IS", c, col) in hidden for c in _derived_inputs(f, key)):
            return Value(None)      # số tính từ ô "cần xem lại" cũng ẩn
        return v
    return Value(None)


def _load(conn, ticker: str, year: int, period: str, basis: str, with_flags: bool, extra: tuple[str, ...] = ()):
    """(số của mã, lý do không có): lý do là "document" (chưa có BCTC), "record" (chưa có kết quả đọc) hoặc "template"
    (mẫu BCTC chưa hỗ trợ, như bảo hiểm)."""
    found = _find(conn, ticker, year, period)
    if found is None:
        return None, "document"
    doc_id, doc_type, doc_period = found
    try:
        record = _load_record(conn, doc_id)
    except RuntimeError:
        return None, "record"
    ev = document_evidence(conn, doc_id)
    f = Facts(doc_id, record, {(m.statement, m.key) for m in ev.missing} if ev else None)
    kind = catalog.KIND_OF_TEMPLATE.get(f.template)
    if kind is None:
        return None, "template"
    hidden = {k for k, v in (ev.status.items() if ev else []) if v["status"] in HIDDEN}
    cur_cols, prev_cols = columns(doc_type, doc_period, basis)
    values = {}
    for key in list(catalog.METRICS[kind]) + list(extra):      # extra: chỉ tiêu chuẩn ngoài danh mục (phép đo)
        cur, prev = _first(f, key, cur_cols, hidden), _first(f, key, prev_cols, hidden)
        values[key] = Pair(cur.value, prev.value, [asdict(s) for s in (cur.source, prev.source) if s is not None])
    flags: list[tuple[str, str]] = []
    if with_flags and doc_type == "fs_quarter" and basis == "quarter":
        from services.metrics.service import card_for
        got = card_for(conn, doc_id)
        if got is not None:
            flags = visible_flags(got[0].flags, f, hidden)
    return TickerData(ticker, kind, label(year, period, basis), values, flags, doc_id), None


def load_ticker(conn, ticker: str, year: int, period: str, basis: str, with_flags: bool = True,
                extra: tuple[str, ...] = ()) -> TickerData | None:
    return _load(conn, ticker, year, period, basis, with_flags, extra)[0]


def load_group(conn, kind: str, year: int, period: str, basis: str, with_flags: bool = False) -> Group:
    members = [d for t in tracked(conn, [kind]) if (d := load_ticker(conn, t, year, period, basis, with_flags))
               is not None]
    return Group(GROUP_NAMES[kind], members)


def record_version(doc_id: int) -> str:
    """Phiên bản kết quả trích xuất (file mới nhất và thời điểm sửa): sửa tay một ô thì phiên bản đổi."""
    files = _record_files(doc_id)
    if not files:
        return ""
    p = files[-1]
    return f"{p.name}:{p.stat().st_mtime_ns}"


def _sources(docs) -> list[dict]:
    return [{"document_id": i, "version": record_version(i)} for i in sorted(docs)]


def screen_sheet(conn, plan: Plan):
    """Câu hỏi "mã nào tốt nhất": nạp mọi mã đang theo dõi của từng nhóm (kèm cờ thẻ KQKD), xếp riêng từng nhóm."""
    groups, notes = {}, []
    for k in sector_kinds(plan.sector):
        g = load_group(conn, k, plan.year, plan.period, plan.basis, with_flags=True)
        n = len(tracked(conn, [k]))
        if len(g.members) < n:
            have = {m.ticker for m in g.members}
            notes.append(f"{GROUP_LABELS[k].capitalize()}: {len(g.members)}/{n} mã đã có BCTC kiểm chứng cho "
                         f"{plan.label()}; chưa có: {', '.join(t for t in tracked(conn, [k]) if t not in have)}.")
        if g.members:
            groups[k] = g
    sheet, more, tops = build_screen(groups, plan.metrics, plan.measure)
    docs = {m.document_id for g in groups.values() for m in g.members}
    return sheet, _sources(docs), notes + more, screen_charts(groups, plan.metrics, plan.measure, tops)


def sheet_for_plan(conn, plan: Plan):
    """(bảng số, BCTC nguồn kèm phiên bản, ghi chú, đặc tả biểu đồ)."""
    if plan.kind == "screen":
        return screen_sheet(conn, plan)
    data, notes = [], []
    for t in plan.tickers:
        d, why = _load(conn, t, plan.year, plan.period, plan.basis, True)
        if d is None:
            notes.append(f"Chưa hỗ trợ mẫu BCTC của {t} (bảo hiểm): báo cáo không có số của mã này." if why == "template"
                         else f"Chưa có BCTC đã kiểm chứng của {t} cho {plan.label()}: báo cáo không có số của mã này.")
            continue
        data.append(d)
    groups = {k: load_group(conn, k, plan.year, plan.period, plan.basis) for k in {d.kind for d in data}} \
        if plan.kind == "rank" else {}
    sheet = build_sheet(plan.kind, data, plan.metrics, groups)
    docs = {d.document_id for d in data} | {m.document_id for g in groups.values() for m in g.members}
    return sheet, _sources(docs), notes, chart_specs(plan.kind, data, plan.metrics, groups)
