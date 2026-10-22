"""Đọc CSDL cho agent báo cáo: tìm BCTC đã kiểm chứng của (mã, kỳ), kỳ gần nhất, phần còn thiếu, nạp số một mã và cả
nhóm. Chỉ BCTC công khai (không dùng file người dùng tải lên riêng, không dùng bản trùng)."""

from __future__ import annotations

import re
from dataclasses import asdict
from decimal import Decimal

from services.analyst import catalog, ratios
from services.analyst.facts import (GROUP_LABELS, SCREEN_ORDER, Group, Pair, TickerData, build_screen, build_sheet,
                                    build_trend, chart_specs, screen_charts, trend_charts, trend_fact)
from services.analyst.plan import Plan, label
from services.analyst.sheet import Fact, FactSheet
from services.analyst.trend import DEFAULT_QUARTERS, qlabel, quarters_back
from services.extraction.bank import clean_label, fold
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


def trend_window(plan: Plan) -> list[tuple[int, int]]:
    """Các quý của câu hỏi xu hướng, từ cũ đến mới, kết thúc ở quý của kế hoạch."""
    return quarters_back(plan.year, plan.period, plan.quarters or DEFAULT_QUARTERS)


def _missing_one(conn, ticker: str, year: int, period: str) -> dict | None:
    if find_document(conn, ticker, year, period) is not None:
        return None
    per = reading_period(period)
    review = conn.execute(
        """SELECT 1 FROM documents WHERE ticker = %s AND fiscal_year = %s AND fiscal_period = %s
             AND doc_type = 'fs_quarter' AND content_kind = 'full' AND status IN ('needs_review', 'extracting')
             AND owner_user_id IS NULL LIMIT 1""", (ticker, year, per)).fetchone()
    return {"ticker": ticker, "year": year, "period": per, "can_read": review is None,
            "note": "BCTC đang chờ duyệt tay" if review else ""}


def missing(conn, plan: Plan) -> list[dict]:
    """(mã, kỳ) chưa có BCTC đã kiểm chứng. can_read: đọc thêm được (BCTC đang chờ duyệt tay thì không).

    Xu hướng: người dùng nói rõ số quý thì mọi quý còn thiếu của khung đều được đề nghị đọc thêm; không nói thì chỉ quý
    cuối (các quý trước chưa có trong kho thì báo cáo ghi rõ, không tự đề nghị đọc kỳ cũ)."""
    if plan.kind == "trend":
        window = trend_window(plan)
        offer = window if plan.quarters else window[-1:]
        items = [(t, y, f"Q{q}") for t in plan.tickers for y, q in offer]
    else:
        items = [(t, plan.year, plan.period) for t in plan.tickers]
    return [m for t, y, p in items if (m := _missing_one(conn, t, y, p)) is not None]


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


def _doc_facts(conn, doc_id: int):
    """(Facts, ô bị ẩn) của một BCTC; chưa có kết quả đọc thì ném RuntimeError."""
    record = _load_record(conn, doc_id)
    ev = document_evidence(conn, doc_id)
    f = Facts(doc_id, record, {(m.statement, m.key) for m in ev.missing} if ev else None)
    hidden = {k for k, v in (ev.status.items() if ev else []) if v["status"] in HIDDEN}
    return f, hidden


_MINORITY_LABEL = re.compile(r"khong kiem soat|thieu so")


def minority_code(f) -> str | None:
    """Mã dòng lợi ích cổ đông không kiểm soát trong phần vốn của BCĐKT doanh nghiệp/công ty chứng khoán (mã 4xx có tên
    "không kiểm soát"/"thiểu số"; 429 ở TT200/TT99, 418 ở BCTC SSI)."""
    for (st, code), it in sorted(f.rows.items()):
        if st == "BS" and code.startswith("4") and _MINORITY_LABEL.search(fold(clean_label(getattr(it, "label", "")))):
            return code
    return None


def _split_in_is(f) -> bool:
    """BCKQKD có tách phần lợi nhuận của cổ đông không kiểm soát (dòng đó có số khác 0)."""
    code = f.code("IS", "minority")
    return bool(code and "IS" in f.statements and any(f.statements["IS"].values.get(code, {}).values()))


