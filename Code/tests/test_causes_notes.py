"""Đối chiếu bảng thuyết minh đã chép với dòng KQKD (không CSDL, không gọi mô hình)."""
from decimal import Decimal as D

from services.causes.notes import match_note, note_number

M = D(10) ** 6      # KQKD tính bằng đồng, thuyết minh in triệu đồng


def test_note_number_forms():
    assert note_number("27") == 27 and note_number("VI.25") == 25 and note_number("5.1") == 5
    assert note_number("27. DOANH THU") == 27 and note_number(None) is None and note_number("Cộng") is None


def test_revenue_items_minus_deductions_match_ytd_columns():
    raw = {"title": "TỔNG DOANH THU", "pages": [67], "columns": ["9T/2026", "9T/2025"], "rows": [
        {"label": "Tổng doanh thu", "values": [None, None], "is_total": False},
        {"label": "Thành phẩm, hàng hóa", "values": ["89.350.481", "58.627.117"], "is_total": False},
        {"label": "Chiết khấu", "values": ["185.345", "171.789"], "is_total": False},
        {"label": "Hàng bán bị trả lại", "values": ["46.664", "79.824"], "is_total": False},
        {"label": "Doanh thu thuần", "values": ["89.118.472", "58.375.504"], "is_total": True}]}
    pairs = {"quarter": (D(36_981_040) * M, D(21_163_826) * M), "ytd": (D(89_118_472) * M, D(58_375_504) * M)}
    nt = match_note(raw, 27, pairs, M * 5)
    assert nt.verified and nt.period == "ytd"
    assert nt.items[0] == ("Thành phẩm, hàng hóa", D(89_350_481) * M, D(58_627_117) * M)
    assert nt.items[1][1] == -D(185_345) * M


def test_only_total_matches_is_reported_and_mismatch_rejected():
    raw = {"title": "X", "pages": [5], "columns": ["a", "b"], "rows": [
        {"label": "A", "values": ["10.000", "8.000"], "is_total": False},
        {"label": "A1 (trong đó)", "values": ["4.000", "3.000"], "is_total": False},
        {"label": "Cộng", "values": ["10.000", "8.000"], "is_total": True}]}
    nt = match_note(raw, 9, {"quarter": (D(10_000) * M, D(8_000) * M)}, M)
    assert not nt.verified and nt.items and "dòng tổng" in nt.note
    bad = match_note(raw, 9, {"quarter": (D(99_000) * M, D(8_000) * M)}, M)
    assert bad.items == [] and "không bằng" in bad.note
    assert "không tìm thấy" in match_note(None, 9, {}, M).note
