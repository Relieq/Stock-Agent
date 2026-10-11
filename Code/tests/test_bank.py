from services.extraction.bank import canonicalize, clean_label, fold
from services.extraction.validate import ExtractedItem, ExtractedStatement, normalize, summarize, validate


def _st(statement, rows, col):
    return ExtractedStatement(statement, "Triệu VND",
                              [ExtractedItem(code, label, {col: value}) for code, label, value in rows])


# Bảng cân đối thu gọn, tên chỉ tiêu lấy theo cách gọi thực tế của VCB/TCB/ACB quý 2/2026
BS = [
    (None, "TÀI SẢN", None),
    (None, "Tiền mặt, vàng bạc, đá quý", "100"),
    (None, "Tiền gửi tại Ngân hàng Nhà nước Việt Nam (“NHNN”)", "200"),
    (None, "Tiền gửi và cấp tín dụng cho các tổ chức tín dụng (“TCTD”) khác", "300"),
    (None, "Chứng khóan kinh doanh", "50"),           # kiểu bỏ dấu cũ như BCTC VCB
    (None, "Chứng khóan kinh doanh", "55"),           # dòng con trùng tên: không được nhận mã
    (None, "Dự phòng rủi ro chứng khóan kinh doanh", "(5)"),
    (None, "Cho vay khách hàng", "1.000"),
    (None, "Tài sản Có khác", "50"),
    (None, "TỔNG TÀI SẢN CÓ", "1.700"),
    (None, "Tiền gửi của khách hàng", "1.200"),
    (None, "Phát hành giấy tờ có giá", "300"),
    (None, "TỔNG NỢ PHẢI TRẢ", "1.500"),
    (None, "VỐN CHỦ SỞ HỮU", None),                  # tiêu đề không có số
    (None, "TỔNG VỐN CHỦ SỞ HỮU", "200"),
    (None, "TỔNG NỢ PHẢI TRẢ VÀ VỐN CHỦ SỞ HỮU", "1.700"),
]

IS = [
    ("24", "Thu nhập lãi và các khoản thu nhập tương tự", "1.000"),   # số thuyết minh bị ghi vào ô mã số (TCB)
    ("25", "Chi phí lãi và các chi phí tương tự", "(600)"),
    (None, "Thu nhập lãi thuần", "400"),
    (None, "Thu nhập từ hoạt động dịch vụ", "100"),
    (None, "Chi phí hoạt động dịch vụ", "(40)"),
    (None, "Lãi thuần từ hoạt động dịch vụ", "60"),
    (None, "Lãi/(lỗ) thuần từ hoạt động kinh doanh ngoại hối", "(10)"),
    (None, "Thu nhập từ hoạt động khác", "30"),
    (None, "Chi phí hoạt động khác", "(10)"),
    (None, "Lãi thuần từ hoạt động khác", "20"),
    (None, "Tổng thu nhập hoạt động", "470"),
    (None, "Chi phí hoạt động", "(170)"),
    (None, "Lợi nhuận thuần từ hoạt động kinh doanh trước chi phí dự phòng rủi ro tín dụng", "300"),
    (None, "Chi phí dự phòng rủi ro tín dụng", "(50)"),
    (None, "Tổng lợi nhuận trước thuế", "250"),
    (None, "Chi phí thuế thu nhập doanh nghiệp hiện hành", "(52)"),
    (None, "Thu nhập/(chi phí) thuế thu nhập doanh nghiệp hoãn lại", "2"),
    (None, "Chi phí thuế thu nhập doanh nghiệp", "(50)"),
    (None, "Lợi nhuận sau thuế", "200"),
]

CF = [
    (None, "Tiền thuần từ hoạt động kinh doanh", "500"),
    (None, "Lưu chuyển tiền thuần từ/(sử dụng vào) hoạt động đầu tư", "(100)"),
    (None, "Lưu chuyển tiền thuần trong kỳ", "400"),
    (None, "TIỀN VÀ CÁC KHOẢN TƯƠNG ĐƯƠNG TIỀN TẠI NGÀY 1 THÁNG 1", "1.000"),
    (None, "Điều chỉnh ảnh hưởng của thay đổi tỷ giá", "(10)"),
    (None, "TIỀN VÀ CÁC KHOẢN TƯƠNG ĐƯƠNG TIỀN TẠI NGÀY 30 THÁNG 6", "1.390"),
]


