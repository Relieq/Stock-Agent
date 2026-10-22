"""Bảng số của báo cáo, tính bằng code từ số đã nạp (store.py) — không đụng CSDL, không gọi mô hình.

Mỗi dòng ghi đủ các con số được phép nói: kỳ này, cùng kỳ, % thay đổi và mức thay đổi; dòng so sánh ghi thứ tự các mã,
chênh lệch tăng trưởng (điểm %), số lần; dòng xếp hạng ghi thứ hạng, trung vị nhóm và thứ tự cả nhóm. Lợi nhuận âm ở một
trong hai kỳ thì không ghi %, mà tả bằng lời như thẻ KQKD.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from statistics import median

from services.analyst import catalog
from services.analyst.sheet import Fact, FactSheet
from services.analyst.trend import extremes, last_streak, pct_between, qlabel, qoq_dirs, value_of
from services.metrics.card import change_text, ty, vn

B = Decimal(10) ** 9


@dataclass
class Pair:
    cur: Decimal | None                 # đồng; tỷ lệ: %
    prev: Decimal | None
    sources: list[dict] = field(default_factory=list)


@dataclass
class TickerData:
    ticker: str
    kind: str                           # corporate / TCTD / CTCK
    label: str                          # "quý 3/2026"
    values: dict[str, Pair]
    flags: list[tuple[str, str]] = field(default_factory=list)   # (tên cờ, chi tiết) của thẻ KQKD
    document_id: int | None = None
    notes: list[str] = field(default_factory=list)               # tỷ lệ hỏi mà không tính được, kèm lý do
    other_documents: list[int] = field(default_factory=list)     # BCTC khác đã dùng (số dư cuối quý trước cho ROE, NIM)


@dataclass
class Group:
    name: str                           # "các ngân hàng đang theo dõi"
    members: list[TickerData]


def money(v: Decimal) -> str:
    return ("−" if v < 0 else "") + ty(v)


def signed(x: Decimal, unit: str) -> str:
    return ("+" if x >= 0 else "−") + vn(abs(x)) + unit


def is_ratio(kind: str, key: str) -> bool:
    return key in catalog.RATIOS.get(kind, {}) or key in catalog.COMPUTED.get(kind, {})


def pair_of(d: TickerData, key: str) -> Pair | None:
    if not is_ratio(d.kind, key) or key in catalog.COMPUTED.get(d.kind, {}):
        return d.values.get(key)      # tỷ lệ cần số dư bình quân: store.py đã tính sẵn (services/analyst/ratios.py)
    _, num, den = catalog.RATIOS[d.kind][key]
    n, m = d.values.get(num), d.values.get(den)
    if n is None or m is None:
        return None

    def r(a: Decimal | None, b: Decimal | None) -> Decimal | None:
        if a is None or not b:
            return None
        return (abs(a) if num in catalog.EXPENSES else a) / abs(b) * 100   # chi phí theo độ lớn; lợi nhuận giữ dấu

    return Pair(r(n.cur, m.cur), r(n.prev, m.prev), n.sources + m.sources)


def growth(d: TickerData, key: str) -> Decimal | None:
    """% thay đổi so với cùng kỳ (tỷ lệ: điểm %). Lợi nhuận âm ở một kỳ: None. Chi phí: theo độ lớn."""
    p = pair_of(d, key)
    if p is None or p.cur is None or p.prev is None:
        return None
    if is_ratio(d.kind, key):
        return p.cur - p.prev
    if p.prev == 0 or (key in catalog.PROFIT and (p.cur <= 0 or p.prev <= 0)):
        return None
    a, b = (abs(p.cur), abs(p.prev)) if key in catalog.EXPENSES else (p.cur, p.prev)
    return (a - b) / abs(b) * 100


def direction(d: TickerData, key: str) -> str | None:
    p = pair_of(d, key)
    if p is None or p.cur is None or p.prev is None:
        return None
    a, b = (abs(p.cur), abs(p.prev)) if key in catalog.EXPENSES else (p.cur, p.prev)
    return "up" if a > b else "down" if a < b else "flat"


def _show(d: TickerData, key: str, v: Decimal) -> str:
    if is_ratio(d.kind, key):
        return ("−" if v < 0 else "") + vn(abs(v)) + "%"
    return ty(abs(v)) if key in catalog.EXPENSES else money(v)


# Cách tính in kèm dòng tỷ lệ cần số dư bình quân, để mô hình viết đúng "quy năm" (định nghĩa: ratios.py)
COMPUTED_HOW = {
    ("roe", "TCTD"): "LNST của cổ đông ngân hàng mẹ quy năm trên vốn chủ sở hữu bình quân đầu và cuối kỳ của cổ đông "
                     "ngân hàng mẹ",
    ("roe", ""): "LNST của cổ đông công ty mẹ quy năm trên vốn chủ sở hữu bình quân đầu và cuối kỳ của cổ đông công ty mẹ",
    ("nim", "TCTD"): "thu nhập lãi thuần quy năm trên tài sản sinh lãi bình quân đầu và cuối kỳ",
}


def computed_how(kind: str, key: str) -> str | None:
    if key not in catalog.COMPUTED.get(kind, {}):
        return None
    return COMPUTED_HOW.get((key, kind)) or COMPUTED_HOW.get((key, ""))


def metric_fact(sheet: FactSheet, d: TickerData, key: str) -> Fact | None:
    name = catalog.name(d.kind, key)
    p = pair_of(d, key)
    if name is None or p is None or p.cur is None:
        return None
    how = computed_how(d.kind, key)
    parts = [f"{name}, {d.ticker}, {d.label}: {_show(d, key, p.cur)}" + (f" ({how})" if how else "")]
    if p.prev is None:
        parts.append("chưa có số cùng kỳ")
    else:
        parts.append(f"cùng kỳ {_show(d, key, p.prev)}")
        g = growth(d, key)
        if is_ratio(d.kind, key):
            parts.append("không đổi so với cùng kỳ" if g == 0 else f"thay đổi {signed(g, ' điểm %')}")
        else:
            delta = abs(p.cur) - abs(p.prev) if key in catalog.EXPENSES else p.cur - p.prev
            if delta == 0:
                parts.append("không đổi so với cùng kỳ")
            elif g is not None:
                parts.append(f"thay đổi {signed(g, '%')} ({'tăng' if delta > 0 else 'giảm'} {ty(abs(delta))})")
            else:
                parts.append(change_text(p.cur, p.prev, key in catalog.PROFIT))
    return sheet.add("ratio" if is_ratio(d.kind, key) else "metric", "; ".join(parts), ticker=d.ticker, metric=key,
                     direction=direction(d, key), names=catalog.names(d.kind, key), sources=p.sources)


def _title(kinds: set[str], key: str) -> str:
    kind = next(iter(kinds))
    if len(kinds) > 1:
        return {"pbt": "Lợi nhuận trước thuế", "npat_parent": "LNST của cổ đông công ty mẹ"}.get(key, key)
    return catalog.name(kind, key) or key


def compare_facts(sheet: FactSheet, data: list[TickerData], key: str) -> None:
    kinds = {d.kind for d in data}
    title, label = _title(kinds, key), data[0].label
    names = sorted({n for d in data for n in catalog.names(d.kind, key)})
    ratio = all(is_ratio(d.kind, key) for d in data)
    have = [(d, p) for d in data if (p := pair_of(d, key)) is not None and p.cur is not None]
    if len(have) >= 2:
        lv = sorted(have, key=lambda x: abs(x[1].cur) if key in catalog.EXPENSES else x[1].cur, reverse=True)
        text = f"{title}, xếp theo quy mô, {label}: " + ", ".join(f"{d.ticker} {_show(d, key, p.cur)}" for d, p in lv)
        (d0, p0), (d1, p1) = lv[0], lv[1]
        if len(lv) == 2 and ratio:
            gap = vn(p0.cur - p1.cur)
            text += (f"; {d0.ticker} và {d1.ticker} bằng nhau" if gap == "0,0"
                     else f"; {d0.ticker} cao hơn {d1.ticker} {gap} điểm %")
        elif len(lv) == 2 and p0.cur > 0 and p1.cur > 0:
            times = vn(p0.cur / p1.cur, 2)
            text += (f"; {d0.ticker} và {d1.ticker} bằng nhau" if times == "1,00"
                     else f"; {d0.ticker} gấp {times} lần {d1.ticker}")
        sheet.add("compare", text, metric=key, measure="level", order=[d.ticker for d, _ in lv], names=names)
    gr = sorted(((d, g) for d in data if (g := growth(d, key)) is not None), key=lambda x: x[1], reverse=True)
    if len(gr) >= 2:
        unit = " điểm %" if ratio else "%"
        text = f"{title}, thay đổi so với cùng kỳ, {label}: " + ", ".join(f"{d.ticker} {signed(g, unit)}" for d, g in gr)
        if len(gr) == 2:
            gap = vn(gr[0][1] - gr[1][1])
            text += (f"; {gr[0][0].ticker} và {gr[1][0].ticker} bằng nhau" if gap == "0,0"
                     else f"; {gr[0][0].ticker} cao hơn {gr[1][0].ticker} {gap} điểm %")
        sheet.add("compare", text, metric=key, measure="growth", order=[d.ticker for d, _ in gr], names=names)


def rank_facts(sheet: FactSheet, target: TickerData, group: Group, key: str) -> None:
    title, names = catalog.name(target.kind, key) or key, catalog.names(target.kind, key)
    ratio = is_ratio(target.kind, key)
    gr = sorted(((m, g) for m in group.members if (g := growth(m, key)) is not None), key=lambda x: x[1], reverse=True)
    lv = sorted(((m, abs(p.cur) if key in catalog.EXPENSES else p.cur) for m in group.members
                 if (p := pair_of(m, key)) is not None and p.cur is not None),
                key=lambda x: x[1], reverse=True)   # chi phí xếp theo độ lớn, như dòng so sánh
    for measure, items, fmt, head in (
            ("growth", gr, lambda v: signed(v, " điểm %" if ratio else "%"), f"{title}, thay đổi so với cùng kỳ"),
            ("level", lv, lambda v: _show(target, key, v), f"{title}, xếp theo quy mô")):
        order = [m.ticker for m, _ in items]
        if target.ticker not in order or len(items) < 3:
            continue
        r, n = order.index(target.ticker) + 1, len(items)
        med = Decimal(str(median([v for _, v in items])))
        text = (f"{head}, {target.label}, {group.name} ({n} mã có số): {target.ticker} xếp thứ {r} trong {n}; "
                f"trung vị nhóm {fmt(med)}; thứ tự: " + ", ".join(f"{m.ticker} {fmt(v)}" for m, v in items))
        sheet.add("rank", text, ticker=target.ticker, metric=key, measure=measure, order=order, names=names)


SCREEN_TOP = 5                          # số mã đứng đầu mỗi nhóm được nạp đủ chỉ tiêu và cờ cho câu hỏi "mã nào tốt nhất"
LOWER_IS_BETTER = {"cir"}                # tỷ lệ chi phí: thấp là tốt, như các khoản chi phí


def better_low(key: str) -> bool:
    return key in catalog.EXPENSES or key in LOWER_IS_BETTER


def screen_values(group: Group, key: str, measure: str) -> list[tuple[TickerData, Decimal]]:
    """(mã, giá trị) xếp từ cao xuống thấp: tăng trưởng so với cùng kỳ hoặc độ lớn kỳ này (chi phí theo độ lớn)."""
    if measure == "growth":
        items = [(m, g) for m in group.members if (g := growth(m, key)) is not None]
    else:
        items = [(m, abs(p.cur) if key in catalog.EXPENSES else p.cur) for m in group.members
                 if (p := pair_of(m, key)) is not None and p.cur is not None]
    return sorted(items, key=lambda x: x[1], reverse=True)


def screen_top(group: Group, key: str, measure: str, top: int = SCREEN_TOP) -> list[TickerData]:
    """Các mã tốt nhất theo tiêu chí: đầu thứ tự, hoặc cuối thứ tự với chi phí (thấp là tốt)."""
    items = [m for m, _ in screen_values(group, key, measure)]
    return list(reversed(items))[:top] if better_low(key) else items[:top]


def criterion(kind: str, key: str, measure: str) -> str:
    name = (catalog.name(kind, key) or key)
    what = f"mức thay đổi {name} so với cùng kỳ" if measure == "growth" else f"{name} kỳ này"
    return what + (" (thấp là tốt)" if better_low(key) else "")


def screen_facts(sheet: FactSheet, group: Group, kind: str, key: str, measure: str) -> list[TickerData]:
    """Dòng xếp hạng cả nhóm theo tiêu chí, rồi đủ chỉ tiêu và cờ của các mã đứng đầu. Trả về các mã đứng đầu."""
    items = screen_values(group, key, measure)
    if len(items) < 2:
        return []
    title, names = catalog.name(kind, key) or key, catalog.names(kind, key)
    label = items[0][0].label
    ratio = is_ratio(kind, key)
    fmt = (lambda v: signed(v, " điểm %" if ratio else "%")) if measure == "growth" else \
        (lambda v: ("−" if v < 0 else "") + vn(abs(v)) + "%" if ratio else money(v))
    head = f"{title}, thay đổi so với cùng kỳ" if measure == "growth" else f"{title}, xếp theo quy mô"
    n = len(items)
    text = (f"Xếp hạng theo {criterion(kind, key, measure)}: {head}, {label}, {group.name} ({n} mã có số), từ cao xuống "
            f"thấp: " + ", ".join(f"{m.ticker} {fmt(v)}" for m, v in items))
    if n >= 3:
        text += f"; trung vị nhóm {fmt(Decimal(str(median([v for _, v in items]))))}"
    left = [m.ticker for m in group.members if m.ticker not in {x.ticker for x, _ in items}]
    if left:
        text += ("; không tính được % thay đổi (lỗ ở một kỳ hoặc thiếu số cùng kỳ): " if measure == "growth"
                 else "; không có số: ") + ", ".join(left)
    sheet.add("rank", text, metric=key, measure=measure, order=[m.ticker for m, _ in items], names=names)
    top = screen_top(group, key, measure)
    for d in top:
        for k in dict.fromkeys([key] + catalog.keys_for(kind, [])):
            metric_fact(sheet, d, k)
        for t, detail in d.flags:
            sheet.add("flag", f"Cờ cảnh báo của thẻ KQKD, {d.ticker}, {d.label}: {t}. {detail}", ticker=d.ticker)
    return top


def screen_keys(kinds: list[str], metrics: list[str]) -> tuple[dict[str, str], list[str]]:
    """Chỉ tiêu xếp hạng của từng nhóm: chỉ tiêu đầu tiên người dùng nêu mà nhóm có (nhóm không có thì bỏ nhóm), không
    nêu thì LNST của cổ đông công ty mẹ. Trả về (nhóm -> chỉ tiêu, ghi chú)."""
    asked = [m for m in metrics if any(catalog.name(k, m) for k in kinds)]
    if not asked:
        note = [] if not metrics else ["Chỉ tiêu bạn nêu không có ở nhóm này: xếp theo LNST của cổ đông công ty mẹ."]
        return {k: "npat_parent" for k in kinds}, note
    key = asked[0]
    keys = {k: key for k in kinds if catalog.name(k, key)}
    skipped = [GROUP_LABELS[k] for k in kinds if k not in keys]
    return keys, ([f"{catalog.name(next(iter(keys)), key)} không có ở {', '.join(skipped)}: chỉ xếp "
                   f"{', '.join(GROUP_LABELS[k] for k in keys)}."] if skipped else [])


GROUP_LABELS = {"TCTD": "nhóm ngân hàng", "corporate": "nhóm doanh nghiệp", "CTCK": "nhóm công ty chứng khoán"}


def build_sheet(kind: str, data: list[TickerData], metrics: list[str],
                groups: dict[str, Group] | None = None) -> FactSheet:
    sheet = FactSheet()
    for d in data:
        for key in catalog.keys_for(d.kind, metrics):
            metric_fact(sheet, d, key)
        for title, detail in d.flags:
            sheet.add("flag", f"Cờ cảnh báo của thẻ KQKD, {d.ticker}, {d.label}: {title}. {detail}", ticker=d.ticker)
    if kind == "compare" and len(data) >= 2:
        for key in catalog.common_keys({d.kind for d in data}, metrics):
            compare_facts(sheet, data, key)
    if kind == "rank":
        for d in data:
            group = (groups or {}).get(d.kind)
            if group is None:
                continue
            for key in catalog.keys_for(d.kind, metrics):
                rank_facts(sheet, d, group, key)
    return sheet


def _ty_float(v: Decimal | None) -> float | None:
    return None if v is None else round(float(v / B), 1)


def chart_specs(kind: str, data: list[TickerData], metrics: list[str],
                groups: dict[str, Group] | None = None) -> list[dict]:
    """Biểu đồ cho trang báo cáo: số do code lấy thẳng từ dữ liệu đã nạp (tỷ đồng, %), không qua mô hình."""
    specs: list[dict] = []
    if not data:
        return specs
    if kind == "yoy":
        for d in data:
            items = [[catalog.name(d.kind, k), _ty_float(p.cur), _ty_float(p.prev)]
                     for k in catalog.keys_for(d.kind, metrics) if not is_ratio(d.kind, k)
                     and (p := d.values.get(k)) is not None and p.cur is not None]
            if items:
                specs.append({"type": "paired", "title": f"{d.ticker}: kỳ này và cùng kỳ, {d.label}", "unit": "tỷ đồng",
                              "items": items, "highlight": []})
        return specs
    keys = catalog.common_keys({d.kind for d in data}, metrics)
    key = next((k for k in keys if not all(is_ratio(d.kind, k) for d in data)), keys[0])
    title = _title({d.kind for d in data}, key)
    growth_unit = "điểm %" if all(is_ratio(d.kind, key) for d in data) else "%"
    if kind == "compare":
        items = [[d.ticker, _ty_float(p.cur), _ty_float(p.prev)] for d in data
                 if (p := d.values.get(key)) is not None and p.cur is not None]
        if items:
            specs.append({"type": "paired", "title": f"{title}, {data[0].label}", "unit": "tỷ đồng", "items": items,
                          "highlight": []})
        gr = [[d.ticker, round(float(g), 1)] for d in data if (g := growth(d, key)) is not None]
        if len(gr) >= 2:
            specs.append({"type": "bars", "title": f"{title}: thay đổi so với cùng kỳ", "unit": growth_unit, "items": gr,
                          "highlight": []})
        return specs
    for d in data:
        group = (groups or {}).get(d.kind)
        if group is None:
            continue
        gr = sorted(([m.ticker, round(float(g), 1)] for m in group.members if (g := growth(m, key)) is not None),
                    key=lambda x: -x[1])
        if gr:
            specs.append({"type": "bars", "title": f"{title}: thay đổi so với cùng kỳ, {group.name}", "unit": growth_unit,
                          "items": gr, "highlight": [d.ticker]})
    return specs


SCREEN_ORDER = ("TCTD", "corporate", "CTCK")       # thứ tự các nhóm trong báo cáo xếp hạng toàn bộ


def build_screen(groups: dict[str, Group], metrics: list[str], measure: str
                 ) -> tuple[FactSheet, list[str], dict[str, list[str]]]:
    """Bảng số cho câu hỏi "mã nào tốt nhất": xếp riêng từng nhóm (không so ngân hàng với doanh nghiệp). Trả về (bảng số,
    ghi chú, nhóm -> các mã đứng đầu)."""
    sheet = FactSheet()
    kinds = [k for k in SCREEN_ORDER if k in groups]
    keys, notes = screen_keys(kinds, metrics)
    tops = {}
    for k in kinds:
        if k not in keys:
            continue
        top = screen_facts(sheet, groups[k], k, keys[k], measure)
        if top:
            tops[k] = [d.ticker for d in top]
        else:
            notes.append(f"{GROUP_LABELS[k].capitalize()} có dưới 2 mã có số: không xếp hạng.")
    return sheet, notes, tops


def screen_charts(groups: dict[str, Group], metrics: list[str], measure: str, tops: dict[str, list[str]]) -> list[dict]:
    kinds = [k for k in SCREEN_ORDER if k in tops]
    keys, _ = screen_keys(kinds, metrics)
    specs = []
    for k in kinds:
        key = keys[k]
        ratio = is_ratio(k, key)
        items = [[m.ticker, round(float(v if measure == "growth" or ratio else v / B), 1)]
                 for m, v in screen_values(groups[k], key, measure)]
        unit = ("điểm %" if ratio else "%") if measure == "growth" else ("%" if ratio else "tỷ đồng")
        head = "thay đổi so với cùng kỳ" if measure == "growth" else "kỳ này"
        specs.append({"type": "bars", "title": f"{catalog.name(k, key)}: {head}, {GROUP_LABELS[k]}", "unit": unit,
                      "items": items, "highlight": tops[k]})
    return specs


# ---- xu hướng nhiều quý -----------------------------------------------------------------------------------------

Point = tuple[int, int, "TickerData | None"]        # (năm, quý, số của quý đó; None nếu chưa có BCTC kiểm chứng)


def _value_text(kind: str, key: str, v: Decimal) -> str:
    if is_ratio(kind, key):
        return ("−" if v < 0 else "") + vn(abs(v)) + "%"
    return ty(abs(v)) if key in catalog.EXPENSES else money(v)


def _step_text(kind: str, key: str, a: Decimal, b: Decimal) -> str:
    """Thay đổi từ quý a sang quý b: % (tỷ lệ: điểm %) kèm mức tăng/giảm; lợi nhuận âm ở một quý thì tả bằng lời."""
    if is_ratio(kind, key):
        return "không đổi" if b == a else signed(b - a, " điểm %")
    expense, profit = key in catalog.EXPENSES, key in catalog.PROFIT
    delta = abs(b) - abs(a) if expense else b - a
    if delta == 0:
        return "không đổi"
    pct = pct_between(a, b, expense, profit, False)
    word = "tăng" if delta > 0 else "giảm"
    if pct is not None:
        return f"{signed(pct, '%')} ({word} {ty(abs(delta))})"
    if a < 0 and b < 0:
        return f"lỗ {'thu hẹp' if delta > 0 else 'tăng'} từ {ty(a)} {'còn' if delta > 0 else 'lên'} {ty(b)}"
    if a <= 0 < b:
        return f"chuyển từ lỗ {ty(a)} sang lãi {ty(b)}" if a < 0 else f"từ hòa vốn lên lãi {ty(b)}"
    if b <= 0 < a:
        return f"chuyển từ lãi {ty(a)} sang lỗ {ty(b)}" if b < 0 else f"từ lãi {ty(a)} xuống hòa vốn"
    return f"{word} {ty(abs(delta))}"


def trend_fact(sheet: FactSheet, ticker: str, kind: str, key: str, points: list[Point]) -> Fact | None:
    """Dòng "Xu hướng ...": giá trị từng quý, thay đổi so với quý liền trước và so với cùng kỳ của từng quý, quý cuối so
    với quý đầu, quý cao nhất/thấp nhất, chuỗi tăng/giảm liên tiếp gần nhất. Chuỗi số (series) lưu kèm dòng để bộ kiểm
    tra số kiểm các câu xu hướng bằng đúng các phép tính ở trend.py. Dưới 2 quý có số: không có dòng."""
    name = catalog.name(kind, key)
    if name is None:
        return None
    expense = key in catalog.EXPENSES
    series, sources = [], []
    for y, q, d in points:
        p = pair_of(d, key) if d is not None else None
        v = p.cur if p is not None else None
        g = growth(d, key) if v is not None else None
        series.append({"y": y, "q": q, "label": qlabel(y, q), "value": None if v is None else str(v),
                       "yoy": None if g is None else str(g),
                       "yoy_dir": direction(d, key) if v is not None else None})
        if p is not None and v is not None:
            sources += p.sources
    have = [i for i, e in enumerate(series) if e["value"] is not None]
    if len(have) < 2:
        return None
    show = lambda v: _value_text(kind, key, v)      # noqa: E731
    how = computed_how(kind, key)
    head = (f"Xu hướng {name}, {ticker}, {len(series)} quý từ {series[0]['label']} đến {series[-1]['label']}"
            + (f" ({how})" if how else "") + ": ")
    parts = [head + ", ".join(f"{e['label']} {show(value_of(e)) if e['value'] is not None else 'chưa có số'}"
                              for e in series)]
    steps = [f"{series[i]['label']} {_step_text(kind, key, value_of(series[i - 1]), value_of(series[i]))}"
             for i in range(1, len(series)) if series[i - 1]["value"] is not None and series[i]["value"] is not None]
    if steps:
        parts.append("so với quý liền trước: " + ", ".join(steps))
    unit = " điểm %" if is_ratio(kind, key) else "%"
    yoy = [f"{e['label']} {signed(Decimal(e['yoy']), unit)}" for e in series if e["yoy"] is not None]
    if yoy:
        parts.append("so với cùng kỳ năm trước: " + ", ".join(yoy))
    first, last = have[0], have[-1]
    if last - first >= 2:
        parts.append(f"{series[last]['label']} so với {series[first]['label']}: "
                     + _step_text(kind, key, value_of(series[first]), value_of(series[last])))
    hi, lo = extremes(series, expense)
    parts.append(f"cao nhất trong {len(have)} quý có số là {series[hi]['label']} ({show(value_of(series[hi]))}), "
                 f"thấp nhất là {series[lo]['label']} ({show(value_of(series[lo]))})")
    run = last_streak(qoq_dirs(series, expense))
    if run and run[1] >= 2:
        parts.append(f"so với quý liền trước, {series[-1]['label']} là quý thứ {run[1]} liên tiếp "
                     f"{'tăng' if run[0] == 'up' else 'giảm'}")
    yrun = last_streak([e["yoy_dir"] for e in series])
    if yrun and yrun[1] >= 2:
        parts.append(f"so với cùng kỳ năm trước, {series[-1]['label']} là quý thứ {yrun[1]} liên tiếp "
                     f"{'tăng' if yrun[0] == 'up' else 'giảm'}")
    return sheet.add("trend", "; ".join(parts), ticker=ticker, metric=key, measure="trend",
                     names=catalog.names(kind, key), sources=sources, series=series)


def build_trend(data: dict[str, tuple[str, list[Point]]], metrics: list[str]) -> FactSheet:
    """Bảng số cho câu hỏi xu hướng: mỗi mã, mỗi chỉ tiêu một dòng xu hướng; thêm các dòng chỉ tiêu (so với cùng kỳ) và
    cờ của quý cuối; nhiều mã thì so các mã ở quý cuối."""
    sheet = FactSheet()
    last: list[TickerData] = []
    for ticker, (kind, points) in data.items():
        for key in catalog.keys_for(kind, metrics):
            trend_fact(sheet, ticker, kind, key, points)
        end = points[-1][2] if points else None
        if end is not None:
            last.append(end)
            for key in catalog.keys_for(kind, metrics):
                metric_fact(sheet, end, key)
            for title, detail in end.flags:
                sheet.add("flag", f"Cờ cảnh báo của thẻ KQKD, {end.ticker}, {end.label}: {title}. {detail}",
                          ticker=end.ticker)
    if len(last) >= 2:
        for key in catalog.common_keys({d.kind for d in last}, metrics):
            compare_facts(sheet, last, key)
    return sheet


TREND_CHARTS = 3        # số chỉ tiêu tối đa vẽ biểu đồ xu hướng


def trend_charts(data: dict[str, tuple[str, list[Point]]], metrics: list[str]) -> list[dict]:
    """Đường theo quý của từng chỉ tiêu (mỗi mã một đường): tỷ đồng, tỷ lệ thì %."""
    if not data:
        return []
    kinds = {kind for kind, _ in data.values()}
    keys = catalog.common_keys(kinds, metrics) if len(data) > 1 else catalog.keys_for(next(iter(kinds)), metrics)
    window = next(iter(data.values()))[1]
    labels = [f"Q{q}/{y}" for y, q, _ in window]
    specs = []
    for key in keys[:TREND_CHARTS]:
        lines = []
        ratio = all(is_ratio(kind, key) for kind, _ in data.values())
        for ticker, (kind, points) in data.items():
            vals = []
            for _, _, d in points:
                p = pair_of(d, key) if d is not None else None
                v = p.cur if p is not None else None
                if v is None:
                    vals.append(None)
                    continue
                mag = abs(v) if key in catalog.EXPENSES else v
                vals.append(round(float(mag if ratio else mag / B), 1))
            if sum(v is not None for v in vals) >= 2:
                lines.append({"name": ticker, "values": vals})
        if lines:
            specs.append({"type": "line", "title": f"{_title(kinds, key)} theo quý", "unit": "%" if ratio else "tỷ đồng",
                          "labels": labels, "series": lines, "highlight": []})
    return specs
