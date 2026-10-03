from decimal import Decimal

import pytest

from services.extraction.numbers import infer_thousands_sep, normalize_code, parse_amount, unit_multiplier
from services.extraction.validate import (
    ExtractedItem,
    ExtractedStatement,
    detect_template,
    normalize,
    summarize,
    validate,
)


@pytest.mark.parametrize(
    "raw, sep, expected",
    [
        ("1.234.567", ".", Decimal("1234567")),
        ("1,234,567", ",", Decimal("1234567")),
        ("(1.234.567)", ".", Decimal("-1234567")),
        ("-1.234", ".", Decimal("-1234")),
        ("1 234 567", ".", Decimal("1234567")),
        ("12,5", ".", Decimal("12.5")),
        ("-", ".", None),
        ("", ".", None),
        (None, ".", None),
        ("VI.1", ".", None),
    ],
)
def test_parse_amount(raw, sep, expected):
    assert parse_amount(raw, sep) == expected


def test_infer_thousands_sep():
    assert infer_thousands_sep(["1.234.567", "(2.000.000)", "12"]) == "."
    assert infer_thousands_sep(["1,234,567", "2,000,000", "1.234.567"]) == ","
    assert infer_thousands_sep(["1.234", "5"]) == "."  # không đủ bằng chứng: mặc định "."


@pytest.mark.parametrize(
    "raw, expected",
    [("Đơn vị tính: VND", 1), ("Đơn vị: triệu đồng", 1_000_000), ("ĐVT: nghìn đồng", 1_000), ("Đồng", 1), ("", None)],
)
def test_unit_multiplier(raw, expected):
    assert unit_multiplier(raw) == (Decimal(expected) if expected is not None else None)


def test_normalize_code():
    assert normalize_code("1") == "01"
    assert normalize_code(" 411a ") == "411a"
    assert normalize_code("421 B") == "421b"


def _bs(rows, unit="VND"):
    return ExtractedStatement(
        "BS", unit,
        [ExtractedItem(code, label, {"end_period": end, "begin_year": begin}) for code, label, end, begin in rows],
    )


# Bảng cân đối thu gọn, số liệu tự đặt cho khớp phép cộng
_TT200_ROWS = [
    ("100", "TÀI SẢN NGẮN HẠN", "1.500.000", "1.200.000"),
    ("110", "Tiền và các khoản tương đương tiền", "500.000", "400.000"),
    ("111", "Tiền", "300.000", "400.000"),
    ("112", "Các khoản tương đương tiền", "200.000", "-"),
    ("130", "Các khoản phải thu ngắn hạn", "1.000.000", "800.000"),
    ("131", "Phải thu ngắn hạn của khách hàng", "1.100.000", "850.000"),
    ("137", "Dự phòng phải thu ngắn hạn khó đòi", "(100.000)", "(50.000)"),
    ("200", "TÀI SẢN DÀI HẠN", "2.500.000", "2.300.000"),
    ("220", "Tài sản cố định", "2.500.000", "2.300.000"),
    ("221", "Tài sản cố định hữu hình", "2.500.000", "2.300.000"),
    ("222", "Nguyên giá", "4.000.000", "3.600.000"),
    ("223", "Giá trị hao mòn lũy kế", "(1.500.000)", "(1.300.000)"),
    ("270", "TỔNG CỘNG TÀI SẢN", "4.000.000", "3.500.000"),
    ("300", "NỢ PHẢI TRẢ", "1.000.000", "900.000"),
    ("310", "Nợ ngắn hạn", "1.000.000", "900.000"),
    ("311", "Phải trả người bán ngắn hạn", "1.000.000", "900.000"),
    ("400", "VỐN CHỦ SỞ HỮU", "3.000.000", "2.600.000"),
    ("410", "Vốn chủ sở hữu", "3.000.000", "2.600.000"),
    ("411", "Vốn góp của chủ sở hữu", "2.000.000", "2.000.000"),
    ("421", "Lợi nhuận sau thuế chưa phân phối", "1.000.000", "600.000"),
    ("440", "TỔNG CỘNG NGUỒN VỐN", "4.000.000", "3.500.000"),
]