def _extracted():
    return [_st("BS", BS, "end_period"), _st("IS", IS, "q_cur"), _st("CF", CF, "ytd_cur")]


def test_fold_ignores_tone_mark_placement():
    assert fold(clean_label("Chứng khóan kinh doanh")) == fold(clean_label("Chứng khoán kinh doanh"))
    assert fold(clean_label("II. Vốn tài trợ, uỷ thác đầu tư")) == fold("vốn tài trợ, ủy thác đầu tư")


def test_canonicalize_maps_parent_rows_and_skips_headings():
    extracted = _extracted()
    canonicalize(extracted)
    bs = {it.code: it for it in extracted[0].items if it.code}
    assert bs["b.trading_sec"].values_raw["end_period"] == "50"     # dòng cha, không phải dòng con trùng tên
    assert bs["b.interbank"].values_raw["end_period"] == "300"
    assert bs["b.te"].label == "TỔNG VỐN CHỦ SỞ HỮU"
    is_items = {it.code: it for it in extracted[1].items if it.code}
    assert is_items["b.ii"].note == "24"                               # số thuyết minh được chuyển sang cột thuyết minh


def test_bank_rules_pass_on_consistent_statements():
    extracted = _extracted()
    canonicalize(extracted)
    statements, _ = normalize(extracted)
    checks = validate(statements, "TCTD")
    assert summarize(checks)["gate_failed"] == 0
    ids = {c.rule_id for c in checks}
    assert {"BS_bank_assets", "BS_bank_ta_eq_tle", "IS_bank_nii", "IS_bank_toi", "IS_bank_npat",
            "CF_bank_net", "CF_bank_cash_end"} <= ids


def test_missing_asset_line_is_caught():
    extracted = _extracted()
    extracted[0].items = [it for it in extracted[0].items if it.label != "Cho vay khách hàng"]
    canonicalize(extracted)
    statements, _ = normalize(extracted)
    failed = [c.rule_id for c in validate(statements, "TCTD") if not c.passed]
    assert failed == ["BS_bank_assets"]


def test_label_variants_seen_in_q2_2026():
    rows = [
        (None, "Tiền mặt", "10"),                                                   # LPB
        (None, "Tiền gửi tại Ngân hàng Trung ương", "20"),                          # BID
        (None, "Tiền, vàng gửi tại và cho vay TCTD khác", "30"),                    # BID
        (None, "Các khoản nợ Chính phủ và Ngân hàng Trung ương", "40"),             # BID
        (None, "Các khoản nợ Chính phủ và NHNNVN", "40"),                           # LPB (dòng sau: không nhận mã)
        (None, "Các công cụ tài chính phái sinh và các công nợ tài chính khác", "5"),  # BID
    ]
    extracted = [_st("BS", rows, "end_period")]
    canonicalize(extracted)
    codes = [it.code for it in extracted[0].items]
    assert codes == ["b.cash", "b.sbv", "b.interbank", "b.gov", None, "b.deriv_liab"]


def test_minority_interest_sign_does_not_follow_expense_convention():
    # Chi phí in số dương (không đảo dấu), nhưng lợi ích cổ đông không kiểm soát in trong ngoặc (như MBB, VPB)
    rows = [
        (None, "Thu nhập lãi và các khoản thu nhập tương tự", "1.000"),
        (None, "Chi phí lãi và các chi phí tương tự", "600"),
        (None, "Chi phí hoạt động", "100"),
        (None, "Lợi nhuận sau thuế", "200"),
        (None, "Lợi ích của cổ đông không kiểm soát", "(20)"),
        (None, "Lợi nhuận sau thuế của cổ đông của Ngân hàng", "180"),
    ]
    extracted = [_st("IS", rows, "q_cur")]
    canonicalize(extracted)
    statements, _ = normalize(extracted)
    checks = {c.rule_id: c for c in validate(statements, "TCTD")}
    assert checks["IS_bank_parent"].passed
