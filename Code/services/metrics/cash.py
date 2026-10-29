"""Chất lượng lợi nhuận trên thẻ KQKD: lãi có thu về thành tiền không, tiền nằm lại ở đâu.

Chỉ tính bằng code từ số đã kiểm chứng (LCTT lập theo phương pháp gián tiếp, BCĐKT, KQKD), mỗi số mang nguồn như các
số khác trên thẻ. Không áp dụng cho ngân hàng và công ty chứng khoán: dòng tiền kinh doanh của họ gồm cả tiền gửi, cho
vay, cho vay ký quỹ nên không đo được chất lượng lợi nhuận. Đây là dữ kiện, không phải nhận định tốt/xấu.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import replace
from datetime import date
from decimal import Decimal

from services.extraction.bank import clean_label, fold

# Các dòng giữa "lợi nhuận trước thay đổi vốn lưu động" (08) và "lưu chuyển tiền thuần từ hoạt động kinh doanh" (20),
# tên viết theo việc đã xảy ra để người đọc không phải suy nghĩa của dấu: (khi làm tiền ít đi, khi làm tiền nhiều lên)
WORDING = {
    "09": ("Khách hàng và bên khác nợ thêm (phải thu tăng)", "Thu được tiền khách nợ (phải thu giảm)"),
    "10": ("Nhập thêm hàng, tồn kho tăng", "Bán bớt hàng tồn kho"),
    "11": ("Trả bớt nợ nhà cung cấp và các khoản phải trả", "Nợ nhà cung cấp và các khoản phải trả nhiều hơn"),
    "12": ("Chi phí trả trước tăng", "Chi phí trả trước giảm"),
    "13": ("Mua thêm chứng khoán kinh doanh", "Bán bớt chứng khoán kinh doanh"),
    "14": ("Trả lãi vay", "Trả lãi vay"),
    "15": ("Nộp thuế thu nhập doanh nghiệp", "Được hoàn thuế thu nhập doanh nghiệp"),
    "16": ("Chi khác cho hoạt động kinh doanh", "Thu khác từ hoạt động kinh doanh"),
    "17": ("Chi khác cho hoạt động kinh doanh", "Thu khác từ hoạt động kinh doanh"),
}
SMALL_SHARE = Decimal("0.01")      # khoản dưới 1% mốc đầu (hoặc dòng tiền kinh doanh) gộp vào "các khoản nhỏ khác"
PERIOD_END_MONTH = {"Q1": 3, "Q2": 6, "H1": 6, "Q3": 9, "Q4": 12, "FY": 12}
_CODE = re.compile(r"(\d{2})[a-z]?")
_PROFIT_LABEL = re.compile(r"loi nhuan|lai.*truoc thue")


def period_days(year: int, period: str) -> int | None:
    """Số ngày từ đầu năm tài chính tới cuối kỳ (năm tài chính theo năm dương lịch)."""
    month = PERIOD_END_MONTH.get(period)
    if month is None:
        return None
    return (date(year, month, calendar.monthrange(year, month)[1]) - date(year, 1, 1)).days + 1


def _codes_between(f, lo: int, hi: int) -> list[str]:
    cf = f.statements["CF"].values
    return sorted(c for c in cf if (m := _CODE.fullmatch(c)) and lo <= int(m.group(1)) <= hi)


def _blocked(hidden: set, *cells: tuple[str, str, str]) -> bool:
    return any(c in hidden for c in cells)


def _pct(part: Decimal, whole: Decimal) -> Decimal:
    return part / whole * 100


def _growth(cur: Decimal | None, prev: Decimal | None) -> Decimal | None:
    if cur is None or prev is None or prev <= 0 or cur < 0:
        return None
    return _pct(cur - prev, prev)


QUARTER_COLUMN = {"ytd_cur": "q_cur", "ytd_prev_year": "q_prev_year"}


def ytd(f, metric: str, col: str, period: str):
    """(số lũy kế trên KQKD, cột đã dùng). BCTC quý 1 thường chỉ in cột quý: lũy kế quý 1 chính là số quý. Quý khác
    thiếu cột lũy kế thì để trống (LCTT là lũy kế, không ghép với số một quý)."""
    v = f.metric("IS", metric, col)
    if v.value is None and period == "Q1":
        col = QUARTER_COLUMN[col]
        v = f.metric("IS", metric, col)
    return v, col


def summary(f, hidden: set, period: str) -> dict | None:
    """LNST và tiền thu từ hoạt động kinh doanh, lũy kế kỳ này và cùng kỳ."""
    out = {}
    for col in ("ytd_cur", "ytd_prev_year"):
        (npat, is_col), cfo = ytd(f, "npat", col, period), f.metric("CF", "cfo", col)
        if npat.value is None or cfo.value is None or _blocked(
                hidden, ("IS", f.code("IS", "npat"), is_col), ("CF", f.code("CF", "cfo"), col)):
            if col == "ytd_cur":
                return None
            continue
        ratio = _pct(cfo.value, npat.value) if npat.value > 0 else None
        out[col] = {"npat": npat, "cfo": cfo, "ratio": ratio}
    return out


def bridge(f, hidden: set) -> tuple[dict | None, str | None]:
    """(bảng "lợi nhuận đi đâu", lý do không lập được). Đi từ lợi nhuận trước thay đổi vốn lưu động (dòng 08) qua từng
    khoản 09-17 tới dòng tiền kinh doanh (20), lũy kế kỳ này. Các khoản phải cộng đúng ra dòng 20 (sai số làm tròn
    ±1 đơn vị in mỗi số hạng như phép kiểm của LCTT), không thì không hiện."""
    if "CF" not in f.statements:
        return None, "BCTC không có LCTT"
    col = "ytd_cur"
    cfo = f.get("CF", "20", col)
    if cfo.value is None:
        return None, "LCTT không có dòng lưu chuyển tiền thuần từ hoạt động kinh doanh"
    start = f.get("CF", "08", col)
    used = [("CF", "20", col)]
    if start.value is None:
        first = f.rows.get(("CF", "01"))
        if first is None or not _PROFIT_LABEL.search(fold(clean_label(first.label or ""))):
            return None, "LCTT lập theo phương pháp trực tiếp, không có các dòng điều chỉnh từ lợi nhuận"
        parts = [f.get("CF", c, col) for c in _codes_between(f, 1, 7)]
        start_value = sum((p.value for p in parts if p.value is not None), Decimal(0))
        start = type(start)(start_value, None, "Cộng lợi nhuận trước thuế và các khoản điều chỉnh (dòng 01 đến 07); "
                                                "BCTC không in sẵn dòng này")
        used += [("CF", c, col) for c in _codes_between(f, 1, 7)]
    else:
        used.append(("CF", "08", col))
    items = []
    for c in _codes_between(f, 9, 17):
        v = f.get("CF", c, col)
        if v.value:
            items.append((c, v))
            used.append(("CF", c, col))
    if _blocked(hidden, *used):
        return None, "có ô trong LCTT đang cần xem lại"
    total = start.value + sum(v.value for _, v in items)
    if abs(total - cfo.value) > f.statements["CF"].multiplier * (len(items) + 2):
        return None, "các dòng của LCTT không cộng ra đúng dòng tiền kinh doanh"

    scale = max(abs(start.value), abs(cfo.value)) or Decimal(1)
    groups: dict[str, list[dict]] = {"down": [], "up": []}
    small = {"down": [], "up": []}
    for c, v in items:
        side = "down" if v.value < 0 else "up"
        if abs(v.value) < scale * SMALL_SHARE:
            small[side].append(v)
            continue
        words = WORDING.get(_CODE.fullmatch(c).group(1))
        name = words[0 if side == "down" else 1] if words else clean_label(f.rows[("CF", c)].label or c)
        groups[side].append({"name": name, "value": replace(v, value=abs(v.value)), "amount": abs(v.value)})
    for side, vals in small.items():
        if vals:
            amount = abs(sum(v.value for v in vals))
            if amount:
                groups[side].append({"name": "Các khoản nhỏ khác", "value": type(cfo)(amount, None,
                                     "Cộng " + ", ".join(clean_label(v.source.label or v.source.code) for v in vals)),
                                     "amount": amount, "sources": [v.source for v in vals]})
    for side in groups:
        groups[side].sort(key=lambda r: -r["amount"])

    # Thanh thác nước: vị trí tính theo phần trăm bề ngang của dải số từ min tới max các mức cộng dồn
    level, points = start.value, [Decimal(0), start.value]
    for r in groups["down"]:
        r["from"], level = level, level - r["amount"]
        r["to"] = level
        points.append(level)
    for r in groups["up"]:
        r["from"], level = level, level + r["amount"]
        r["to"] = level
        points.append(level)
    lo, hi = min(points + [cfo.value]), max(points + [cfo.value])
    span = (hi - lo) or Decimal(1)

    def bar(a: Decimal, b: Decimal) -> dict:
        left, right = min(a, b), max(a, b)
        return {"left": float((left - lo) / span * 100), "width": max(float((right - left) / span * 100), 0.4)}

    for side in groups:
        for r in groups[side]:
            r["bar"] = bar(r.pop("from"), r.pop("to"))
    return {"start": start, "start_bar": bar(Decimal(0), start.value), "down": groups["down"], "up": groups["up"],
            "end": cfo, "end_bar": bar(Decimal(0), cfo.value)}, None


def balances(f, hidden: set, year: int, period: str) -> list[dict]:
    """Tồn kho và phải thu ngắn hạn: đầu năm, cuối kỳ, thay đổi, đặt cạnh mức tăng giá vốn/doanh thu lũy kế so cùng
    kỳ, và số ngày giá vốn/doanh thu mà số dư cuối kỳ tương ứng."""
    days = period_days(year, period)
    out = []
    for key, name, flow_key, flow_name in (("inventory", "Hàng tồn kho", "cogs", "giá vốn"),
                                           ("receivables", "Phải thu ngắn hạn", "revenue", "doanh thu")):
        code = f.code("BS", key)
        end, begin = f.get("BS", code, "end_period"), f.get("BS", code, "begin_year")
        (flow, col), (flow_prev, col_prev) = ytd(f, flow_key, "ytd_cur", period), ytd(f, flow_key, "ytd_prev_year", period)
        if end.value is None or _blocked(hidden, ("BS", code, "end_period"), ("BS", code, "begin_year"),
                                         ("IS", f.code("IS", flow_key), col), ("IS", f.code("IS", flow_key), col_prev)):
            continue
        row = {"name": name, "end": end, "begin": begin, "flow_name": flow_name, "flow": flow,
               "change": _growth(end.value, begin.value), "flow_change": _growth(flow.value, flow_prev.value),
               "days": None}
        if days and flow.value and flow.value > 0:
            row["days"] = end.value / flow.value * days
        out.append(row)
    return out


def cash_quality(f, year: int, period: str, hidden: set | None = None) -> tuple[dict | None, str | None]:
    """(mục "Chất lượng lợi nhuận", lý do không có). hidden: các ô (báo cáo, mã, cột) đang "cần xem lại"."""
    if f.template not in ("TT200", "TT99"):
        return None, None
    hidden = hidden or set()
    head = summary(f, hidden, period)
    if head is None:
        return None, ("Chất lượng lợi nhuận: KQKD không in số lũy kế để đặt cạnh dòng tiền kinh doanh lũy kế"
                      if f.metric("IS", "npat", "q_cur").value is not None else
                      "Chất lượng lợi nhuận: chưa có LNST hoặc dòng tiền kinh doanh lũy kế đã kiểm chứng")
    table, reason = bridge(f, hidden)
    return {"summary": head, "bridge": table, "bridge_reason": reason,
            "balances": balances(f, hidden, year, period), "days": period_days(year, period)}, None
