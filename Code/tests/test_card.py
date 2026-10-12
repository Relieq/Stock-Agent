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
