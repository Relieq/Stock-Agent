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


def test_note_numbers_and_block_inside_multi_line_table():
    from services.causes.notes import note_numbers
    assert note_numbers("26, 28") == [26, 28] and note_numbers("24.1") == [24] and note_numbers(None) == []
    raw = {"title": "CHI PHÍ BÁN HÀNG VÀ QUẢN LÝ", "pages": [40], "columns": ["6T/2026", "6T/2025"], "rows": [
        {"label": "Chi phí bán hàng", "values": ["11.265", "9.106"], "is_total": False},
        {"label": "Dịch vụ mua ngoài", "values": ["5.380", "4.479"], "is_total": False},
        {"label": "Nhân viên", "values": ["3.908", "3.210"], "is_total": False},
        {"label": "Khấu hao", "values": ["680", "957"], "is_total": False},
        {"label": "Khác", "values": ["1.298", "460"], "is_total": False},
        {"label": "Chi phí quản lý", "values": ["2.841", "2.416"], "is_total": False},
        {"label": "Nhân viên", "values": ["2.760", "2.324"], "is_total": False},
        {"label": "Khác", "values": ["81", "92"], "is_total": False}]}
    nt = match_note(raw, 26, {"ytd": (-D(11_265) * M * 1000, -D(9_106) * M * 1000)}, M * 1000 * 5)
    assert nt.verified and [lab for lab, *_ in nt.items] == ["Dịch vụ mua ngoài", "Nhân viên", "Khấu hao", "Khác"]
    adm = match_note(raw, 26, {"ytd": (D(2_841) * M * 1000, D(2_416) * M * 1000)}, M * 1000 * 5)
    assert adm.verified and len(adm.items) == 2


def test_section_numbering_refs():
    from services.causes.notes import note_refs, ref_text, roman_value
    assert roman_value("VI.") == 6 and roman_value("IV") == 4 and roman_value("27.") is None
    assert note_refs("VI.14") == [(6, 14)] and note_refs("26, 28") == [(None, 26), (None, 28)]
    assert note_refs("VI.12.2") == [(6, 12)] and note_refs("V.4(c)") == [(5, 4)]
    assert ref_text(6, 14) == "VI.14" and ref_text(None, 27) == "27"


def test_nested_table_subset_matches_both_columns_or_nothing():
    raw = {"title": "THU NHẬP LÃI", "pages": [30], "columns": ["6T/2026", "6T/2025"], "rows": [
        {"label": "Lãi tiền gửi", "values": ["4.462", "2.995"], "is_total": False},
        {"label": "Lãi cho vay", "values": ["79.470", "62.791"], "is_total": False},
        {"label": "Lãi chứng khoán nợ", "values": ["6.479", "4.974"], "is_total": False},
        {"label": "- kinh doanh", "values": ["634", "127"], "is_total": False},
        {"label": "- đầu tư", "values": ["5.845", "4.847"], "is_total": False},
        {"label": "Cộng", "values": ["90.411", "70.760"], "is_total": True}]}
    nt = match_note(raw, 14, {"ytd": (D(90_411) * M, D(70_760) * M)}, M * 5)
    assert nt.verified and len(nt.items) == 4          # tập nhiều dòng nhất: hai dòng con thay cho dòng cha
    assert "Lãi chứng khoán nợ" not in [lab for lab, *_ in nt.items]
