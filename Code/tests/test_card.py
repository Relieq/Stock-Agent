from decimal import Decimal as D

from services.metrics.card import change_text, ty, vn

B = D(10**9)


def test_number_format_is_vietnamese():
    assert vn(D("1234.56")) == "1.234,6"
    assert ty(D("4292") * B) == "4.292 tỷ"
    assert ty(D("-3.17") * B) == "3,2 tỷ"


def test_growth_percent_only_when_both_periods_profitable():
    assert change_text(D(120) * B, D(100) * B, True) == "+20,0% (từ 100 tỷ lên 120 tỷ)"
    assert change_text(D(80) * B, D(100) * B, True) == "−20,0% (từ 100 tỷ xuống 80,0 tỷ)"


def test_losses_are_described_in_words_not_percent():
    # DNSE viết "lợi nhuận đạt âm 3,17 tỷ đồng, tăng trưởng 53,6%" cho APG quý 2/2026: thẻ không được in như vậy
    assert change_text(D("-3.17") * B, D("-6.83") * B, True) == "lỗ thu hẹp từ 6,8 tỷ còn 3,2 tỷ"
    assert change_text(D(-10) * B, D(-5) * B, True) == "lỗ tăng từ 5,0 tỷ lên 10,0 tỷ"
    assert change_text(D(10003) * B, D(-941) * B, True) == "chuyển từ lỗ 941 tỷ sang lãi 10.003 tỷ"
    assert change_text(D(-5) * B, D(20) * B, True) == "chuyển từ lãi 20,0 tỷ sang lỗ 5,0 tỷ"
    assert "%" not in change_text(D(-1) * B, D(-2) * B, True)


def test_missing_values_give_no_text():
    assert change_text(None, D(1), True) == ""


class _Facts:
    """Thay Facts: chỉ trả các số quý cho cờ (đơn vị tỷ)."""

    def __init__(self, template, **vals):
        self.template, self.vals = template, vals

    def metric(self, statement, metric, column):
        from services.metrics.card import Value
        v = self.vals.get(f"{metric}.{column}")
        return Value(None if v is None else D(v) * B)


def test_other_income_flag_on_bank_debt_recovery():
    from services.metrics.card import flag_other_income
    # VCB quý 2/2026: LNTT +6.386 tỷ, lãi thuần hoạt động khác +2.906 tỷ (46% mức tăng)
    vcb = _Facts("TCTD", **{"other_profit.q_cur": "4058.556", "other_profit.q_prev_year": "1152.928",
                            "pbt.q_cur": "17419.725", "pbt.q_prev_year": "11033.915"})
    flag = flag_other_income(vcb)
    assert flag is not None and "46%" in flag.detail and "hoạt động khác" in flag.detail
    # lãi khác tăng ít so với mức tăng LNTT: không gắn cờ
    small = _Facts("TT200", **{"other_profit.q_cur": "12", "other_profit.q_prev_year": "10",
                               "pbt.q_cur": "200", "pbt.q_prev_year": "100"})
    assert flag_other_income(small) is None
    # LNTT giảm: không gắn cờ
    down = _Facts("TT200", **{"other_profit.q_cur": "50", "other_profit.q_prev_year": "0",
                              "pbt.q_cur": "90", "pbt.q_prev_year": "100"})
    assert flag_other_income(down) is None


def _bank_is(*rows):
    return {"company_template": "bank", "raw": {"IS": {"unit_text": "Đơn vị tính: triệu đồng", "rows": [
        {"stt": None, "code": None, "label": label, "note": None, "page": 1, "values": {"q_cur": value}}
        for label, value in rows]}}}


def test_parent_profit_is_computed_when_its_row_is_missing():
    # VPB quý 3/2026, bản scan 72 dpi: dòng "Lợi nhuận thuần cổ đông ngân hàng" bị đọc sót; trước đây thẻ lấy LNST chung
    from services.metrics.card import Facts
    rec = _bank_is(("Tổng lợi nhuận trước thuế", "11.030.887"), ("Chi phí thuế TNDN", "(2.167.977)"),
                   ("Lợi nhuận sau thuế", "8.862.910"), ("Lợi ích của cổ đông không kiểm soát", "(219.284)"))
    v = Facts(1, rec).metric("IS", "npat_parent", "q_cur")
    assert v.value == D("8643626") * 10**6 and "trừ" in v.computed


def test_parent_profit_is_left_blank_when_another_report_has_the_row():
    from services.metrics.card import Facts
    rec = _bank_is(("Tổng lợi nhuận trước thuế", "11.030.887"), ("Chi phí thuế TNDN", "(2.167.977)"),
                   ("Lợi nhuận sau thuế", "8.862.910"))
    assert Facts(1, rec).metric("IS", "npat_parent", "q_cur").value == D("8862910") * 10**6   # ngân hàng không tách
    v = Facts(1, rec, {("IS", "b.npat_parent")}).metric("IS", "npat_parent", "q_cur")
    assert v.value is None and "cần xem lại" in v.computed
