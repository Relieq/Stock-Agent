"""Ràng buộc kế toán khai báo theo mẫu BCTC và phiên bản (architecture.md mục 4.2).

Mỗi ràng buộc: lhs = tổng có dấu của các mã ở rhs, áp cho từng cột số (kỳ này, cùng kỳ, đầu năm...).
  * `gate=True`: ràng buộc chắc chắn theo mẫu biểu; trượt thì tài liệu không được coi là đã kiểm chứng.
  * `gate=False`: chưa đối chiếu với mẫu biểu gốc; chỉ ghi lại để theo dõi, không chặn.

Mẫu TT200 (Thông tư 200/2014, B01/B02/B03-DN và bản hợp nhất theo TT202) viết theo mẫu biểu.
Mẫu TT99 (Thông tư 99/2025) mới khai báo các dòng tổng đã đối chiếu trên BCTC thực tế; các dòng con bị
đổi mã chưa đối chiếu với phụ lục của thông tư nên chưa đưa vào (xem architecture.md mục 4.2).
Mẫu ngân hàng (TCTD) không in mã số kiểu DN thường, cần ánh xạ theo tên chỉ tiêu: chưa làm.
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
    rule("BS", "260", "261", "262", "263", "268"),
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
    rule("CF", "30", *codes(21, 27, 2), include_suffixed=True),
    rule("CF", "40", *codes(31, 36, 2), include_suffixed=True),
    rule("CF", "50", "20", "30", "40"),
    rule("CF", "70", "50", "60", "61"),
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

TT99 = RuleSet(
    template="TT99",
    total_assets_code="280",
    rules=(
        rule("BS", "280", "100", "200"),
        rule("BS", "280", "440", id="BS_280_eq_440"),
        # Một số BCTC dùng cấu trúc TT99 nhưng vẫn in mã tổng tài sản là 270 (ví dụ HPG quý 2/2026)
        rule("BS", "270", "100", "200", id="BS_270_total", when_absent="280"),
        rule("BS", "270", "440", id="BS_270_total_eq_440", when_absent="280"),
        # Dòng con theo cấu trúc quan sát trên BCTC quý 2/2026 (150: tài sản sinh học ngắn hạn, 160: tài sản ngắn
        # hạn khác, 230: tài sản sinh học dài hạn); chưa đối chiếu phụ lục TT99 nên chưa bắt buộc
        rule("BS", "100", "110", "120", "130", "140", "150", "160", gate=False),
        rule("BS", "200", "210", "220", "230", "240", "250", "260", "270", gate=False, when_present="280"),
        rule("BS", "200", "210", "220", "230", "240", "250", "260", id="BS_200_total270", gate=False,
             when_absent="280"),
        rule("BS", "300", "310", "330"),
        rule("BS", "400", "410", "430"),
        rule("BS", "440", "300", "400"),
        *_IS_TOTALS,
        # 27: lãi/lỗ trong công ty liên doanh, liên kết (khớp đúng cả 4 cột trên BCTC hợp nhất FPT quý 2/2026).
        # Chưa đối chiếu phụ lục TT99 nên chưa bắt buộc.
        rule("IS", "30", "20", "21", "22", "-23", "-25", "-26", "27", gate=False),
        *_no_gate(_CF),
        *_no_gate((rule("BS", "110", "111", "112"),)),
    ),
    cross_rules=tuple(replace(c, gate=False) for c in _CASH_CROSS),
)

RULESETS = {rs.template: rs for rs in (TT200, TT99)}

# Mã chỉ có ở cấu trúc TT99: 160 (tài sản ngắn hạn khác) và 280 (tổng cộng tài sản); TT200 không có hai mã này
TT99_ONLY_BS_CODES = ("160", "280")
