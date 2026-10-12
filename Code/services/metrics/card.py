"""Thẻ KQKD: số chính, tăng trưởng theo quy tắc hiển thị và cờ cảnh báo, tính bằng code từ số đã kiểm chứng.

Theo kế hoạch MVP (Baocao/dinh-huong/ke-hoach-mvp.md mục 2.1, 2.2):
  * mọi số mang theo nguồn: tài liệu, báo cáo, mã số, trang, chuỗi nguyên văn như in;
  * kỳ này hoặc cùng kỳ lỗ thì không in %, viết bằng chữ ("lỗ thu hẹp", "chuyển từ lỗ sang lãi"...);
  * cờ là thông tin để người đọc xem kỹ hơn, không phải nhận định tốt/xấu hay khuyến nghị.
Mô hình ngôn ngữ không tham gia: không có phép tính nào do LLM làm.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal

from services.extraction.bank import clean_label, fold
from services.extraction.numbers import normalize_code
from services.extraction.pipeline import _check
from services.extraction.rules import BANK_INCOME_PARTS, RULESETS
from services.extraction.validate import expenses_printed_negative
from services.metrics.canonical import code_for

QUARTERS = ("Q1", "Q2", "Q3", "Q4")

# Số chính trên thẻ: (chỉ tiêu chuẩn, tên hiển thị)
KEY_METRICS = {
    "corporate": [("revenue", "Doanh thu thuần"), ("gross_profit", "Lợi nhuận gộp"),
                  ("npat_parent", "LNST của cổ đông công ty mẹ")],
    "TCTD": [("nii", "Thu nhập lãi thuần"), ("toi", "Tổng thu nhập hoạt động"),
             ("provision", "Chi phí dự phòng rủi ro tín dụng"), ("pbt", "Lợi nhuận trước thuế"),
             ("npat_parent", "LNST của cổ đông ngân hàng mẹ")],
}
EXPENSE_METRICS = {"provision", "cogs", "selling_expense", "admin_expense", "opex"}


@dataclass
class Source:
    document_id: int
    statement: str
    code: str
    column: str
    page: int | None
    label: str
    raw: str | None          # chuỗi nguyên văn như in trên BCTC


@dataclass
class Value:
    value: Decimal | None    # đồng; chi phí đổi về số dương
    source: Source | None = None
    computed: str | None = None   # cách tính nếu không in sẵn trên BCTC (ví dụ tổng thu nhập hoạt động của ngân hàng)


@dataclass
class Metric:
    key: str
    name: str
    q_cur: Value
    q_prev_year: Value
    ytd_cur: Value
    ytd_prev_year: Value
    q_change: str = ""
    ytd_change: str = ""


@dataclass
class Flag:
    key: str
    title: str
    detail: str
    sources: list[Source] = field(default_factory=list)


@dataclass
class Card:
    document_id: int
    ticker: str
    year: int
    period: str
    template: str | None
    metrics: list[Metric]
    flags: list[Flag]
    not_evaluated: list[str]              # cờ chưa xét được và lý do
    supported: bool = True
    plan: dict | None = None              # lũy kế so với kế hoạch năm của ĐHCĐ


# ---- đọc số từ bản ghi trích xuất -------------------------------------------------------------------------------

class Facts:
    """Số đã chuẩn hóa của một tài liệu (đồng) kèm nguồn từng ô."""

    def __init__(self, document_id: int, record: dict):
        extracted, statements, _, template, _ = _check(record)
        self.document_id = document_id
        self.template = template
        self.statements = statements
        self.flip_is = "IS" in statements and template in RULESETS and \
            expenses_printed_negative(statements["IS"], RULESETS[template].expense_codes)
        self.rows: dict[tuple[str, str], object] = {}
        for ex in extracted:
            for it in ex.items:
                code = normalize_code(it.code)
                if code and (ex.statement, code) not in self.rows:
                    self.rows[(ex.statement, code)] = it

    def code(self, statement: str, metric: str) -> str | None:
        if self.template is None:
            return None
        return code_for(self.template, statement, metric)

    def get(self, statement: str, code: str | None, column: str, expense: bool = False) -> Value:
        if code is None:
            return Value(None)
        v = self.statements.get(statement).values.get(code, {}).get(column) if statement in self.statements else None
        it = self.rows.get((statement, code))
        src = Source(self.document_id, statement, code, column, getattr(it, "page", None),
                     getattr(it, "label", ""), (it.values_raw.get(column) if it else None)) if v is not None else None
        if v is not None and expense and statement == "IS" and self.flip_is:
            v = -v
        return Value(v, src)

    def metric(self, statement: str, metric: str, column: str) -> Value:
        expense = metric in EXPENSE_METRICS
        val = self.get(statement, self.code(statement, metric), column, expense)
        if val.value is None and self.template == "TCTD" and metric == "toi" and statement == "IS":
            parts = [self.get("IS", c, column) for c in BANK_INCOME_PARTS]
            if any(p.value is not None for p in parts):
                total = sum((p.value for p in parts if p.value is not None), Decimal(0))
                return Value(total, None, "Cộng các khoản thu nhập thuần (BCTC không in dòng tổng)")
        if val.value is None and metric == "npat_parent":
            # Một số BCTC (riêng, hoặc ngân hàng không có công ty con) không tách phần cổ đông công ty mẹ
            alt = self.get(statement, self.code(statement, "npat"), column)
            if alt.value is not None:
                return Value(alt.value, alt.source, "BCTC không tách LNST của cổ đông công ty mẹ: dùng LNST")
        return val


# ---- quy tắc hiển thị tăng trưởng ---------------------------------------------------------------------------------

def vn(x: Decimal | float, decimals: int = 1) -> str:
    """Số kiểu Việt Nam: dấu chấm phân tách hàng nghìn, dấu phẩy thập phân."""
    return f"{x:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def ty(v: Decimal) -> str:
    """Đồng -> tỷ đồng, bỏ dấu: 1.234,5 tỷ (dưới 100 tỷ giữ một chữ số thập phân)."""
    x = abs(v) / Decimal(10**9)
    return vn(x, 1 if x < 100 else 0) + " tỷ"


def change_text(cur: Decimal | None, prev: Decimal | None, profit: bool) -> str:
    """Mô tả thay đổi so với cùng kỳ. Lợi nhuận âm ở kỳ này hoặc cùng kỳ thì viết bằng chữ, không in %."""
    if cur is None or prev is None:
        return ""
    if profit and (cur <= 0 or prev <= 0):
        if prev < 0 and cur < 0:
            if abs(cur) < abs(prev):
                return f"lỗ thu hẹp từ {ty(prev)} còn {ty(cur)}"
            if abs(cur) > abs(prev):
                return f"lỗ tăng từ {ty(prev)} lên {ty(cur)}"
            return f"lỗ {ty(cur)}, bằng cùng kỳ"
        if prev <= 0 < cur:
            return f"chuyển từ lỗ {ty(prev)} sang lãi {ty(cur)}" if prev < 0 else f"lãi {ty(cur)}, cùng kỳ hòa vốn"
        if cur <= 0 < prev:
            return f"chuyển từ lãi {ty(prev)} sang lỗ {ty(cur)}" if cur < 0 else f"hòa vốn, cùng kỳ lãi {ty(prev)}"
        return "hòa vốn cả hai kỳ"
    if prev == 0:
        return f"cùng kỳ bằng 0, kỳ này {ty(cur)}"
    pct = (cur - prev) / abs(prev) * 100
    if pct >= 0:
        return f"+{vn(pct)}% (từ {ty(prev)} lên {ty(cur)})"
    return f"−{vn(-pct)}% (từ {ty(prev)} xuống {ty(cur)})"


# ---- cờ cảnh báo ---------------------------------------------------------------------------------------------------

def _src(*values: Value) -> list[Source]:
    return [v.source for v in values if v.source is not None]


def flag_sign_change(f: Facts) -> Flag | None:
    cur, prev = f.metric("IS", "npat_parent", "q_cur"), f.metric("IS", "npat_parent", "q_prev_year")
    if cur.value is None or prev.value is None or (cur.value > 0 and prev.value > 0):
        return None
    return Flag("sign_change", "Lỗ hoặc đổi dấu lợi nhuận",
                f"LNST quý: {change_text(cur.value, prev.value, True)}. Tỷ lệ % không có ý nghĩa khi một trong hai kỳ lỗ.",
                _src(cur, prev))


def flag_low_base(f: Facts, history: dict[tuple[int, str], Decimal], year: int, period: str) -> Flag | str | None:
    """Tăng > 100% và LNST cùng kỳ < 1/3 trung bình 4 quý trước quý cùng kỳ. Trả về chuỗi lý do nếu chưa xét được."""
    cur, prev = f.metric("IS", "npat_parent", "q_cur"), f.metric("IS", "npat_parent", "q_prev_year")
    if cur.value is None or prev.value is None or prev.value <= 0 or cur.value <= 2 * prev.value:
        return None
    if period not in QUARTERS:
        return None
    i = QUARTERS.index(period)
    before = []
    y, q = year - 1, i
    for _ in range(4):           # 4 quý ngay trước quý cùng kỳ năm trước
        q -= 1
        if q < 0:
            y, q = y - 1, 3
        before.append(history.get((y, QUARTERS[q])))
    known = [v for v in before if v is not None]
    if len(known) < 2:
        return f"tăng {change_text(cur.value, prev.value, True)} nhưng chưa đủ lịch sử LNST các quý trước để xét nền thấp"
    avg = sum(known) / len(known)
    if prev.value >= avg / 3:
        return None
    return Flag("low_base", "Tăng trưởng do nền so sánh thấp",
                f"LNST quý {change_text(cur.value, prev.value, True)}, nhưng LNST cùng kỳ chỉ bằng "
                f"{vn(prev.value / avg * 100, 0)}% trung bình {len(known)} quý trước đó ({ty(avg)}).",
                _src(cur, prev))


def flag_non_core(f: Facts) -> Flag | None:
    if f.template == "TCTD":
        return None
    gp, sell, adm = (f.metric("IS", m, "q_cur") for m in ("gross_profit", "selling_expense", "admin_expense"))
    pbt = f.metric("IS", "pbt", "q_cur")
    if None in (gp.value, pbt.value) or pbt.value <= 0:
        return None
    core = gp.value - (sell.value or 0) - (adm.value or 0)
    other = pbt.value - core
    if core <= 0 or other > pbt.value / 2:
        part = (f"lợi nhuận từ hoạt động chính (LN gộp − CP bán hàng − CP quản lý) là {'−' if core < 0 else ''}{ty(core)}"
                f", phần còn lại {ty(other)} đến từ hoạt động tài chính, công ty liên kết hoặc thu nhập khác")
        return Flag("non_core", "Lợi nhuận phần lớn ngoài hoạt động chính",
                    f"LNTT quý {ty(pbt.value)}: {part}.", _src(gp, sell, adm, pbt))
    return None


def flag_provision(f: Facts) -> Flag | None:
    if f.template == "TCTD":
        cur, prev = f.metric("IS", "provision", "q_cur"), f.metric("IS", "provision", "q_prev_year")
        pbt, pbt_prev = f.metric("IS", "pbt", "q_cur"), f.metric("IS", "pbt", "q_prev_year")
        if None in (cur.value, prev.value):
            return None
        if cur.value < 0:
            return Flag("provision", "Hoàn nhập dự phòng",
                        f"Chi phí dự phòng rủi ro tín dụng quý này là số âm ({ty(cur.value)}): ngân hàng hoàn nhập dự phòng, "
                        f"làm tăng lợi nhuận.", _src(cur))
        if prev.value > 0 and cur.value < prev.value / 2 and None not in (pbt.value, pbt_prev.value) \
                and pbt.value > pbt_prev.value:
            return Flag("provision", "Chi phí dự phòng giảm mạnh",
                        f"Chi phí dự phòng giảm từ {ty(prev.value)} xuống {ty(cur.value)} trong khi LNTT tăng từ "
                        f"{ty(pbt_prev.value)} lên {ty(pbt.value)}.", _src(cur, prev, pbt, pbt_prev))
        return None
    prov = f.get("CF", "03", "ytd_cur")
    pbt = f.metric("IS", "pbt", "ytd_cur")
    if prov.value is None or pbt.value is None or pbt.value <= 0 or "phòng" not in (prov.source.label or ""):
        return None
    if prov.value < 0 and -prov.value > pbt.value / 5:
        return Flag("provision", "Hoàn nhập dự phòng lớn",
                    f"Lưu chuyển tiền tệ lũy kế ghi các khoản dự phòng {ty(prov.value)} (âm: hoàn nhập), bằng "
                    f"{vn(-prov.value / pbt.value * 100, 0)}% LNTT lũy kế {ty(pbt.value)}.", _src(prov, pbt))
    return None


# Dòng LCTT về mua, bán, mất hoặc giành quyền kiểm soát công ty con (so khớp trên tên đã bỏ dấu)
CONSOLIDATION_LINE = re.compile(r"quyen kiem soat|hop nhat kinh doanh|thanh ly.*(cong ty con|loi ich)|thoai von"
                                r"|(mua|ban|chuyen nhuong).*cong ty con")
MATERIAL_SHARE = Decimal("0.05")       # khoản bất thường dưới 5% LNTT thì không gắn cờ


def flag_consolidation(f: Facts) -> Flag | None:
    if f.template == "TCTD":
        return None
    pbt_ytd, pbt_q = f.metric("IS", "pbt", "ytd_cur").value, f.metric("IS", "pbt", "q_cur").value
    parts = []
    sources: list[Source] = []
    for (st, code), it in f.rows.items():
        if st != "CF" or not CONSOLIDATION_LINE.search(fold(clean_label(it.label or ""))):
            continue
        v = f.get("CF", code, "ytd_cur")
        if v.value and (not pbt_ytd or abs(v.value) >= abs(pbt_ytd) * MATERIAL_SHARE):
            parts.append(f"dòng \"{it.label.strip()}\" {'−' if v.value < 0 else ''}{ty(v.value)}")
            sources += _src(v)
    jv, jv_prev = f.metric("IS", "jv_profit", "q_cur"), f.metric("IS", "jv_profit", "q_prev_year")
    if jv.value is not None and jv_prev.value is not None and jv_prev.value > 0 and jv.value > 3 * jv_prev.value             and (not pbt_q or jv.value - jv_prev.value >= abs(pbt_q) * MATERIAL_SHARE * 2):
        parts.append(f"lãi từ công ty liên doanh, liên kết tăng từ {ty(jv_prev.value)} lên {ty(jv.value)}")
        sources += _src(jv, jv_prev)
    if not parts:
        return None
    return Flag("consolidation", "Có mua bán công ty con hoặc biến động lớn ở công ty liên kết",
                "Lưu chuyển tiền tệ hoặc KQKD có: " + "; ".join(parts) + ". Lợi nhuận có thể có khoản một lần.", sources)


def flag_cash(f: Facts) -> Flag | None:
    if f.template == "TCTD":
        return None
    npat, cfo = f.metric("IS", "npat", "ytd_cur"), f.metric("CF", "cfo", "ytd_cur")
    if npat.value is None or cfo.value is None or npat.value <= 0 or cfo.value >= 0:
        return None
    return Flag("cash", "Có lãi nhưng dòng tiền kinh doanh âm",
                f"LNST lũy kế {ty(npat.value)} nhưng lưu chuyển tiền thuần từ hoạt động kinh doanh lũy kế âm "
                f"{ty(cfo.value)}.", _src(npat, cfo))


COLUMN_NAMES = {"q_cur": "quý này", "q_prev_year": "cùng kỳ năm trước", "ytd_cur": "lũy kế",
                "ytd_prev_year": "lũy kế năm trước", "end_period": "cuối kỳ", "begin_year": "đầu năm"}
REVISED_MIN_SHARE = Decimal("0.005")   # chênh dưới 0,5% hoặc dưới 1 tỷ thì bỏ qua (làm tròn, sửa nhỏ)
REVISED_MIN_AMOUNT = Decimal(10**9)


def flag_revised(f: Facts, period_checks, labels) -> Flag | None:
    """Số chính khác giữa BCTC này và BCTC khác của cùng công ty (bản soát xét, kiểm toán hoặc trình bày lại)."""
    watched = {f.code("IS", m) for m in ("revenue", "toi", "pbt", "npat", "npat_parent")} - {None}
    lines = []
    sources: list[Source] = []
    for pc in period_checks:
        if pc.passed or pc.suspect_misread or pc.statement != "IS" or pc.key not in watched:
            continue
        if abs(pc.diff) < REVISED_MIN_AMOUNT or abs(pc.diff) < abs(pc.expected) * REVISED_MIN_SHARE:
            continue
        name = labels.get((pc.statement, pc.key), pc.key).strip()
        col = COLUMN_NAMES.get(pc.column, pc.column)
        if pc.kind == "same_date":
            text = f"{name} ({col}): BCTC quý ghi {ty(pc.later)}, BCTC bán niên/năm đã soát xét hoặc kiểm toán ghi {ty(pc.expected)}"
        elif pc.kind == "is_quarter":
            text = (f"{name} ({col}): BCTC này ghi {ty(pc.later)}, nhưng lấy lũy kế trừ đi lũy kế đã công bố ở BCTC quý "
                    f"trước thì ra {ty(pc.expected)}, tức số kỳ trước đã bị sửa")
        else:
            text = f"{name} ({col}): BCTC này ghi {ty(pc.later)}, BCTC quý liền kề ghi {ty(pc.expected)}"
        if pc.restated:
            text += " (BCTC có ghi \"trình bày lại\")"
        lines.append(text)
        sources += _src(f.get("IS", pc.key, pc.column))
    if not lines:
        return None
    return Flag("revised", "Số liệu bị sửa giữa các BCTC",
                "; ".join(lines) + ". Thường do kiểm toán soát xét hoặc công ty điều chỉnh; số mới nhất là số đáng tin hơn.",
                sources)


# ---- lắp thẻ --------------------------------------------------------------------------------------------------------

PLAN_NAMES = {"revenue": "doanh thu thuần", "toi": "tổng thu nhập hoạt động", "pbt": "lợi nhuận trước thuế",
              "npat": "lợi nhuận sau thuế", "npat_parent": "LNST của cổ đông công ty mẹ"}


def plan_progress(f: Facts, plans: dict[str, tuple[Decimal, str]]) -> dict | None:
    """Lũy kế kỳ này so với kế hoạch năm. plans: chỉ tiêu -> (kế hoạch, đồng; link nguồn)."""
    for metric in ("npat_parent", "npat", "pbt", "revenue", "toi"):
        if metric not in plans:
            continue
        target, url = plans[metric]
        v = f.metric("IS", metric, "ytd_cur")
        if v.value is None:
            v = f.metric("IS", metric, "q_cur")      # BCTC quý 1 có thể không in cột lũy kế
        if v.value is None or not target:
            continue
        return {"metric": metric, "name": PLAN_NAMES[metric], "plan": target, "ytd": v.value,
                "pct": v.value / target * 100, "pct_text": vn(v.value / target * 100, 1) + "%",
                "source_url": url, "source": v.source}
    return None


def build_card(document_id: int, ticker: str, year: int, period: str, record: dict,
               history: dict[tuple[int, str], Decimal] | None = None, evidence=None,
               plans: dict[str, tuple[Decimal, str]] | None = None) -> Card:
    f = Facts(document_id, record)
    kind = "TCTD" if f.template == "TCTD" else ("corporate" if f.template in ("TT200", "TT99") else None)
    if kind is None:
        return Card(document_id, ticker, year, period, f.template, [], [],
                    ["Thẻ chưa hỗ trợ mẫu BCTC này (công ty chứng khoán, bảo hiểm)"], supported=False)
    metrics = []
    for key, name in KEY_METRICS[kind]:
        vals = {col: f.metric("IS", key, col) for col in ("q_cur", "q_prev_year", "ytd_cur", "ytd_prev_year")}
        profit = key in ("npat_parent", "npat", "pbt", "gross_profit")
        m = Metric(key, name, **vals)
        m.q_change = change_text(vals["q_cur"].value, vals["q_prev_year"].value, profit)
        m.ytd_change = change_text(vals["ytd_cur"].value, vals["ytd_prev_year"].value, profit)
        metrics.append(m)

    flags: list[Flag] = []
    not_evaluated: list[str] = []
    for fn in (flag_sign_change, flag_non_core, flag_provision, flag_consolidation, flag_cash):
        if (x := fn(f)) is not None:
            flags.append(x)
    low = flag_low_base(f, history or {}, year, period)
    if isinstance(low, Flag):
        flags.append(low)
    elif isinstance(low, str):
        not_evaluated.append("Nền so sánh thấp: " + low)
    if evidence is not None:
        if (x := flag_revised(f, evidence.period_checks, evidence.cells.labels)) is not None:
            flags.append(x)
    else:
        not_evaluated.append("Số liệu khác giữa các BCTC: chưa có BCTC khác của cùng công ty để đối chiếu")
    return Card(document_id, ticker, year, period, f.template, metrics, flags, not_evaluated,
                plan=plan_progress(f, plans or {}))


def card_dict(card: Card) -> dict:
    """Dạng JSON cho API: số là chuỗi để giữ nguyên độ chính xác."""
    def conv(o):
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, dict):
            return {k: conv(v) for k, v in o.items()}
        if isinstance(o, list):
            return [conv(v) for v in o]
        return o
    return conv(asdict(card))
