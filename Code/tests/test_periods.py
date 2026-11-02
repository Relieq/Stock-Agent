"""Tiêu đề cột phải đúng kỳ của BCTC (VCB quý 3/2026 chép nhầm phụ lục số năm 2025)."""
from services.extraction.periods import period_problem
from services.extraction.pipeline import _statement_blocks


def cols(*pairs):
    return {"columns": [{"header": h, "kind": k} for h, k in pairs]}


def test_appendix_of_last_year_is_wrong_period():
    bs = cols(("31/12/2025 Triệu VND (Số Kiểm toán Nhà nước) (Trình bày lại)", "end_period"),
              ("31/12/2025 (Đã công bố)", "other"), ("Chênh lệch", "other"))
    assert "2025" in period_problem("BS", bs, 2026, "Q3")
    is_ = cols(("Năm 2025 (Trình bày lại)", "other"), ("Năm 2025 (Đã công bố)", "other"), ("Chênh lệch", "other"))
    assert period_problem("IS", is_, 2026, "Q3")


def test_right_period_and_unlabelled_current_columns_pass():
    assert period_problem("BS", cols(("30/09/2026", "end_period"), ("01/01/2026", "begin_year")), 2026, "Q3") is None
    assert period_problem("BS", cols(("Ngày 30.9.2026", "end_period")), 2026, "Q3") is None
    assert "cuối kỳ là 30/9/2026" in period_problem("BS", cols(("30/06/2026", "end_period")), 2026, "Q3")
    # BID, HDB bán niên 2026: mô hình gán "other" cho "Kỳ này", tiêu đề không ghi năm
    assert period_problem("IS", cols(("Kỳ này", "other"), ("Kỳ trước", "other")), 2026, "H1") is None
    assert period_problem("IS", cols(("Quý 3/2026", "q_cur"), ("Quý 3/2025", "q_prev_year")), 2026, "Q3") is None
    assert period_problem("IS", {"rows": []}, 2026, "Q3") is None        # bản ghi cũ không lưu tiêu đề cột


def test_blocks_keep_every_run_of_pages_in_file_order():
    kinds = ["letter", "balance_sheet", "balance_sheet", "income_statement", "notes", "balance_sheet",
             "income_statement", "income_statement", "cash_flow"]
    pages = [{"page": i + 1, "kind": k, "language": "vi"} for i, k in enumerate(kinds)]
    assert _statement_blocks(pages) == {"BS": [[2, 3], [6]], "IS": [[4], [7, 8]], "CF": [[9]]}
