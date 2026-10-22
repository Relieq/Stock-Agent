"""Dòng bảng số của agent tìm nguyên nhân (không CSDL, không gọi mô hình)."""
from decimal import Decimal as D

from services.causes.agent import part_text
from services.causes.decompose import Part

B = D(10) ** 9


def test_income_line_turning_to_loss_says_loss():
    p = Part("b.ntrading", "Lãi thuần mua bán chứng khoán kinh doanh", D(-363) * B, D(1287) * B, D(-1650) * B)
    t = part_text(p, "quý 3/2026", "VPB")
    assert "lỗ 363 tỷ, cùng kỳ 1.287 tỷ (giảm 1.650 tỷ), làm LNST giảm 1.650 tỷ" in t


def test_expense_printed_positive_or_negative_reads_as_size():
    up = Part("25", "Chi phí bán hàng", D(4612) * B, D(3357) * B, D(-1255) * B, expense=True)
    neg = Part("b.opex", "Chi phí hoạt động", D(-5295) * B, D(-4493) * B, D(-802) * B, expense=True)
    assert "4.612 tỷ, cùng kỳ 3.357 tỷ (tăng 1.255 tỷ), làm LNST giảm 1.255 tỷ" in part_text(up, "quý 3/2026", "MSN")
    assert "5.295 tỷ, cùng kỳ 4.493 tỷ (tăng 802 tỷ), làm LNST giảm 802 tỷ" in part_text(neg, "quý 3/2026", "TCB")
