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


def test_cash_flow_detail_lines_with_same_code_are_summed():
    # VNM quý 4/2025: khấu hao và phân bổ lợi thế thương mại cùng in mã 02
    cf = ExtractedStatement("CF", "VND", [
        ExtractedItem("01", "Lợi nhuận trước thuế", {"ytd_cur": "1.000"}),
        ExtractedItem("02", "Khấu hao", {"ytd_cur": "200"}),
        ExtractedItem("02", "Phân bổ lợi thế thương mại", {"ytd_cur": "50"}),
        ExtractedItem("08", "Lợi nhuận trước thay đổi vốn lưu động", {"ytd_cur": "1.250"}),
    ])
    statements, _ = normalize([cf])
    assert statements["CF"].values["02"]["ytd_cur"] == Decimal(250)
    assert statements["CF"].summed_codes == ["02"] and statements["CF"].duplicate_codes == []
    assert {c.rule_id: c for c in validate(statements, "TT200")}["CF_08"].passed


def test_goodwill_269_counts_in_other_long_term_assets():
    rows = [("260", "Tài sản dài hạn khác", "150", "150"), ("261", "Chi phí trả trước dài hạn", "100", "100"),
            ("269", "Lợi thế thương mại", "50", "50")]
    statements, _ = normalize([_bs(rows)])
    assert all(c.passed for c in validate(statements, "TT200") if c.rule_id == "BS_260")


def _record(rows_by_statement, company_template="corporate"):
    return {"company_template": company_template,
            "raw": {st: {"unit_text": "Đơn vị tính: VND", "rows": rows} for st, rows in rows_by_statement.items()}}


def _row(stt, code, label, value, page=1, col="end_period"):
    return {"stt": stt, "code": code, "label": label, "note": None, "page": page, "values": {col: value}}


def test_code_column_swapped_with_stt_is_recovered():
    # VIC quý 2/2026 in cột mã số bên trái, mô hình chép đảo mã số và số thứ tự
    from services.extraction.pipeline import _check
    bs = [_row("100", None, "TÀI SẢN NGẮN HẠN", "60", page=1), _row("110", "1", "Tiền", "60", page=1),
          _row("200", None, "TÀI SẢN DÀI HẠN", "40", page=1), _row("280", None, "TỔNG CỘNG TÀI SẢN", "100", page=1),
          _row("300", None, "NỢ PHẢI TRẢ", "70", page=2), _row("400", None, "VỐN CHỦ SỞ HỮU", "30", page=2),
          _row("440", None, "TỔNG CỘNG NGUỒN VỐN", "100", page=2)]
    rec = _record({"BS": bs})
    _, statements, _, template, checks = _check(rec)
    assert template == "TT99"
    assert {"100", "280", "440"} <= set(statements["BS"].values)
    assert rec["stt_code_swapped"] == ["BS@1", "BS@2"]
    assert all(c.passed for c in checks if c.gate)


def test_missing_code_is_inferred_only_when_numbers_prove_it():
    # SSI quý 2/2026: dòng "KẾT QUẢ HOẠT ĐỘNG" (mã 70) bị chép thiếu mã
    from services.extraction.pipeline import _check
    def r(code, label, cur, prev):
        return {"stt": None, "code": code, "label": label, "note": None, "page": 1,
                "values": {"q_cur": cur, "q_prev_year": prev}}
    is_rows = [r(None, "KẾT QUẢ HOẠT ĐỘNG", "1.500", "1.200"), r("71", "Thu nhập khác", "30", "20"),
               r("72", "Chi phí khác", "10", "5"), r("80", "Cộng kết quả hoạt động khác", "20", "15"),
               r("90", "Tổng lợi nhuận trước thuế", "1.520", "1.215")]
    rec = _record({"IS": is_rows}, "securities")
    _, statements, _, template, checks = _check(rec)
    assert template == "CTCK"
    assert rec["codes_inferred"] == [{"statement": "IS", "code": "70", "label": "KẾT QUẢ HOẠT ĐỘNG", "rule": "IS_90"}]
    assert all(c.passed for c in checks if c.gate)

    is_rows[0]["values"]["q_prev_year"] = "1.100"      # số không khớp ở một cột thì không gán
    rec = _record({"IS": is_rows}, "securities")
    _check(rec)
    assert rec["codes_inferred"] == []


