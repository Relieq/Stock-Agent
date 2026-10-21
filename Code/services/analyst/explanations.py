"""Đọc công văn giải trình kết quả kinh doanh và đối chiếu từng con số công ty nêu với BCTC đã kiểm chứng.

Đúng nguyên tắc chung của Soi: mô hình chỉ chép nguyên văn (câu chính về lợi nhuận, từng nguyên nhân kèm khoản mục và
con số nếu có), mọi phép tính và kết luận khớp hay lệch do code làm trên số của BCTC đã kiểm chứng.

Một công văn có thể có nhiều phần (hợp nhất, riêng; quý, lũy kế). Với mỗi phần:
  * câu chính: số lợi nhuận kỳ này, cùng kỳ và % thay đổi công ty nêu, so với LNST (hoặc LNST của cổ đông công ty mẹ)
    trên BCTC cùng phạm vi, cùng kỳ;
  * nguyên nhân: nếu công ty nêu con số (% tăng giảm hoặc số tiền) cho một khoản mục (doanh thu, giá vốn, dự phòng...)
    thì so với thay đổi của khoản mục đó trên BCTC; nguyên nhân chỉ là lời (ví dụ "tối ưu chi phí") thì ghi là không
    kiểm được bằng số.
Phần riêng (BCTC công ty mẹ) chưa đối chiếu được vì hệ thống chỉ đọc BCTC hợp nhất hoặc BCTC duy nhất.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

LINE_ITEMS = ["revenue", "gross_profit", "cogs", "fin_income", "fin_expense", "fin_net", "interest_expense", "selling_expense",
              "admin_expense", "jv_profit", "other_income", "other_expense", "other_profit", "operating_profit", "pbt",
              "tax", "npat",
              "interest_income", "bank_interest_expense", "nii", "fee_income", "net_fee", "fx", "trading_sec",
              "invest_sec", "equity_income", "other_net", "non_interest_income", "toi", "opex", "provision", "other",
              "unspecified"]

# Khoản mục không có trong bảng chỉ tiêu chuẩn của thẻ (services/metrics/canonical.py): mã theo nhóm mẫu BCTC
EXTRA_CODES = {
    "corporate": {"other_income": "31", "other_expense": "32"},
    "TCTD": {"interest_income": "b.ii", "bank_interest_expense": "b.ie", "fee_income": "b.fi", "fx": "b.nfx",
             "trading_sec": "b.ntrading", "invest_sec": "b.ninv", "equity_income": "b.equity_inc", "other_net": "b.nother",
             "other_profit": "b.nother", "tax": "b.cit"},
    # Công ty chứng khoán (B02-CTCK): thẻ chưa hỗ trợ nên ghép thẳng mã
    "CTCK": {"revenue": "20", "opex": "40", "fin_income": "50", "fin_expense": "60", "admin_expense": "62",
             "operating_profit": "70", "other_profit": "80", "pbt": "90", "tax": "100", "npat": "200",
             "npat_parent": "201"},
}
_GROUP = {"TT200": "corporate", "TT99": "corporate", "TCTD": "TCTD", "CTCK": "CTCK"}

_STR = {"type": ["string", "null"]}
SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["consolidated", "separate", "unknown"]},
                    "period_kind": {"type": "string", "enum": ["quarter", "ytd", "half_year", "year", "other"]},
                    "metric_label": _STR,
                    "value_cur": _STR, "value_prev": _STR, "unit": _STR, "change_text": _STR,
                    "reasons": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "about": {"type": "string", "enum": ["company", "segment"]},
                                "line_item": {"type": "string", "enum": LINE_ITEMS},
                                "direction": {"type": "string", "enum": ["up", "down", "unknown"]},
                                "number_kind": {"type": "string", "enum": ["change", "level", "other", "none"]},
                                "pct": _STR, "amount": _STR, "amount_unit": _STR,
                            },
                            "required": ["text", "about", "line_item", "direction", "number_kind", "pct", "amount",
                                         "amount_unit"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["scope", "period_kind", "metric_label", "value_cur", "value_prev", "unit", "change_text",
                             "reasons"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["sections"],
    "additionalProperties": False,
}

PROMPT = """Ảnh sau là công văn giải trình biến động kết quả kinh doanh của một doanh nghiệp Việt Nam gửi UBCKNN, Sở
GDCK (có thể song ngữ Việt - Anh; chỉ dùng phần tiếng Việt). Chép NGUYÊN VĂN, không tính toán, không suy diễn.

