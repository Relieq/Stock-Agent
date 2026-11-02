"""Tiêu đề cột của một báo cáo đã chép có đúng kỳ của BCTC không.

VCB quý 3/2026 (tài liệu 246382): file kẹp phụ lục "trình bày lại số liệu năm 2025" (BCĐKT 31/12/2025, KQKD năm
2025, ba cột "số KTNN / số đã công bố / chênh lệch") trước BCTC quý 3. Bước định vị lấy khối trang đầu tiên nên chép
nhầm phụ lục; mỗi cột vẫn tự cộng khớp nên mọi ràng buộc đạt. Kiểm tiêu đề cột: cột kỳ này phải có, và nếu tiêu đề có
ghi năm hay ngày thì phải đúng năm, đúng ngày cuối kỳ.
"""

from __future__ import annotations

import calendar
import re

END_MONTH = {"Q1": 3, "Q2": 6, "H1": 6, "Q3": 9, "Q4": 12, "FY": 12}
CURRENT = {"BS": ("end_period",), "IS": ("q_cur", "ytd_cur"), "CF": ("ytd_cur",)}
YEAR = re.compile(r"(?<!\d)(20\d\d)(?!\d)")
DATE = re.compile(r"(?<!\d)(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(20\d\d)(?!\d)")


def column_problem(statement: str, header: str, year: int, period: str) -> str | None:
    """Lý do tiêu đề một cột kỳ này không khớp kỳ của BCTC; khớp hoặc không đủ thông tin thì None."""
    years = {int(y) for y in YEAR.findall(header or "")}
    if years and year not in years:
        return f"cột kỳ này ghi năm {', '.join(map(str, sorted(years)))}, BCTC là năm {year}"
    month = END_MONTH.get(period)
    if statement == "BS" and month:
        dates = {(int(d), int(m), int(y)) for d, m, y in DATE.findall(header or "")}
        end = (calendar.monthrange(year, month)[1], month, year)
        if dates and end not in dates:
            got = ", ".join(f"{d}/{m}/{y}" for d, m, y in sorted(dates, key=lambda x: (x[2], x[1], x[0])))
            return f"cột cuối kỳ ghi ngày {got}, cuối kỳ là {end[0]}/{end[1]}/{end[2]}"
    return None


def period_problem(statement: str, raw: dict | None, year: int | None, period: str | None) -> str | None:
    """Lý do báo cáo đã chép không phải của kỳ này (không có cột kỳ này, hoặc mọi cột kỳ này ghi sai năm/ngày)."""
    if not raw or year is None or statement not in CURRENT:
        return None
    cols = [c for c in raw.get("columns") or [] if c.get("kind") in CURRENT[statement]]
    if not raw.get("columns"):
        return None                       # bản ghi cũ không lưu tiêu đề cột
    if not cols:
        # Mô hình có khi gán "other" cho cột "Kỳ này" (BID, HDB bán niên 2026): chỉ coi là sai kỳ khi tiêu đề có ghi năm
        # mà không năm nào là năm của BCTC
        years = {int(y) for c in raw["columns"] for y in YEAR.findall(c.get("header") or "")}
        if years and year not in years:
            return ("không cột nào là kỳ này: tiêu đề cột ghi năm " + ", ".join(map(str, sorted(years)))
                    + f", BCTC là năm {year}")
        return None
    problems = [column_problem(statement, c.get("header", ""), year, period) for c in cols]
    return problems[0] if all(problems) else None