def test_parent_and_minority_rows_without_codes_get_61_62_from_labels():
    # VIC quý 1/2026: hai dòng chia LNST không in mã số; thiếu bước này thẻ lấy dòng 60 làm LNST công ty mẹ
    from services.extraction.pipeline import _label_split_codes
    is_ = ExtractedStatement("IS", "Triệu VND", [
        ExtractedItem("60", "Lợi nhuận sau thuế TNDN", {"q_cur": "5.610.779"}),
        ExtractedItem(None, "Trong đó:", {"q_cur": None}),
        ExtractedItem(None, "- Lợi nhuận/(lỗ) sau thuế của công ty mẹ", {"q_cur": "7.276.018"}),
        ExtractedItem(None, "- Lợi nhuận/(lỗ) sau thuế của cổ đông không kiểm soát", {"q_cur": "(1.665.239)"}),
    ])
    statements, _ = normalize([is_])
    assert [d["code"] for d in _label_split_codes([is_], statements)] == ["61", "62"]
    statements, _ = normalize([is_])
    assert all(c.passed for c in validate(statements, "TT200") if c.rule_id == "IS_60_split")


def test_output_limits_per_step():
    from services.llm import output_limit
    assert output_limit("statement_BS") == 24_000
    assert output_limit("reextract_IS") == 16_000
    assert output_limit("repair_zoom") == 6_000
    assert output_limit("something_new") is None


def test_balance_sheet_detail_line_split_in_two_rows_is_summed():
    # VJC quý 2/2026: "Vay ngắn hạn" và "Phải trả thuê tài chính ngắn hạn" cùng in mã 321 (mẫu TT99: vay và nợ thuê
    # tài chính ngắn hạn); dòng tổng in trùng mã thì vẫn báo trùng, không cộng
    bs = ExtractedStatement("BS", "VND", [
        ExtractedItem("310", "Nợ ngắn hạn", {"end_period": "1.300"}),
        ExtractedItem("321", "Vay ngắn hạn", {"end_period": "1.000"}),
        ExtractedItem("321", "Phải trả thuê tài chính ngắn hạn", {"end_period": "300"}),
        ExtractedItem("310", "Nợ ngắn hạn (in lại)", {"end_period": "999"}),
    ])
    statements, _ = normalize([bs])
    assert statements["BS"].values["321"]["end_period"] == Decimal(1_300)
    assert statements["BS"].summed_codes == ["321"]
    assert statements["BS"].duplicate_codes == ["310"]


def _cf(rows):
    return ExtractedStatement("CF", "VND", [ExtractedItem(c, l, {"ytd_cur": v}) for c, l, v in rows])


def test_cash_flow_without_codes_checked_by_position():
    # MSN bán niên 2026: LCTT chép ra không có mã số; dòng tổng tạm không tên = 08 + biến động vốn lưu động
    from services.extraction.pipeline import _cf_positional_codes
    cf = _cf([
        (None, "LƯU CHUYỂN TIỀN TỪ HOẠT ĐỘNG KINH DOANH", None),
        (None, "Lợi nhuận kế toán trước thuế", "100"),
        (None, "Khấu hao", "20"),
        (None, "Lãi từ hoạt động kinh doanh trước những thay đổi vốn lưu động", "120"),
        (None, "Biến động phải thu", "(30)"),
        (None, "Biến động hàng tồn kho", "10"),
        (None, "", "100"),
        (None, "Thuế thu nhập doanh nghiệp đã nộp", "(5)"),
        (None, "Lưu chuyển tiền thuần từ hoạt động kinh doanh", "95"),
        (None, "Tiền chi mua tài sản cố định", "(40)"),
        (None, "Lưu chuyển tiền thuần từ hoạt động đầu tư", "(40)"),
        (None, "Lưu chuyển tiền thuần trong kỳ", "55"),
    ])
    _cf_positional_codes([cf], ".")
    assert [it.code for it in cf.items] == [None, "08.1", "08.2", "08", "20.1.1", "20.1.2", "20.1", "20.2", "20",
                                            "30.1", "30", "50"]
    statements, _ = normalize([cf])
    groups = [c for c in validate(statements, "TT200") if "_grp_" in c.rule_id]
    assert len(groups) == 4 and all(c.passed and c.gate for c in groups)
    assert not [c for c in validate(statements, "TT200") if c.rule_id in ("CF_08", "CF_20")]