Công văn thường có một hay nhiều phần, mỗi phần nói về một báo cáo (hợp nhất hoặc riêng/công ty mẹ) và một kỳ (quý,
lũy kế từ đầu năm, 6 tháng/bán niên, cả năm). Với MỖI phần, cho biết:
- scope: consolidated (hợp nhất), separate (riêng, công ty mẹ) hoặc unknown;
- period_kind: quarter (số của riêng quý), ytd (lũy kế từ đầu năm trong BCTC quý, ví dụ 9 tháng), half_year (BCTC bán
  niên/6 tháng), year (cả năm), other;
- metric_label: tên chỉ tiêu được giải trình, chép như in (thường là lợi nhuận sau thuế);
- value_cur, value_prev: số kỳ này và cùng kỳ năm trước, chép đúng như in (giữ dấu chấm, phẩy, ngoặc); không có thì null;
- unit: đơn vị như in (ví dụ "tỷ đồng", "triệu VND", "đồng"); change_text: câu tăng/giảm bao nhiêu như in, ví dụ "tăng 78%"
  (không chép câu trích quy định như "thay đổi từ 10% trở lên"; không có thì null);
- reasons: từng nguyên nhân công ty nêu, mỗi ý một phần tử:
  text: câu nguyên nhân chép ngắn gọn như in (không quá 300 ký tự);
  about: company nếu con số là của cả một dòng trên báo cáo đang giải trình; segment nếu nói về một mảng, chuỗi cửa hàng,
  sản phẩm, công ty con, thị trường riêng (ví dụ "chuỗi Điện Máy Xanh doanh thu tăng 34%"), hoặc chỉ một phần nhỏ bên
  trong một dòng (ví dụ "thu nhập lãi khác tăng 38,5 tỷ", "thu lãi cho vay tăng", "lãi từ thanh lý bất động sản");
  line_item: dòng trên báo cáo kết quả kinh doanh mà nguyên nhân nói tới, chọn dòng chi tiết nhất đúng với câu:
  doanh nghiệp: revenue (doanh thu thuần), gross_profit (lợi nhuận gộp), cogs (giá vốn), fin_income (doanh thu hoạt
  động tài chính), fin_expense (chi phí tài chính), fin_net (thu nhập tài chính thuần = doanh thu tài chính trừ chi phí
  tài chính), interest_expense (trong đó chi phí lãi vay), selling_expense (chi phí
  bán hàng), admin_expense (chi phí quản lý doanh nghiệp), jv_profit (lãi/lỗ công ty liên doanh, liên kết), other_income
  (thu nhập khác), other_expense (chi phí khác), other_profit (lợi nhuận khác), operating_profit (lợi nhuận thuần từ hoạt
  động kinh doanh), pbt (lợi nhuận trước thuế), tax (thuế TNDN), npat (lợi nhuận sau thuế);
  ngân hàng: interest_income (thu nhập lãi và các khoản thu nhập tương tự), bank_interest_expense (chi phí lãi), nii (thu
  nhập lãi thuần), fee_income (thu nhập từ hoạt động dịch vụ), net_fee (lãi thuần từ dịch vụ), fx (lãi thuần ngoại hối),
  trading_sec (lãi thuần chứng khoán kinh doanh), invest_sec (lãi thuần chứng khoán đầu tư), equity_income (thu nhập góp
  vốn, mua cổ phần), other_net (lãi thuần hoạt động khác), non_interest_income (thu nhập ngoài lãi, tức thu nhập từ mọi
  hoạt động ngoài cho vay, có ngân hàng gọi là "thu nhập từ các hoạt động còn lại"), toi (tổng thu nhập hoạt động), opex
  (chi phí hoạt động),
  provision (chi phí dự phòng rủi ro tín dụng);
  công ty chứng khoán: revenue (cộng doanh thu hoạt động), opex (cộng chi phí hoạt động), fin_income (cộng doanh thu
  hoạt động tài chính), fin_expense (cộng chi phí tài chính), admin_expense (chi phí quản lý công ty chứng khoán),
  other_profit (kết quả hoạt động khác);
  other (dòng khác), unspecified (không gắn với dòng nào, ví dụ chiến lược, thị trường, dư nợ, sản lượng);
  number_kind: con số công ty nêu (pct, amount) là gì: change nếu là mức tăng/giảm của chính dòng đó so với cùng kỳ năm
  trước (ví dụ "doanh thu tăng 29%", "chi phí dự phòng giảm 300 tỷ"); level nếu là giá trị kỳ này của dòng đó (ví dụ
  "doanh thu đạt 46.462 tỷ"); other nếu so với kế hoạch, với quý trước, hay là sản lượng, dư nợ, số cửa hàng, tỷ lệ;
  none nếu không có con số;
  direction: up nếu khoản mục tăng, down nếu giảm, unknown;
  pct: phần trăm tăng/giảm của khoản mục nếu công ty nêu, chép như in (ví dụ "29%"), không có thì null;
  amount, amount_unit: số tiền tăng/giảm hoặc giá trị của khoản mục nếu công ty nêu, chép như in, không có thì null.
