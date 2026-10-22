"""Chú thích phép kiểm của ô trên trang tài liệu viết bằng tên dòng, không lộ mã ràng buộc nội bộ."""
from services.api.data import evidence_words


def test_evidence_words_use_row_labels():
    e = {"sum": ["IS_10"], "period": ["is_quarter:10:q_cur", "is_quarter:10:q_cur"], "differs": []}
    labels = {"10": "Doanh thu thuần", "01": "Doanh thu bán hàng", "02": "Các khoản giảm trừ doanh thu"}
    w = evidence_words(e, "TT200", labels)
    assert w["sum"] == ["Doanh thu thuần = Doanh thu bán hàng − Các khoản giảm trừ doanh thu"]
    assert w["period"] == ["số quý = lũy kế kỳ này − lũy kế kỳ trước"]
    assert w["differs"] == []


def test_evidence_words_keep_q1_note_and_unknown_template():
    w = evidence_words({"sum": ["Q1: quý = lũy kế"], "period": [], "differs": ["bs_begin:x:begin_year"]}, None, {})
    assert w["sum"] == ["Q1: quý = lũy kế"]
    assert w["differs"] == ["số đầu năm so với BCTC kỳ trước"]