def test_cash_flow_positional_codes_skip_direct_method_and_mixed_blocks():
    from services.extraction.pipeline import _cf_positional_codes
    direct = _cf([(None, "Tiền thu từ bán hàng", "100"), ("02", "Tiền chi trả cho người cung cấp", "(60)"),
                  (None, "Lưu chuyển tiền thuần từ hoạt động kinh doanh", "40")])
    assert _cf_positional_codes([direct], ".") == [] and direct.items[0].code is None
    mixed = _cf([("08", "Lợi nhuận trước thay đổi vốn lưu động", "100"), ("09", "Biến động phải thu", "(30)"),
                 (None, "Biến động khác", "5"), ("20", "Lưu chuyển tiền thuần từ hoạt động kinh doanh", "75")])
    _cf_positional_codes([mixed], ".")
    assert mixed.items[2].code is None


def test_reread_label_names_which_of_duplicate_rows():
    # TCX quý 1/2026: trang có hai dòng "Lợi nhuận đã thực hiện"; hỏi theo tên thì mô hình đọc số của dòng kia
    from services.extraction.pipeline import _label_on_page
    record = {"raw": {"IS": {"rows": [
        {"label": "Lợi nhuận đã thực hiện", "page": 11},
        {"label": "Chi phí", "page": 11},
        {"label": "Lợi nhuận  đã thực hiện", "page": 11},
        {"label": "Lợi nhuận đã thực hiện", "page": 12},
    ]}}}
    assert _label_on_page(record, "IS", 1) == "Chi phí"
    assert "dòng thứ 2 trong 2" in _label_on_page(record, "IS", 2)
    assert "dòng thứ 1 trong 2" in _label_on_page(record, "IS", 0)
    assert _label_on_page(record, "IS", 3) == "Lợi nhuận đã thực hiện"


class _FakeReader:
    """Giả lập mô hình đọc lại: by_step[bước][tên dòng] là số trả về; dòng không có trong bảng thì trả số đang in."""

    def __init__(self, by_step, step_providers):
        import types
        self.by_step, self.step_providers, self.calls = by_step, step_providers, []
        self.cfg = types.SimpleNamespace(model="fake", provider="fake")

    def json_from_images(self, prompt, images, schema, schema_name, step=None, detail=None):
        import re
        self.calls.append(step)
        printed = {"TÀI SẢN NGẮN HẠN": "60", "Tiền": "50"}
        return {"cells": [{"code": cid, "column_kind": "end_period",
                           "value": self.by_step.get(step, {}).get(label, printed.get(label))}
                          for cid, label in re.findall(r'ô (o\d+): dòng "([^"]+)"', prompt)]}


def _bs_with_misread_cash():
    rows = [_row(None, "100", "TÀI SẢN NGẮN HẠN", "60"), _row(None, "110", "Tiền", "50"),
            _row(None, "200", "TÀI SẢN DÀI HẠN", "40"), _row(None, "280", "TỔNG CỘNG TÀI SẢN", "100"),
            _row(None, "300", "NỢ PHẢI TRẢ", "70"), _row(None, "400", "VỐN CHỦ SỞ HỮU", "30"),
            _row(None, "440", "TỔNG CỘNG NGUỒN VỐN", "100")]
    rec = _record({"BS": rows})
    rec.update(candidates=[{"name": "f.pdf", "rotations": {}}], chosen="f.pdf")
    return rec


def test_escalation_reader_confirms_when_main_model_repeats_old_value(monkeypatch):
    # FPT quý 2/2026: ô bị con dấu đè, mô hình chính đọc lại vẫn ra số cũ; mô hình mạnh hơn đọc ra đúng số ràng buộc đòi
    from services.extraction import pipeline
    monkeypatch.setattr(pipeline, "render_sharp", lambda *a, **k: b"")
    monkeypatch.setattr(pipeline, "render_strips", lambda *a, **k: [b""])
    rec = _bs_with_misread_cash()
    reader = _FakeReader({"repair_escalate": {"Tiền": "60"}},
                         {"repair_escalate": "anthropic:claude-opus-5-5"})
    assert pipeline._repair_by_constraints(rec, reader, doc=None) is True
    assert rec["raw"]["BS"]["rows"][1]["values"]["end_period"] == "60"
    assert reader.calls[-1] == "repair_escalate"
    assert any(r["escalated"] == "60" and r["accepted"] for r in rec["repairs"])


def test_no_escalation_step_when_not_configured(monkeypatch):
    from services.extraction import pipeline
    monkeypatch.setattr(pipeline, "render_sharp", lambda *a, **k: b"")
    monkeypatch.setattr(pipeline, "render_strips", lambda *a, **k: [b""])
    rec = _bs_with_misread_cash()
    reader = _FakeReader({}, {})
    assert pipeline._repair_by_constraints(rec, reader, doc=None) is False
    assert "repair_escalate" not in reader.calls
    assert rec["raw"]["BS"]["rows"][1]["values"]["end_period"] == "50"
