"""Công cụ mô hình viết lời được xin thêm (Baocao/dinh-huong/agent-bao-cao.md mục 5): một chỉ tiêu của một mã, hoặc
nguyên nhân công ty nêu trong công văn giải trình kèm kết quả đối chiếu với BCTC."""

from __future__ import annotations

from services.analyst import store
from services.analyst.explanations import Check, check_section, facts_for, load_letter
from services.analyst.facts import metric_fact
from services.analyst.guard import numbers
from services.analyst.plan import Plan
from services.analyst.sheet import Fact, FactSheet, report_tickers

REASON_LABELS = {"khớp": "đã đối chiếu, khớp BCTC", "khớp chiều": "đã đối chiếu, khớp chiều tăng/giảm",
                 "không kiểm được": "theo công ty, chưa kiểm được bằng số"}
PERIOD_KINDS = {"quarter": ("quarter",), "ytd": ("ytd", "half_year", "year")}
WORDS_ONLY = {"khớp chiều", "không kiểm được"}     # số trong các nguyên nhân này chưa đối chiếu được với BCTC


def words_only(text: str) -> str:
    """Thay mọi con số (đọc như bộ kiểm tra số) bằng "…", để số chưa kiểm không thành số có nguồn trong bảng số."""
    for n in reversed(numbers(text)):
        text = text[:n.start] + "…" + text[n.end:]
    return text


def reason_line(ticker: str, c: Check) -> str | None:
    """Dòng bảng số cho một nguyên nhân; nguyên nhân lệch với BCTC thì None. Chỉ nguyên nhân khớp số giữ số."""
    lab = REASON_LABELS.get(c.verdict)
    if lab is None:
        return None
    what = words_only(c.what) if c.verdict in WORDS_ONLY else c.what
    return f"Nguyên nhân {ticker} nêu trong công văn giải trình ({lab}): {what}"


def more_metric(conn, plan: Plan, sheet: FactSheet, ticker: str, key: str) -> list[Fact]:
    if ticker not in report_tickers(plan, sheet):
        return []
    if plan.kind == "trend":        # câu hỏi xu hướng: thêm dòng xu hướng của chỉ tiêu đó
        return store.trend_rows(conn, plan, sheet, ticker, key)
    d = store.load_ticker(conn, ticker, plan.year, plan.period, plan.basis, with_flags=False, computed=(key,))
    f = metric_fact(sheet, d, key) if d is not None else None
    return [f] if f else []


def reasons(conn, client, plan: Plan, sheet: FactSheet, ticker: str, cache_dir=None) -> list[Fact]:
    """Nguyên nhân trong công văn giải trình cùng kỳ. Chỉ đưa nguyên nhân khớp, khớp chiều hoặc chưa kiểm được (ghi rõ là
    theo công ty); nguyên nhân lệch với BCTC không đưa cho mô hình."""
    if ticker not in report_tickers(plan, sheet):
        return []
    row = conn.execute(
        """SELECT id, fiscal_period FROM documents
           WHERE ticker = %s AND fiscal_year = %s AND fiscal_period = ANY(%s) AND doc_type = 'explanation'
             AND owner_user_id IS NULL AND duplicate_of IS NULL
           ORDER BY (fiscal_period = %s) DESC, (scope = 'consolidated') DESC, source_listed_at DESC NULLS LAST LIMIT 1""",
        (ticker, plan.year, [plan.period, store.reading_period(plan.period)], plan.period)).fetchone()
    if row is None:
        return [sheet.add("reason", f"{ticker} không có công văn giải trình cho {plan.label()}.", ticker=ticker)]
    doc_id, period = row
    src = [{"document_id": doc_id, "page": None, "label": "Công văn giải trình", "raw": None}]
    out = []
    for sec in load_letter(conn, client, doc_id, cache_dir).get("sections", []):
        if sec["scope"] == "separate" or sec["period_kind"] not in PERIOD_KINDS[plan.basis]:
            continue
        res = check_section(sec, facts_for(conn, ticker, plan.year, period, sec["scope"], sec["period_kind"]))
        for c in res.checks:
            if c.what == "cả phần" or c.what.startswith(("lợi nhuận", "doanh thu", "% thay đổi")):
                continue
            line = reason_line(ticker, c)
            if line:
                out.append(sheet.add("reason", line, ticker=ticker, sources=src))
    return out or [sheet.add("reason", f"Công văn giải trình của {ticker} không có nguyên nhân dùng được cho "
                                       f"{plan.label()}.", ticker=ticker)]
