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
        (None, "Các khoản nợ Chính phủ và NHNNVN", "40"),                           # LPB (dòng sau, cùng số: không nhận mã)
        (None, "Các công cụ tài chính phái sinh và các công nợ tài chính khác", "5"),  # BID
    ]
    extracted = [_st("BS", rows, "end_period")]
    canonicalize(extracted)
    codes = [it.code for it in extracted[0].items]
    assert codes == ["b.cash", "b.sbv", "b.interbank", "b.gov", None, "b.deriv_liab"]


def test_label_variants_seen_in_q4_2025():
    rows = [
        (None, "Tiền; vàng gửi và cho vay các tổ chức tín dụng (\"TCTD\")", "30"),    # MBB
        (None, "Các công cụ tài chính phái sinh và các khoản nợ", "5"),              # STB, tên bị cắt khi xuống dòng
    ]
    extracted = [_st("BS", rows, "end_period")]
    canonicalize(extracted)
    assert [it.code for it in extracted[0].items] == ["b.interbank", "b.deriv_liab"]


def test_operating_cash_flow_takes_the_last_matching_total():
    # BID quý 4/2025: dòng tổng tạm trước phần thay đổi tài sản/công nợ hoạt động mang cùng tên với dòng tổng thật
    rows = [
        (None, "Lưu chuyển tiền thuần từ hoạt động kinh doanh", "50"),
        (None, "(Tăng) các khoản cho vay khách hàng", "(30)"),
        (None, "Lưu chuyển tiền thuần từ hoạt động KD", "20"),
        (None, "Lưu chuyển tiền thuần từ hoạt động đầu tư", "(5)"),
    ]
    extracted = [_st("CF", rows, "ytd_cur")]
    canonicalize(extracted)
    # Hai dòng phía trên là thành phần của khúc kinh doanh: 50 + (30) = 20 (bank.assign_children)
    assert [it.code for it in extracted[0].items] == ["b.cfo.1", "b.cfo.2", "b.cfo", "b.cfi"]


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


def test_wrapped_label_shift_is_repaired():
    # KQKD SHB quý 2/2026: tên dòng IX xuống ba dòng, mô hình gán số của IX cho tên dòng X
    rows = [
        (None, "Chi phí hoạt động", "(1.459)"),
        (None, "Lợi nhuận thuần từ hoạt động kinh doanh trước chi phí dự phòng rủi ro tín dụng", None),
        (None, "Hoàn nhập/(Chi phí) dự phòng rủi ro tín dụng", "8.261"),
        (None, "Hoàn nhập/(Chi phí) dự phòng rủi ro tín dụng", "(3.825)"),
        (None, "Tổng lợi nhuận trước thuế", "4.436"),
        (None, "Chi phí thuế TNDN hiện hành tạm tính", "(879)"),
    ]
    st = _st("IS", rows, "q_cur")
    canonicalize([st], repair_labels=True)
    codes = {it.code: it.values_raw["q_cur"] for it in st.items if it.code}
    assert codes["b.ppop"] == "8.261"
    assert codes["b.prov"] == "(3.825)"
    assert codes["b.cit_cur"] == "(879)"


def test_label_variants_seen_in_q1_2026():
    rows = [
        (None, "Thu nhập/(lỗ) từ góp vốn, mua cổ phần", "(58)"),                       # TCB
        (None, "Chi phí thuế thu nhập doanh nghiệp hiện hành", "(547)"),
        (None, 'Chi phí thuế thu nhập doanh nghiệp ("TNDN")', "(547)"),               # LPB
    ]
    st = _st("IS", rows, "ytd_cur")
    canonicalize([st])
    assert [it.code for it in st.items] == ["b.equity_inc", "b.cit_cur", "b.cit"]


def test_detail_lines_are_checked_against_their_parent_line():
    # VCB quý 2/2026 (triệu đồng): dòng con theo vị trí, dòng cháu theo số thứ tự a/b hoặc tên nguyên giá/hao mòn
    rows = [
        ("VI", "Cho vay khách hàng", "1.728.183.370"),
        ("1", "Cho vay khách hàng", "1.758.168.065"),
        ("2", "Dự phòng rủi ro cho vay khách hàng", "(29.984.695)"),
        ("IX", "Tài sản cố định", "17.937.947"),
        ("1", "Tài sản cố định hữu hình", "10.376.429"),
        ("a", "Nguyên giá", "22.603.916"),
        ("b", "Hao mòn tài sản cố định", "(12.227.487)"),
        ("3", "Tài sản cố định vô hình", "7.561.518"),
        (None, "Nguyên giá", "10.478.167"),
        (None, "Khấu hao tài sản cố định", "(2.916.649)"),
        ("X", "Tài sản Có khác", "1"),
    ]
    st = _st("BS", [(None, label, v) for _, label, v in rows], "end_period")
    for it, (stt, _, _) in zip(st.items, rows):
        it.stt = stt
    canonicalize([st])
    assert [it.code for it in st.items] == [
        "b.loans", "b.loans.1", "b.loans.2", "b.fixed_assets", "b.fixed_assets.1", "b.fixed_assets.1.1",
        "b.fixed_assets.1.2", "b.fixed_assets.2", "b.fixed_assets.2.1", "b.fixed_assets.2.2", "b.other_assets"]
    statements, _ = normalize([st])
    groups = {c.rule_id: c.passed for c in validate(statements, "TCTD") if "_grp_" in c.rule_id}
    assert groups == {"BS_grp_b.loans": True, "BS_grp_b.fixed_assets": True, "BS_grp_b.fixed_assets.1": True,
                      "BS_grp_b.fixed_assets.2": True}