def bs_column(f, column: str, hidden: set[tuple[str, str, str]]) -> tuple[dict[str, Decimal], set[str]]:
    """(mã -> số của một cột BCĐKT, mã bị chặn): bị chặn là ô "cần xem lại" ở cột đó hoặc dòng có dấu hiệu thiếu."""
    bs = f.statements.get("BS")
    vals = {c: cols[column] for c, cols in (bs.values.items() if bs else []) if cols.get(column) is not None}
    blocked = {c for st, c, col in hidden if st == "BS" and col == column} | {c for st, c in f.missing if st == "BS"}
    return vals, blocked


def balance(f, hidden: set[tuple[str, str, str]], key: str, column: str) -> Decimal | None:
    """Số dư dùng làm mẫu số của tỷ lệ (services/analyst/ratios.py): ROE -> vốn chủ sở hữu của cổ đông công ty mẹ, NIM ->
    tài sản sinh lãi của ngân hàng."""
    vals, blocked = bs_column(f, column, hidden)
    if f.template == "TCTD":
        return ratios.earning_assets(vals, blocked) if key == "nim" else ratios.parent_equity_bank(vals, blocked)
    if key == "nim":
        return None
    return ratios.parent_equity_corporate(vals, blocked, minority_code(f), _split_in_is(f))


BALANCE_NAME = {"roe": "vốn chủ sở hữu của cổ đông công ty mẹ", "nim": "tài sản sinh lãi"}
BANK_BALANCE_NAME = {"roe": "vốn chủ sở hữu của cổ đông ngân hàng mẹ", "nim": "tài sản sinh lãi"}
NUMERATOR = {"roe": "npat_parent", "nim": "nii"}
BALANCE_SOURCE = {("roe", "TCTD"): "b.te", ("nim", "TCTD"): "b.loans"}   # dòng số dư ghi làm nguồn; còn lại dòng 400


def computed_ratio(conn, ticker: str, f, hidden: set[tuple[str, str, str]], key: str, year: int, period: str,
                   basis: str, doc_type: str, doc_period: str) -> tuple[Pair, str | None, int | None]:
    """(tỷ lệ, lý do không tính được, BCTC quý trước đã dùng). Định nghĩa ở ratios.py: tử số quy năm, mẫu số bình quân
    đầu và cuối kỳ; riêng quý (trừ quý 1) lấy số dư đầu kỳ ở cột cuối kỳ của BCTC quý liền trước, đọc cùng mẫu."""
    cur_cols, _ = columns(doc_type, doc_period, basis)
    num = _first(f, NUMERATOR[key], cur_cols, hidden)
    end = balance(f, hidden, key, "end_period")
    prev_doc = None
    if basis == "quarter" and period != "Q1":
        begin = None
        found = _find(conn, ticker, year, f"Q{int(period[1]) - 1}")
        if found is not None and found[1] == "fs_quarter":
            try:
                pf, phidden = _doc_facts(conn, found[0])
            except RuntimeError:
                pf = None
            if pf is not None and pf.template == f.template:
                begin, prev_doc = balance(pf, phidden, key, "end_period"), found[0]
        start_text = f"cuối quý {int(period[1]) - 1}/{year}"
    else:
        begin = balance(f, hidden, key, "begin_year")
        start_text = "đầu năm"
    value = ratios.annualised_ratio(num.value, begin, end, ratios.annual_factor(basis, period))
    srcs = [asdict(s) for s in (num.source,) if s is not None]
    bv = f.get("BS", BALANCE_SOURCE.get((key, f.template), "400"), "end_period")
    if bv.source is not None:
        srcs.append(asdict(bv.source))
    why = None
    if value is None:
        kind = catalog.KIND_OF_TEMPLATE[f.template]
        bal = (BANK_BALANCE_NAME if kind == "TCTD" else BALANCE_NAME)[key]
        lack = [w for w, v in ((catalog.name(kind, NUMERATOR[key]) or NUMERATOR[key], num.value),
                               (f"{bal} cuối kỳ", end), (f"{bal} {start_text}", begin)) if v is None]
        why = (f"{catalog.name(kind, key)} của {ticker} {label(year, period, basis)}: không tính được, "
               + (f"thiếu {', '.join(lack)} đã kiểm chứng" if lack else "số dư bình quân không dương")
               + (" (chưa có BCTC quý trước)" if begin is None and prev_doc is None and basis == "quarter"
                  and period != "Q1" else "") + ".")
    return Pair(value, None, srcs), why, prev_doc