def test_tt200_balance_sheet_passes_and_is_detected():
    statements, sep = normalize([_bs(_TT200_ROWS)])
    assert sep == "."
    assert detect_template(statements) == "TT200"
    checks = validate(statements, "TT200")
    assert summarize(checks)["gate_failed"] == 0
    assert any(c.rule_id == "BS_270_eq_440" for c in checks)


def test_tt99_total_assets_code_is_detected():
    rows = [(("280" if code == "270" else code), label, end, begin) for code, label, end, begin in _TT200_ROWS]
    statements, _ = normalize([_bs(rows)])
    assert detect_template(statements) == "TT99"
    assert summarize(validate(statements, "TT99"))["gate_failed"] == 0


def test_misread_digit_is_caught():
    rows = [r if r[0] != "131" else ("131", r[1], "1.180.000", r[3]) for r in _TT200_ROWS]  # đọc sai 1 chữ số
    statements, _ = normalize([_bs(rows)])
    failed = [c for c in validate(statements, "TT200") if not c.passed]
    assert [(c.rule_id, c.column_kind) for c in failed] == [("BS_130", "end_period")]
    assert failed[0].diff == Decimal(-80_000)


def test_unit_is_applied():
    statements, _ = normalize([_bs(_TT200_ROWS, unit="Đơn vị tính: triệu đồng")])
    assert statements["BS"].values["270"]["end_period"] == Decimal(4_000_000) * 1_000_000


def _is(rows):
    return ExtractedStatement("IS", "VND", [ExtractedItem(c, label, {"q_cur": v}) for c, label, v in rows])


def test_income_statement_with_expenses_printed_negative():
    # Kiểu trình bày của MWG: giảm trừ và chi phí in trong ngoặc
    rows = [("01", "Doanh thu", "1.000.000"), ("02", "Giảm trừ", "(50.000)"), ("10", "Doanh thu thuần", "950.000"),
            ("11", "Giá vốn", "(700.000)"), ("20", "Lợi nhuận gộp", "250.000"),
            ("21", "DT tài chính", "10.000"), ("22", "CP tài chính", "(20.000)"),
            ("25", "CP bán hàng", "(100.000)"), ("26", "CP quản lý", "(40.000)"), ("30", "LN thuần", "100.000")]
    statements, _ = normalize([_bs(_TT200_ROWS), _is(rows)])
    checks = {c.rule_id: c for c in validate(statements, "TT200")}
    assert checks["IS_10"].passed and checks["IS_20"].passed and checks["IS_30"].passed


def test_income_statement_with_expenses_printed_positive():
    rows = [("01", "Doanh thu", "1.000.000"), ("02", "Giảm trừ", "50.000"), ("10", "Doanh thu thuần", "950.000"),
            ("11", "Giá vốn", "700.000"), ("20", "Lợi nhuận gộp", "250.000"), ("25", "CP bán hàng", "100.000"),
            ("26", "CP quản lý", "40.000"), ("30", "LN thuần", "110.000")]
    statements, _ = normalize([_bs(_TT200_ROWS), _is(rows)])
    checks = {c.rule_id: c for c in validate(statements, "TT200")}
    assert checks["IS_10"].passed and checks["IS_20"].passed and checks["IS_30"].passed


def test_cash_cross_check_between_statements():
    cf = ExtractedStatement("CF", "VND", [
        ExtractedItem("50", "Lưu chuyển tiền thuần trong kỳ", {"ytd_cur": "100.000"}),
        ExtractedItem("60", "Tiền đầu kỳ", {"ytd_cur": "400.000"}),
        ExtractedItem("70", "Tiền cuối kỳ", {"ytd_cur": "500.000"}),
    ])
    statements, _ = normalize([_bs(_TT200_ROWS), cf])
    checks = {c.rule_id: c for c in validate(statements, "TT200")}
    assert checks["X_cash_end"].passed and checks["X_cash_begin"].passed and checks["CF_70"].passed


def test_duplicate_code_is_reported_not_overwritten():
    rows = _TT200_ROWS + [("221", "Bất động sản đầu tư (in trùng mã)", "999.999", "999.999")]
    statements, _ = normalize([_bs(rows)])
    assert statements["BS"].duplicate_codes == ["221"]
    assert statements["BS"].values["221"]["end_period"] == Decimal(2_500_000)
