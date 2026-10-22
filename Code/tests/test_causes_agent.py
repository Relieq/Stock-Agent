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


def test_guard_reason_label_only_flags_matched_numbers_called_unchecked():
    from services.analyst.guard import check_sentence
    from services.analyst.sheet import FactSheet
    sh = FactSheet()
    sh.add("reason", "Nguyên nhân MSN nêu trong công văn giải trình (khớp BCTC): Lãi công ty liên kết tăng 13%", ticker="MSN")
    sh.add("reason", "Nguyên nhân MSN nêu trong công văn giải trình (theo công ty, chưa kiểm được bằng số): mảng vật liệu "
                     "phục hồi", ticker="MSN")
    bad = check_sentence("Theo công ty, lãi công ty liên kết tăng 13%, chưa kiểm chứng bằng số.", ["S1", "S2"], sh,
                         {"MSN"}, {"MSN"})
    assert [v.kind for v in bad.violations] == ["reason_label"]
    ok_words = check_sentence("Theo công ty, mảng vật liệu phục hồi; lời giải thích này chưa kiểm được bằng số.", ["S1", "S2"],
                              sh, {"MSN"}, {"MSN"})
    assert not [v for v in ok_words.violations if v.kind == "reason_label"]
    wrong = check_sentence("Mảng vật liệu phục hồi, đã đối chiếu khớp BCTC.", ["S2"], sh, {"MSN"}, {"MSN"})
    assert [v.kind for v in wrong.violations] == ["reason_label"]