def _load(conn, ticker: str, year: int, period: str, basis: str, with_flags: bool, extra: tuple[str, ...] = (),
          computed: tuple[str, ...] = ()):
    """(số của mã, lý do không có): lý do là "document" (chưa có BCTC), "record" (chưa có kết quả đọc) hoặc "template"
    (mẫu BCTC chưa hỗ trợ, như bảo hiểm). `computed`: các tỷ lệ cần số dư bình quân (ROE, NIM) được hỏi; chỉ tính cho
    mã có chỉ tiêu đó."""
    found = _find(conn, ticker, year, period)
    if found is None:
        return None, "document"
    doc_id, doc_type, doc_period = found
    try:
        f, hidden = _doc_facts(conn, doc_id)
    except RuntimeError:
        return None, "record"
    kind = catalog.KIND_OF_TEMPLATE.get(f.template)
    if kind is None:
        return None, "template"
    cur_cols, prev_cols = columns(doc_type, doc_period, basis)
    values = {}
    for key in list(catalog.METRICS[kind]) + list(extra):      # extra: chỉ tiêu chuẩn ngoài danh mục (phép đo)
        cur, prev = _first(f, key, cur_cols, hidden), _first(f, key, prev_cols, hidden)
        values[key] = Pair(cur.value, prev.value, [asdict(s) for s in (cur.source, prev.source) if s is not None])
    notes, others = [], []
    for key in catalog.computed(kind, list(computed)):
        values[key], why, prev_doc = computed_ratio(conn, ticker, f, hidden, key, year, period, basis, doc_type,
                                                    doc_period)
        if why:
            notes.append(why)
        if prev_doc is not None:
            others.append(prev_doc)
    flags: list[tuple[str, str]] = []
    if with_flags and doc_type == "fs_quarter" and basis == "quarter":
        from services.metrics.service import card_for
        got = card_for(conn, doc_id)
        if got is not None:
            flags = visible_flags(got[0].flags, f, hidden)
    return TickerData(ticker, kind, label(year, period, basis), values, flags, doc_id, notes, others), None


def load_ticker(conn, ticker: str, year: int, period: str, basis: str, with_flags: bool = True,
                extra: tuple[str, ...] = (), computed: tuple[str, ...] = ()) -> TickerData | None:
    return _load(conn, ticker, year, period, basis, with_flags, extra, computed)[0]


def load_group(conn, kind: str, year: int, period: str, basis: str, with_flags: bool = False,
               computed: tuple[str, ...] = ()) -> Group:
    members = [d for t in tracked(conn, [kind])
               if (d := load_ticker(conn, t, year, period, basis, with_flags, computed=computed)) is not None]
    return Group(GROUP_NAMES[kind], members)


def _docs_of(d: TickerData) -> set[int]:
    return ({d.document_id} if d.document_id else set()) | set(d.other_documents)


def _computed_keys(plan: Plan) -> tuple[str, ...]:
    return tuple(k for k in plan.metrics if any(k in r for r in catalog.COMPUTED.values()))


def trend_points(conn, ticker: str, plan: Plan, computed: tuple[str, ...] = ()):
    """(loại công ty, các quý của khung kèm số, lý do không có số của mã): số riêng từng quý; quý cuối kèm cờ thẻ KQKD."""
    window = trend_window(plan)
    points, kind, why = [], None, None
    for i, (y, q) in enumerate(window):
        d, w = _load(conn, ticker, y, f"Q{q}", "quarter", i == len(window) - 1, computed=computed)
        if w == "template":
            return None, [], "template"
        if d is not None:
            kind = d.kind
        points.append((y, q, d))
    if kind is None:
        why = "document"
    return kind, points, why