Mỗi ảnh có nhãn "Trang N" trước nó. Bỏ qua trang bìa, phần tiếng Anh và chữ ký."""


# ---- số như in -> Decimal -------------------------------------------------------------------------------------------

UNITS = (("nghìn tỷ", Decimal(10) ** 12), ("ngàn tỷ", Decimal(10) ** 12), ("tỷ", Decimal(10) ** 9),
         ("triệu", Decimal(10) ** 6), ("nghìn", Decimal(10) ** 3), ("ngàn", Decimal(10) ** 3),
         ("đồng", Decimal(1)), ("vnd", Decimal(1)), ("vnđ", Decimal(1)))


def unit_multiplier(unit: str | None) -> Decimal | None:
    u = (unit or "").lower()
    return next((m for name, m in UNITS if name in u), None)


def parse_number(text: str | None) -> tuple[Decimal, Decimal] | None:
    """Số kiểu Việt Nam như in -> (giá trị, sai số làm tròn theo chữ số cuối). "2.757,6" -> (2757.6, 0.05);
    "(1.547,8)" và "-1.547,8" là số âm; "1,547.8" (kiểu Anh) cũng đọc được khi có cả hai dấu."""
    if not text:
        return None
    s = text.strip().replace(" ", "").replace(" ", "")
    neg = s.startswith("(") and s.endswith(")") or s.startswith("-") or s.startswith("−")
    s = re.sub(r"[^\d.,]", "", s)
    if not s or not re.search(r"\d", s):
        return None
    if "." in s and "," in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
    elif "," in s:
        dec = "," if not re.fullmatch(r"\d{1,3}(,\d{3})+", s) else None
    elif "." in s:
        dec = "." if not re.fullmatch(r"\d{1,3}(\.\d{3})+", s) else None
    else:
        dec = None
    if dec:
        whole, _, frac = s.rpartition(dec)
        whole = re.sub(r"[.,]", "", whole)
        s, places = f"{whole}.{frac}", len(frac)
    else:
        s, places = re.sub(r"[.,]", "", s), 0
    try:
        v = Decimal(s)
    except InvalidOperation:
        return None
    return (-v if neg else v), Decimal(5) / Decimal(10) ** (places + 1)


# Câu trích quy định làm công văn ("thay đổi từ 10% trở lên so với cùng kỳ"), không phải mức thay đổi thật (BSR)
_THRESHOLD = re.compile(r"trở lên|từ\s*\d+\s*%|trên\s*\d+\s*%|tối thiểu", re.IGNORECASE)


_AT_LEAST = re.compile(r"\b(hơn|trên|vượt)\s*\d", re.IGNORECASE)


def parse_pct(text: str | None) -> Decimal | None:
    if _THRESHOLD.search(text or ""):
        return None
    m = re.search(r"(\d+(?:[.,]\d+)*)\s*%", text or "")
    if not m:
        return None
    parsed = parse_number(m.group(1))      # "2.324%" (VJC) là hai nghìn ba trăm hai mươi bốn phần trăm
    return abs(parsed[0]) if parsed else None


# ---- đối chiếu --------------------------------------------------------------------------------------------------------

COLUMNS = {"quarter": ("q_cur", "q_prev_year"), "ytd": ("ytd_cur", "ytd_prev_year"),
           "half_year": ("ytd_cur", "ytd_prev_year"), "year": ("ytd_cur", "ytd_prev_year")}
EXPENSES = {"cogs", "fin_expense", "interest_expense", "selling_expense", "admin_expense", "tax", "tax_current",
            "tax_deferred", "opex", "provision",
            "other_expense", "bank_interest_expense"}


@dataclass
class Check:
    what: str                    # "lợi nhuận kỳ này", "% thay đổi", nguyên nhân...
    verdict: str                 # khớp / lệch / không kiểm được
    stated: str = ""
    bctc: str = ""
    note: str = ""


@dataclass
class SectionResult:
    scope: str
    period_kind: str
    label: str | None
    checks: list[Check] = field(default_factory=list)


def _value(facts, metric: str, column: str) -> Decimal | None:
    if metric == "non_interest_income":
        # Thu nhập ngoài lãi của ngân hàng (STB: "thu nhập từ các hoạt động còn lại"): tổng thu nhập hoạt động trừ thu
        # nhập lãi thuần
        toi, nii = facts.metric("IS", "toi", column).value, facts.metric("IS", "nii", column).value
        return None if toi is None or nii is None else toi - nii
    if metric in ("tax_current", "tax_deferred"):
        group = _GROUP.get(getattr(facts, "template", None))
        code = {("corporate", "tax_current"): "51", ("corporate", "tax_deferred"): "52",
                ("TCTD", "tax_current"): "b.cit_cur", ("TCTD", "tax_deferred"): "b.cit_def"}.get((group, metric))
        return facts.get("IS", code, column, True).value if code else None
    if metric == "tax" and _GROUP.get(getattr(facts, "template", None)) == "corporate":
        # Chi phí thuế TNDN của doanh nghiệp = hiện hành (51) + hoãn lại (52)
        cur, dfr = facts.get("IS", "51", column, True).value, facts.get("IS", "52", column, True).value
        return None if cur is None and dfr is None else (cur or 0) + (dfr or 0)
    if metric == "fin_net":
        # "Thu nhập tài chính thuần" (MCH): doanh thu tài chính trừ chi phí tài chính, không in thành một dòng
        inc, exp = _value(facts, "fin_income", column), _value(facts, "fin_expense", column)
        return None if inc is None or exp is None else inc - abs(exp)
    code = EXTRA_CODES.get(_GROUP.get(getattr(facts, "template", None), ""), {}).get(metric)
    if code is None:
        return facts.metric("IS", metric, column).value
    return facts.get("IS", code, column, metric in EXPENSES).value


def _pair(facts, metric: str, period_kind: str) -> tuple[Decimal | None, Decimal | None]:
    """(kỳ này, cùng kỳ) của chỉ tiêu trên BCTC (đồng). BCTC bán niên/năm có thể ghi số cả kỳ ở cột quý."""
    cur_col, prev_col = COLUMNS.get(period_kind, (None, None))
    if cur_col is None:
        return None, None
    cur, prev = _value(facts, metric, cur_col), _value(facts, metric, prev_col)
    if cur is None and period_kind in ("half_year", "year"):
        cur, prev = _value(facts, metric, "q_cur"), _value(facts, metric, "q_prev_year")
    return cur, prev


def _pct_change(cur: Decimal, prev: Decimal) -> Decimal | None:
    """% thay đổi có dấu theo cách công văn hay tính: (kỳ này - cùng kỳ) / |cùng kỳ|; chuyển từ lãi sang lỗ ra số âm
    lớn hơn 100% (ví dụ lãi ngoại hối 119,5 tỷ thành lỗ 419,8 tỷ: -451%)."""
    return (cur - prev) / abs(prev) * 100 if prev else None


def _tolerance(value: Decimal, rounding: Decimal) -> Decimal:
    """Sai số cho phép: làm tròn theo chữ số cuối như in, và 0,1% giá trị vì công ty hay cộng các số đã làm tròn."""
    return max(rounding * Decimal("1.01"), abs(value) * Decimal("0.001"))


def _folded(text: str | None) -> str:
    import unicodedata
    t = unicodedata.normalize("NFD", (text or "").lower()).replace("đ", "d")
    return "".join(c for c in t if not unicodedata.combining(c))


def _headline_metrics(label: str | None) -> tuple[str, ...]:
    """Chỉ tiêu BCTC để so câu chính: phần nói về doanh thu (VJC bán niên 2026 giải trình cả doanh thu) so với doanh thu
    (ngân hàng: tổng thu nhập hoạt động), còn lại so với lợi nhuận."""
    import unicodedata
    folded = "".join(c for c in unicodedata.normalize("NFD", (label or "").lower()) if not unicodedata.combining(c))
    if "doanh thu" in folded and "loi nhuan" not in folded:
        return ("revenue", "toi")
    return ("npat", "npat_parent", "pbt")


def _vn(x: Decimal, places: int = 1) -> str:
    return f"{x:,.{places}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _ty(v: Decimal) -> str:
    return _vn(v / Decimal(10**9)) + " tỷ"


def _with_unit(value: str, unit: str | None) -> str:
    return value if not unit or unit.lower() in value.lower() else f"{value} {unit}"


def check_section(sec: dict, facts) -> SectionResult:
    """Đối chiếu một phần của công văn với BCTC (`facts`: services.metrics.card.Facts của BCTC cùng phạm vi, kỳ; None
    nếu không có)."""
    res = SectionResult(sec["scope"], sec["period_kind"], sec.get("metric_label"))
    if facts is None:
        res.checks.append(Check("cả phần", "không kiểm được", note="chưa có BCTC đã kiểm chứng cùng phạm vi, cùng kỳ"))
        return res
    mult = unit_multiplier(sec.get("unit"))
    stated = {k: parse_number(sec.get(k)) for k in ("value_cur", "value_prev")}
    metrics = _headline_metrics(sec.get("metric_label"))
    word = "doanh thu" if metrics[0] == "revenue" else "lợi nhuận"
    profits = {m: _pair(facts, m, sec["period_kind"]) for m in metrics}
    for key, idx, what in (("value_cur", 0, f"{word} kỳ này"), ("value_prev", 1, f"{word} cùng kỳ")):
        if stated[key] is None or mult is None:
            continue
        v = stated[key][0] * mult
        tol = _tolerance(v, stated[key][1] * mult)
        hit = next((m for m, pair in profits.items() if pair[idx] is not None and abs(pair[idx] - v) <= tol), None)
        best = next((pair[idx] for pair in profits.values() if pair[idx] is not None), None)
        res.checks.append(Check(what, "khớp" if hit else ("lệch" if best is not None else "không kiểm được"),
                                _with_unit(sec.get(key), sec.get("unit")), _ty(best) if best is not None else "",
                                {"npat": "LNST", "npat_parent": "LNST cổ đông công ty mẹ", "pbt": "LNTT",
                                 "revenue": "doanh thu", "toi": "tổng thu nhập hoạt động"}.get(hit, "")))
    pct = parse_pct(sec.get("change_text"))
    if pct is not None:
        changes = {m: _pct_change(*pair) for m, pair in profits.items() if None not in pair}
        ok = any(c is not None and abs(abs(c) - pct) <= Decimal("1") for c in changes.values())
        note = ""
        # Công ty tính % từ chính các số đã làm tròn nó nêu (VJC quý 4/2025: 509 tỷ so với 21 tỷ ra 2.324%, số chưa làm
        # tròn ra 2.274,5%): chấp nhận khi hai số đó đã khớp BCTC
        values_ok = sum(c.verdict == "khớp" for c in res.checks if c.what.endswith(("kỳ này", "cùng kỳ"))) == 2
        if not ok and values_ok and stated["value_prev"] and stated["value_prev"][0]:
            own = _pct_change(stated["value_cur"][0], stated["value_prev"][0])
            if own is not None and abs(abs(own) - pct) <= Decimal("1"):
                ok, note = True, "khớp % tính từ các số đã làm tròn công ty nêu"
        main = next((c for c in changes.values() if c is not None), None)
        res.checks.append(Check(f"% thay đổi {word}", "khớp" if ok else ("lệch" if main is not None else "không kiểm được"),
                                sec["change_text"], (("+" if main >= 0 else "−") + _vn(abs(main)) + "%")
                                if main is not None else "", note))
    for r in sec.get("reasons", []):
        res.checks.append(check_reason(r, facts, sec["period_kind"]))
    return res


def check_reason(r: dict, facts, period_kind: str) -> Check:
    item, text = r["line_item"], r["text"][:120]
    if item == "tax" and "hien hanh" in _folded(text):
        item = "tax_current"    # "chi phí thuế TNDN hiện hành tăng 7.744 tỷ" (VIC, VPL): chỉ phần hiện hành
    elif item == "tax" and "hoan lai" in _folded(text):
        item = "tax_deferred"
    if _GROUP.get(getattr(facts, "template", None)) == "CTCK" and item == "fin_income" and _folded(text).startswith(
            "doanh thu hoat dong") and "tai chinh" not in _folded(text):
        item = "revenue"        # công ty chứng khoán: "doanh thu hoạt động" là dòng 20, mô hình hay ghép nhầm (TCX)
    if r.get("about") == "segment":
        return Check(text, "không kiểm được", r.get("pct") or r.get("amount") or "",
                     note="số của một mảng, chuỗi hay công ty con: BCTC không tách")
    if "hoat dong con lai" in _folded(text) and item != "non_interest_income":
        # STB: "chi từ các hoạt động còn lại" = dự phòng + chi phí hoạt động + thuế gộp lại, BCTC không có dòng này
        return Check(text, "không kiểm được", r.get("pct") or r.get("amount") or "",
                     note="nhóm khoản mục do công ty tự gộp, BCTC không có dòng tương ứng")
    if r.get("number_kind") == "other":
        return Check(text, "không kiểm được", r.get("pct") or r.get("amount") or "",
                     note="con số không phải mức thay đổi so với cùng kỳ (kế hoạch, sản lượng, dư nợ...)")
    pct = parse_pct(r.get("pct"))
    amount = parse_number(r.get("amount"))
    if item in ("other", "unspecified") or (pct is None and amount is None):
        if item not in ("other", "unspecified") and r["direction"] != "unknown":
            cur, prev = _pair(facts, item, period_kind)
            if cur is not None and prev is not None and cur != prev:
                if item.startswith("tax"):
                    # Thuế: số dương là chi phí; "thu nhập thuế hoãn lại tăng" (VIC) nghĩa là số thuế giảm
                    up = cur < prev if "thu nhap thue" in _folded(text) else cur > prev
                else:
                    up = abs(cur) > abs(prev) if item in EXPENSES else cur > prev
                same = up == (r["direction"] == "up")
                return Check(text, "khớp chiều" if same else "ngược chiều", r["direction"],
                             f"{_ty(prev)} -> {_ty(cur)}", "chỉ so chiều tăng/giảm, công ty không nêu số")
        return Check(text, "không kiểm được", note="nguyên nhân bằng lời, không có số hoặc khoản mục")
    first = None
    # Công văn quý 4 hay nói số cả năm trong phần quý (MWG, STB): thử cột của kỳ đã ghi trước, sau đó cột kia
    for kind in (period_kind, OTHER_KIND.get(period_kind)):
        if kind is None:
            continue
        check = _compare_reason(r, text, pct, amount, *_pair(facts, item, kind))
        if check is None:
            continue
        if kind != period_kind and check.verdict == "khớp":
            check.note = "khớp số lũy kế (công văn ghi trong phần quý)" if kind == "ytd" else "khớp số riêng quý"
            return check
        first = first or check
        if check.verdict == "khớp":
            return check
    return first or Check(text, "không kiểm được", r.get("pct") or r.get("amount") or "", note=f"BCTC không có {item}")


OTHER_KIND = {"quarter": "ytd", "ytd": "quarter"}


def _compare_reason(r: dict, text: str, pct, amount, cur, prev) -> Check | None:
    if cur is None or prev is None:
        return None
    bctc_pct = _pct_change(cur, prev)
    if pct is not None and bctc_pct is not None:
        if _AT_LEAST.search(r["pct"] or "") or _AT_LEAST.search(text):
            ok = abs(bctc_pct) >= pct - Decimal("1")          # "tăng hơn 20%" (VNM): ngưỡng dưới
        else:
            ok = abs(abs(bctc_pct) - pct) <= Decimal("1")
        return Check(text, "khớp" if ok else "lệch", r["pct"],
                     f"{'+' if bctc_pct >= 0 else '−'}{_vn(abs(bctc_pct))}% ({_ty(prev)} -> {_ty(cur)})")
    mult = unit_multiplier(r.get("amount_unit"))
    if amount is not None and mult is not None:
        v = abs(amount[0]) * mult
        tol = _tolerance(v, amount[1] * mult)
        delta, level = abs(cur - prev), abs(cur)      # hiệu có dấu: khoản mục đổi từ lãi sang lỗ (ACB quý 2/2026)
        kind = r.get("number_kind")
        ok = (kind != "level" and abs(delta - v) <= tol) or (kind != "change" and abs(level - v) <= tol)
        return Check(text, "khớp" if ok else "lệch", _with_unit(r["amount"], r.get("amount_unit")),
                     f"thay đổi {_ty(cur - prev)}, kỳ này {_ty(cur)}")
    return Check(text, "không kiểm được", note="số không đọc được đơn vị")


MAX_PAGES = 6
PAGE_LONG_SIDE = 1600       # công văn chữ to hơn bảng số: ảnh vừa phải là đọc được


def facts_for(conn, ticker: str, year: int, period: str, scope: str, period_kind: str):
    """BCTC đã kiểm chứng ứng với một phần của công văn: quý/lũy kế -> BCTC quý cùng kỳ; bán niên -> BCTC bán niên (phần
    nói về quý 2 thì BCTC quý 2); năm -> BCTC năm. Phần riêng (công ty mẹ): chưa có."""
    from services.extraction.pipeline import _load_record
    from services.metrics.card import Facts
    if scope == "separate":
        return None
    if period == "H1" and period_kind == "quarter":
        doc_type, per = "fs_quarter", "Q2"
    elif period == "H1":
        doc_type, per = "fs_semiannual", "H1"
    elif period == "FY":
        doc_type, per = "fs_annual", "FY"
    else:
        doc_type, per = "fs_quarter", period
    row = conn.execute(
        """SELECT id FROM documents WHERE ticker = %s AND fiscal_year = %s AND fiscal_period = %s AND doc_type = %s
             AND content_kind = 'full' AND scope IN ('consolidated', 'standalone') AND status IN ('verified', 'approved')
             AND owner_user_id IS NULL AND duplicate_of IS NULL AND NOT is_amended
           ORDER BY (scope = 'consolidated') DESC LIMIT 1""", (ticker, year, per, doc_type)).fetchone()
    if row is None:
        return None
    return Facts(row[0], _load_record(conn, row[0]))


def read_letter(client, path) -> dict:
    from services.extraction.sources import candidates, open_pdf, render_page
    doc = open_pdf(candidates(path)[0])
    images = [(f"Trang {p}", render_page(doc, p, PAGE_LONG_SIDE)) for p in range(1, min(doc.page_count, MAX_PAGES) + 1)]
    return client.json_from_images(PROMPT, images, SCHEMA, "explanation_read")


def load_letter(conn, client, doc_id: int) -> dict:
    """Kết quả đọc công văn: lấy từ Data/raw/explanations/<id>.json nếu đã đọc, chưa thì đọc (khoảng 0,0016 USD) và lưu."""
    import json
    from services.ingestion.registry import raw_data_dir
    cache = raw_data_dir() / "explanations" / f"{doc_id}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    key = conn.execute("SELECT storage_key FROM document_files WHERE document_id = %s ORDER BY downloaded_at DESC LIMIT 1",
                       (doc_id,)).fetchone()
    if key is None:
        return {"sections": []}
    data = read_letter(client, raw_data_dir() / key[0])
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data
