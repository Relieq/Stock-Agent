"""Chú thích phép kiểm của ô trên trang tài liệu viết bằng tên dòng, không lộ mã ràng buộc nội bộ."""
from decimal import Decimal

from services.api.data import evidence_words, sum_reason
from services.extraction.validate import Check


def test_evidence_words_use_row_labels():
    e = {"sum": ["IS_10"], "period": ["is_quarter:10:q_cur", "is_quarter:10:q_cur"], "differs": []}
    labels = {"10": "Doanh thu thuần", "01": "Doanh thu bán hàng", "02": "Các khoản giảm trừ doanh thu"}
    w = evidence_words(e, "TT200", labels)
    assert w["sum"] == ["Doanh thu thuần = Doanh thu bán hàng − Các khoản giảm trừ doanh thu"]
    assert w["period"] == ["số quý = lũy kế kỳ này − lũy kế kỳ trước"]
    assert w["differs"] == []


def test_group_rule_is_named_by_its_total_row():
    # ACB quý 3/2026: ô cần xem ảnh từng ghi "Phép cộng không khớp: CF_grp_b.cff"
    labels = {"b.cff": "LƯU CHUYỂN TIỀN THUẦN TỪ HOẠT ĐỘNG TÀI CHÍNH"}
    w = evidence_words({"sum": ["CF_grp_b.cff"], "period": [], "differs": []}, "TCTD", labels)
    assert w["sum"] == ["LƯU CHUYỂN TIỀN THUẦN TỪ HOẠT ĐỘNG TÀI CHÍNH = tổng các dòng con"]


def test_sum_reason_gives_printed_numbers():
    check = Check("CF_grp_b.cff", "ytd_cur", False, Decimal("-3265660000000"), Decimal("-4246972000000"),
                  Decimal(0), True, [])
    text = sum_reason("Lưu chuyển tiền thuần từ hoạt động tài chính = tổng các dòng con", check, Decimal(1000000))
    assert text == ("Phép cộng không khớp: Lưu chuyển tiền thuần từ hoạt động tài chính = tổng các dòng con. "
                    "Dòng tổng in −3.265.660, cộng các dòng con ra −4.246.972, lệch 981.312")


def test_evidence_words_keep_q1_note_and_unknown_template():
    w = evidence_words({"sum": ["Q1: quý = lũy kế"], "period": [], "differs": ["bs_begin:x:begin_year"]}, None, {})
    assert w["sum"] == ["Q1: quý = lũy kế"]
    assert w["differs"] == ["số đầu năm so với BCTC kỳ trước"]