def trend_sheet(conn, plan: Plan):
    """Câu hỏi xu hướng nhiều quý: số riêng từng quý của mỗi mã trong khung (quý chưa có BCTC kiểm chứng thì ghi rõ)."""
    data, notes = {}, []
    computed = _computed_keys(plan)
    for t in plan.tickers:
        kind, points, why = trend_points(conn, t, plan, computed)
        if why == "template":
            notes.append(f"Chưa hỗ trợ mẫu BCTC của {t} (bảo hiểm): báo cáo không có số của mã này.")
            continue
        lacking = [qlabel(y, q) for y, q, d in points if d is None]
        if kind is None:
            notes.append(f"Chưa có BCTC đã kiểm chứng của {t} cho {plan.label()}: báo cáo không có số của mã này.")
            continue
        if lacking:
            notes.append(f"{t}: chưa có BCTC đã kiểm chứng của {', '.join(lacking)}; xu hướng chỉ gồm các quý đã có số.")
        for y, q, d in points:
            # tỷ lệ của quý đầu khung thiếu số dư quý trước là chuyện thường: chỉ ghi lý do của quý cuối và lý do khác
            if d is not None:
                notes.extend(n for n in d.notes if (y, q) == points[-1][:2] or "chưa có BCTC quý trước" not in n)
        data[t] = (kind, points)
    sheet = build_trend(data, plan.metrics)
    docs = {i for _, pts in data.values() for _, _, d in pts if d is not None for i in _docs_of(d)}
    return sheet, _sources(docs), notes, trend_charts(data, plan.metrics)


def trend_rows(conn, plan: Plan, sheet: FactSheet, ticker: str, key: str) -> list[Fact]:
    """Dòng xu hướng của một chỉ tiêu mô hình xin thêm (câu hỏi xu hướng); đã có dòng đó thì không thêm."""
    if any(f.series and f.ticker == ticker and f.metric == key for f in sheet.facts):
        return []
    kind, points, _ = trend_points(conn, ticker, plan, (key,))
    f = trend_fact(sheet, ticker, kind, key, points) if kind else None
    return [f] if f else []


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
    computed = _computed_keys(plan)
    measure = plan.measure
    if computed and plan.metrics and plan.metrics[0] in computed and measure == "growth":
        measure = "level"       # ROE, NIM chưa có số cùng kỳ năm trước: chỉ xếp được theo mức kỳ này
        notes.append("ROE, NIM chưa có số cùng kỳ năm trước: xếp theo mức của kỳ này.")
    for k in sector_kinds(plan.sector):
        g = load_group(conn, k, plan.year, plan.period, plan.basis, with_flags=True, computed=computed)
        n = len(tracked(conn, [k]))
        if len(g.members) < n:
            have = {m.ticker for m in g.members}
            notes.append(f"{GROUP_LABELS[k].capitalize()}: {len(g.members)}/{n} mã đã có BCTC kiểm chứng cho "
                         f"{plan.label()}; chưa có: {', '.join(t for t in tracked(conn, [k]) if t not in have)}.")
        if g.members:
            groups[k] = g
    sheet, more, tops = build_screen(groups, plan.metrics, measure)
    docs = {i for g in groups.values() for m in g.members for i in _docs_of(m)}
    return sheet, _sources(docs), notes + more, screen_charts(groups, plan.metrics, measure, tops)


def sheet_for_plan(conn, plan: Plan):
    """(bảng số, BCTC nguồn kèm phiên bản, ghi chú, đặc tả biểu đồ)."""
    if plan.kind == "screen":
        return screen_sheet(conn, plan)
    if plan.kind == "trend":
        return trend_sheet(conn, plan)
    data, notes = [], []
    computed = _computed_keys(plan)
    for t in plan.tickers:
        d, why = _load(conn, t, plan.year, plan.period, plan.basis, True, computed=computed)
        if d is None:
            notes.append(f"Chưa hỗ trợ mẫu BCTC của {t} (bảo hiểm): báo cáo không có số của mã này." if why == "template"
                         else f"Chưa có BCTC đã kiểm chứng của {t} cho {plan.label()}: báo cáo không có số của mã này.")
            continue
        data.append(d)
        notes.extend(d.notes)
    groups = {k: load_group(conn, k, plan.year, plan.period, plan.basis, computed=computed)
              for k in {d.kind for d in data}} if plan.kind == "rank" else {}
    sheet = build_sheet(plan.kind, data, plan.metrics, groups)
    docs = {i for d in data for i in _docs_of(d)} | {i for g in groups.values() for m in g.members for i in _docs_of(m)}
    return sheet, _sources(docs), notes, chart_specs(plan.kind, data, plan.metrics, groups)