def test_label_variants_seen_in_h1_2026():
    # BID: "Chi phí từ hoạt động khác" (trước đây khớp nhầm "Chi phí hoạt động khác" trong chi phí hoạt động),
    # "Phân bổ (lãi) cho cổ đông không kiểm soát", "Lợi nhuận thuần của Ngân hàng mẹ"; VCB: chú thích chuyển trang
    rows = [
        (None, "Thu nhập từ hoạt động khác", "6.315.750"),
        (None, "Chi phí từ hoạt động khác", "(1.397.097)"),
        (None, "Lãi thuần từ hoạt động khác", "4.918.653"),
        (None, "Chi phí hoạt động khác", "(5.493.888)"),
        (None, "TỔNG LỢI NHUẬN TRƯỚC THUẾ (MANG SANG TRANG SAU)", "18.904.589"),
        (None, "Phân bổ (lãi) cho cổ đông không kiểm soát", "(226.620)"),
        (None, "Lợi nhuận thuần của Ngân hàng mẹ", "14.947.090"),
    ]
    extracted = [_st("IS", rows, "ytd_cur")]
    canonicalize(extracted)
    assert [it.code for it in extracted[0].items] == ["b.oi", "b.oe", "b.nother", None, "b.pbt", "b.mi", "b.npat_parent"]


def test_parent_profit_label_variants():
    # CTG, HDB: "Lợi nhuận thuần của chủ sở hữu"; MBB quý 1/2026, VPB: "... thuộc về (cổ đông của) Ngân hàng (mẹ)".
    # Trước đây không nhận ra nên thẻ lấy LNST chung (gồm cả phần cổ đông không kiểm soát)
    for label in ("Lợi nhuận thuần của chủ sở hữu", "Lợi nhuận sau thuế thuộc về Ngân hàng mẹ",
                  "Lợi nhuận thuần thuộc về cổ đông của Ngân hàng",
                  "Lợi nhuận sau thuế thuộc về cổ đông của Ngân hàng mẹ"):
        rows = [(None, "Lợi nhuận sau thuế", "5.797.908"), (None, "Lợi ích của cổ đông không kiểm soát", "239.178"),
                (None, label, "5.558.730")]
        extracted = [_st("IS", rows, "ytd_cur")]
        canonicalize(extracted)
        assert [it.code for it in extracted[0].items] == ["b.npat", "b.mi", "b.npat_parent"], label


def test_parent_profit_rule_accepts_minority_loss():
    # Công ty con lỗ: LNST của cổ đông ngân hàng mẹ lớn hơn LNST chung; dấu in của dòng không kiểm soát không cho biết chiều
    for minority, parent in (("(239.178)", "5.558.730"), ("(239.178)", "6.037.086"), ("239.178", "6.037.086")):
        rows = [(None, "Lợi nhuận sau thuế", "5.797.908"), (None, "Lợi ích của cổ đông không kiểm soát", minority),
                (None, "Lợi nhuận thuần của chủ sở hữu", parent)]
        extracted = [_st("IS", rows, "ytd_cur")]
        canonicalize(extracted)
        statements, _ = normalize(extracted)
        checks = [c for c in validate(statements, "TCTD") if c.rule_id == "IS_bank_parent"]
        assert len(checks) == 1 and checks[0].passed and checks[0].gate
    rows = [(None, "Lợi nhuận sau thuế", "8.862.910"), (None, "Lợi ích của cổ đông không kiểm soát", "219.284"),
            (None, "Lợi nhuận sau thuế thuộc về cổ đông của Ngân hàng mẹ", "8.643.526")]   # VPB quý 3/2026, 72 dpi
    extracted = [_st("IS", rows, "q_cur")]
    canonicalize(extracted)
    statements, _ = normalize(extracted)
    assert not next(c for c in validate(statements, "TCTD") if c.rule_id == "IS_bank_parent").passed
