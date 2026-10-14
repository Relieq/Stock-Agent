"""Ràng buộc kế toán khai báo theo mẫu BCTC và phiên bản (architecture.md mục 4.2).

Mỗi ràng buộc: lhs = tổng có dấu của các mã ở rhs, áp cho từng cột số (kỳ này, cùng kỳ, đầu năm...).
  * `gate=True`: ràng buộc chắc chắn theo mẫu biểu; trượt thì tài liệu không được coi là đã kiểm chứng.
  * `gate=False`: chưa đối chiếu với mẫu biểu gốc; chỉ ghi lại để theo dõi, không chặn.

Mẫu TT200 (Thông tư 200/2014, B01/B02/B03-DN và bản hợp nhất theo TT202) viết theo mẫu biểu.
Mẫu TT99 (Thông tư 99/2025): các dòng tổng và dòng con BCĐKT, LCTT gián tiếp khai báo theo cấu trúc mã quan sát trên
BCTC năm 2026 và chỉ đưa vào nhóm bắt buộc sau khi khớp trên dữ liệu thật (eval/rule_fit.py).
Mẫu ngân hàng (TCTD) không in mã số kiểu DN thường: ánh xạ theo tên chỉ tiêu ở bank.py.
Mẫu công ty chứng khoán (CTCK) in mã số; mới khai báo các dòng tổng.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Rule:
    id: str
    statement: str                     # BS / IS / CF
    lhs: str
    rhs: tuple[tuple[int, str], ...]   # ((+1, "110"), (-1, "02"), ...)
    gate: bool = True
    when_present: str | None = None    # chỉ áp dụng khi tài liệu có mã này
    when_absent: str | None = None     # chỉ áp dụng khi tài liệu không có mã này
    # Cộng thêm các dòng có hậu tố chữ của mã trong nhóm (ví dụ LCTT "26b": tiền của công ty con khi mất quyền
    # kiểm soát, doanh nghiệp tự thêm vào giữa nhóm đầu tư)
    include_suffixed: bool = False
    # Mã lấy giá trị tuyệt đối và giữ nguyên dấu của công thức, không theo quy ước dấu của tài liệu
    # (ví dụ lợi ích cổ đông không kiểm soát: ngân hàng in trong ngoặc như một khoản trừ dù chi phí in số dương)
    abs_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CrossRule:
    """Ràng buộc giữa hai báo cáo; mỗi vế chỉ rõ (báo cáo, mã, cột)."""
    id: str
    left: tuple[str, str, str]
    right: tuple[str, str, str]
    gate: bool = True


@dataclass(frozen=True)
class RuleSet:
    template: str
    total_assets_code: str
    rules: tuple[Rule, ...]
    cross_rules: tuple[CrossRule, ...] = ()
    # Các khoản chi phí dùng để nhận ra quy ước dấu của KQKD (chi phí in số dương hay số âm trong ngoặc)
    expense_codes: tuple[str, ...] = ("11", "25", "26")


def rule(statement: str, lhs: str, *codes: str, id: str | None = None, **kw) -> Rule:
    """rule("IS", "10", "01", "-02") nghĩa là IS.10 = 01 - 02."""
    terms = tuple((-1, c[1:]) if c.startswith("-") else (1, c) for c in codes)
    return Rule(id=id or f"{statement}_{lhs}", statement=statement, lhs=lhs, rhs=terms, **kw)


def codes(start: int, end: int, width: int = 3) -> list[str]:
    return [str(i).zfill(width) for i in range(start, end + 1)]


def _no_gate(rules) -> tuple:
    return tuple(replace(r, gate=False) for r in rules)


_TT200_BS = (
    rule("BS", "100", "110", "120", "130", "140", "150"),
    rule("BS", "110", "111", "112"),
    rule("BS", "120", "121", "122", "123"),
    rule("BS", "130", "131", "132", "133", "134", "135", "136", "137", "139"),
    rule("BS", "140", "141", "149"),
    rule("BS", "150", "151", "152", "153", "154", "155"),
    rule("BS", "200", "210", "220", "230", "240", "250", "260"),
    rule("BS", "210", *codes(211, 216), "219"),
    rule("BS", "220", "221", "224", "227"),
    rule("BS", "221", "222", "223"),
    rule("BS", "224", "225", "226"),
    rule("BS", "227", "228", "229"),
    rule("BS", "230", "231", "232"),
    rule("BS", "240", "241", "242"),
    rule("BS", "250", *codes(251, 255)),
    rule("BS", "260", "261", "262", "263", "268", "269"),   # 269: lợi thế thương mại (BCTC hợp nhất)
    rule("BS", "270", "100", "200"),
    rule("BS", "300", "310", "330"),
    rule("BS", "310", *codes(311, 324)),
    rule("BS", "330", *codes(331, 343)),
    rule("BS", "400", "410", "430"),
    rule("BS", "410", *codes(411, 422), "429"),   # 429: lợi ích cổ đông không kiểm soát (BCTC hợp nhất)
    rule("BS", "430", "431", "432"),
    rule("BS", "440", "300", "400"),
    rule("BS", "270", "440", id="BS_270_eq_440"),
    # Chỉ kiểm khi tài liệu tách dòng a/b
    rule("BS", "411", "411a", "411b", when_present="411a"),
    rule("BS", "421", "421a", "421b", when_present="421a"),
)

_IS_TOTALS = (
    rule("IS", "10", "01", "-02"),
    rule("IS", "20", "10", "-11"),
    rule("IS", "40", "31", "-32"),
    rule("IS", "50", "30", "40"),
    rule("IS", "60", "50", "-51", "-52"),
    rule("IS", "60", "61", "62", id="IS_60_split", when_present="61"),  # BCTC hợp nhất
)

# 24: phần lãi/lỗ trong công ty liên doanh, liên kết (chỉ có ở BCTC hợp nhất; không có thì tính là 0)
_TT200_IS = _IS_TOTALS + (rule("IS", "30", "20", "21", "-22", "24", "-25", "-26"),)

_CF = (
    # Phương pháp gián tiếp có dòng 08; phương pháp trực tiếp thì 20 = 01..07
    rule("CF", "08", *codes(1, 7, 2), when_present="08", include_suffixed=True),
    rule("CF", "20", "08", *codes(9, 17, 2), when_present="08", include_suffixed=True),
    rule("CF", "20", *codes(1, 7, 2), id="CF_20_direct", when_absent="08", include_suffixed=True),
    # 28: tiền chi lợi ích cổ đông không kiểm soát, có ở TT99 và một số BCTC lập theo TT200 (MWG quý 4/2025)
    rule("CF", "30", *codes(21, 28, 2), include_suffixed=True),
    rule("CF", "40", *codes(31, 36, 2), include_suffixed=True),
    rule("CF", "50", "20", "30", "40"),
    rule("CF", "70", "50", "60", "61", "62"),   # 62: chênh lệch quy đổi BCTC công ty con nước ngoài (VNM)
)

_CASH_CROSS = (
    CrossRule("X_cash_end", left=("BS", "110", "end_period"), right=("CF", "70", "ytd_cur")),
    CrossRule("X_cash_begin", left=("BS", "110", "begin_year"), right=("CF", "60", "ytd_cur")),
)

TT200 = RuleSet(
    template="TT200",
    total_assets_code="270",
    rules=_TT200_BS + _TT200_IS + _CF,
    cross_rules=_CASH_CROSS,
)

# Dòng con BCĐKT theo TT99: cấu trúc mã quan sát trên 43 BCTC năm 2026 đã đọc (150/230: tài sản sinh học; 160: tài sản
# ngắn hạn khác; 270: tài sản dài hạn khác; 279: lợi thế thương mại; 420: LNST chưa phân phối). Mỗi quy tắc chỉ đưa vào
# nhóm bắt buộc sau khi khớp trên mọi BCTC có đủ số hạng, trừ các ô đọc sai (đo bằng eval/rule_fit.py, 14/10/2026).
_TT99_BS_DETAIL = (
    rule("BS", "120", *codes(121, 125)),
    rule("BS", "130", *codes(131, 139)),
    rule("BS", "140", "141", "142"),
    rule("BS", "150", *codes(151, 154)),
    rule("BS", "160", *codes(161, 169)),
    rule("BS", "210", *codes(211, 219)),
    rule("BS", "220", "221", "224", "227"),
    rule("BS", "221", "222", "223"),
    rule("BS", "224", "225", "226"),
    rule("BS", "227", "228", "229"),
    rule("BS", "240", "241", "242"),
    rule("BS", "250", *codes(251, 259)),
    rule("BS", "260", *codes(261, 269)),
    rule("BS", "270", *codes(271, 279), when_present="280"),
    rule("BS", "310", *codes(311, 329)),
    rule("BS", "330", *codes(331, 349)),
    rule("BS", "410", *codes(411, 429), when_present="410"),
    rule("BS", "400", *codes(411, 429), "430", id="BS_400_items", when_absent="410"),
    rule("BS", "411", "411a", "411b", when_present="411a"),
    rule("BS", "420", "420a", "420b", when_present="420a"),
    rule("BS", "421", "421a", "421b", when_present="421a"),
)

TT99 = RuleSet(
    template="TT99",
    total_assets_code="280",
    rules=(
        rule("BS", "280", "100", "200"),
        rule("BS", "280", "440", id="BS_280_eq_440"),
        # Một số BCTC dùng cấu trúc TT99 nhưng vẫn in mã tổng tài sản là 270 (ví dụ HPG quý 2/2026)
        rule("BS", "270", "100", "200", id="BS_270_total", when_absent="280"),
        rule("BS", "270", "440", id="BS_270_total_eq_440", when_absent="280"),
        # Dòng con theo cấu trúc quan sát trên BCTC năm 2026 (150: tài sản sinh học ngắn hạn, 160: tài sản ngắn hạn
        # khác, 230: tài sản sinh học dài hạn); bắt buộc từ 14/10/2026 sau khi khớp trên mọi BCTC trừ các ô đọc sai
        rule("BS", "100", "110", "120", "130", "140", "150", "160"),
        rule("BS", "200", "210", "220", "230", "240", "250", "260", "270", when_present="280"),
        rule("BS", "200", "210", "220", "230", "240", "250", "260", id="BS_200_total270", gate=False,
             when_absent="280"),
        rule("BS", "300", "310", "330"),
        rule("BS", "400", "410", "430"),
        rule("BS", "440", "300", "400"),
        *_TT99_BS_DETAIL,
        *_IS_TOTALS,
        # 27: lãi/lỗ trong công ty liên doanh, liên kết (khớp đúng cả 4 cột trên BCTC hợp nhất FPT quý 2/2026).
        # Chưa bắt buộc: trượt có hệ thống ở GAS, HPG, SAB, GVR (cấu trúc dòng 21-27 khác nhau giữa các công ty).
        rule("IS", "30", "20", "21", "22", "-23", "-25", "-26", "27", gate=False),
        # LCTT gián tiếp và các dòng tổng: bắt buộc từ 14/10/2026 (khớp trên mọi BCTC trừ ô đọc sai). Phương pháp trực
        # tiếp chưa bắt buộc (SAB in mã khác mẫu).
        *(r for r in _CF if r.id != "CF_20_direct"),
        *_no_gate(r for r in _CF if r.id == "CF_20_direct"),
        rule("BS", "110", "111", "112"),
    ),
    # Tiền đầu kỳ trên LCTT có thể khác số đầu năm trên BCĐKT thật (GAS lệch 15,5 triệu ở cả hai quý: ảnh hưởng tỷ giá)
    cross_rules=(_CASH_CROSS[0], replace(_CASH_CROSS[1], gate=False)),
)

# Ngân hàng (TCTD): mã chuẩn b.* gán theo tên chỉ tiêu ở services/extraction/bank.py
BANK_INCOME_PARTS = ("b.nii", "b.nfee", "b.nfx", "b.ntrading", "b.ninv", "b.nother", "b.equity_inc")
TCTD = RuleSet(
    template="TCTD",
    total_assets_code="b.ta",
    expense_codes=("b.ie", "b.fe", "b.opex"),
    rules=(
        rule("BS", "b.ta", "b.cash", "b.sbv", "b.interbank", "b.trading_sec", "b.deriv_asset", "b.loans",
             "b.debt_purchase", "b.inv_sec", "b.lt_invest", "b.fixed_assets", "b.inv_property", "b.other_assets",
             id="BS_bank_assets"),
        rule("BS", "b.tl", "b.gov", "b.interbank_liab", "b.cust_dep", "b.deriv_liab", "b.trust_funds", "b.papers",
             "b.other_liab", id="BS_bank_liabilities"),
        rule("BS", "b.tle", "b.tl", "b.te", id="BS_bank_tle", when_present="b.tl"),
        # Ngân hàng không in dòng "Tổng nợ phải trả" (ví dụ BID): cộng thẳng các mục nợ phải trả
        rule("BS", "b.tle", "b.gov", "b.interbank_liab", "b.cust_dep", "b.deriv_liab", "b.trust_funds", "b.papers",
             "b.other_liab", "b.te", id="BS_bank_tle_items", when_absent="b.tl"),
        rule("BS", "b.ta", "b.tle", id="BS_bank_ta_eq_tle"),
        rule("IS", "b.nii", "b.ii", "-b.ie", id="IS_bank_nii"),
        rule("IS", "b.nfee", "b.fi", "-b.fe", id="IS_bank_nfee"),
        rule("IS", "b.nother", "b.oi", "-b.oe", id="IS_bank_nother"),
        rule("IS", "b.toi", *BANK_INCOME_PARTS, id="IS_bank_toi"),
        rule("IS", "b.ppop", "b.toi", "-b.opex", id="IS_bank_ppop", when_present="b.toi"),
        rule("IS", "b.ppop", *BANK_INCOME_PARTS, "-b.opex", id="IS_bank_ppop_parts", when_absent="b.toi"),
        rule("IS", "b.pbt", "b.ppop", "-b.prov", id="IS_bank_pbt"),
        rule("IS", "b.cit", "b.cit_cur", "b.cit_def", id="IS_bank_cit"),
        rule("IS", "b.npat", "b.pbt", "-b.cit", id="IS_bank_npat"),
        # Dấu của lợi ích cổ đông không kiểm soát không theo quy ước dấu chung của KQKD; lấy giá trị tuyệt đối.
        # Chưa bắt buộc vì lợi ích cổ đông không kiểm soát có thể âm thật (công ty con lỗ).
        rule("IS", "b.npat_parent", "b.npat", "-b.mi", id="IS_bank_parent", gate=False, abs_codes=("b.mi",)),
        rule("CF", "b.net", "b.cfo", "b.cfi", "b.cff", id="CF_bank_net"),
        rule("CF", "b.cash_end", "b.cash_begin", "b.net", "b.fx", id="CF_bank_cash_end"),
    ),
)

# Công ty chứng khoán (CTCK): mẫu B01/B02/B03-CTCK theo TT334/2016/TT-BTC. Các dòng tổng đã khớp trên BCTC SSI và TCX
# quý 2/2026 (riêng TCX lệch đúng ở 2 ô đọc sai, đã đối chiếu ảnh). LCTT của CTCK có thêm phần lưu chuyển tiền của
# khách hàng đánh mã lại từ 01, nên chỉ lần xuất hiện đầu của mỗi mã (phần của công ty) được dùng.
CTCK = RuleSet(
    template="CTCK",
    total_assets_code="270",
    expense_codes=("21", "40", "60"),
    rules=(
        rule("BS", "100", "110", "130"),
        rule("BS", "200", "210", "220", "230", "240", "250"),
        rule("BS", "270", "100", "200"),
        rule("BS", "300", "310", "340"),
        rule("BS", "440", "300", "400"),
        rule("BS", "270", "440", id="BS_270_eq_440"),
        rule("BS", "400", "410", "420", gate=False),
        rule("IS", "01", "01.1", "01.2", "01.3", "01.4"),
        rule("IS", "20", *codes(1, 11, 2)),
        rule("IS", "21", "21.1", "21.2", "21.3", "21.4"),
        rule("IS", "40", *codes(21, 32, 2)),
        rule("IS", "50", *codes(41, 44, 2)),
        rule("IS", "60", *codes(51, 55, 2)),
        rule("IS", "70", "20", "-40", "50", "-60", "-61", "-62"),
        rule("IS", "80", "71", "-72"),
        rule("IS", "90", "70", "80"),
        rule("IS", "90", "91", "92", id="IS_90_parts", gate=False),
        rule("IS", "100", "100.1", "100.2"),
        rule("IS", "200", "90", "-100"),
        rule("IS", "200", "201", "202", "203", id="IS_200_parts", gate=False),
        rule("CF", "70", *codes(61, 65, 2)),
        rule("CF", "80", *codes(71, 76, 2)),
        rule("CF", "90", "60", "70", "80"),
    ),
)

RULESETS = {rs.template: rs for rs in (TT200, TT99, TCTD, CTCK)}
# Bộ ràng buộc dành cho doanh nghiệp thường (dùng khi tự nhận dạng mẫu)
CORPORATE_TEMPLATES = ("TT200", "TT99")

# Mã chỉ có ở cấu trúc TT99: 160 (tài sản ngắn hạn khác) và 280 (tổng cộng tài sản); TT200 không có hai mã này
TT99_ONLY_BS_CODES = ("160", "280")
