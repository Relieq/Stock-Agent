from decimal import Decimal as D

from services.extraction.evidence import Cells, cell_status, compare_periods, compare_same_date


def _cells(doc_id, period, values, restated=()):
    return Cells(doc_id, period, {k: {c: D(v) for c, v in cols.items()} for k, cols in values.items()},
                 {k: k[1] for k in values}, {"BS": D(1), "IS": D(1), "CF": D(1)}, set(restated))


def test_quarter_identity_and_begin_balance():
    q1 = _cells(1, "Q1", {("IS", "10"): {"q_cur": 100, "q_prev_year": 80},
                          ("BS", "110"): {"end_period": 50, "begin_year": 40}})
    q2 = _cells(2, "Q2", {("IS", "10"): {"q_cur": 120, "q_prev_year": 90, "ytd_cur": 220, "ytd_prev_year": 170},
                          ("BS", "110"): {"end_period": 60, "begin_year": 40}})
    checks = compare_periods(q1, q2)
    assert {(c.kind, c.column) for c in checks} == {("is_quarter", "q_cur"), ("is_quarter", "q_prev_year"),
                                                    ("bs_begin", "begin_year")}
    assert all(c.passed for c in checks)
    status = cell_status(q2, checks)
    assert status[("IS", "10", "q_cur")]["status"] == "period"
    assert status[("BS", "110", "end_period")]["status"] == "none"   # không có kỳ nào khác in số cuối quý 2


def test_misread_cell_is_suspected_unless_restated():
    q1 = _cells(1, "Q1", {("IS", "10"): {"q_cur": 100, "q_prev_year": 80}})
    q2 = _cells(2, "Q2", {("IS", "10"): {"q_cur": 130, "q_prev_year": 90, "ytd_cur": 220, "ytd_prev_year": 170}})
    status = cell_status(q2, compare_periods(q1, q2))
    assert status[("IS", "10", "q_cur")]["status"] == "conflict"
    assert status[("IS", "10", "ytd_cur")]["status"] == "conflict"     # chưa biết ô nào sai: cả hai cần xem

    q2r = _cells(2, "Q2", {("IS", "10"): {"q_cur": 120, "q_prev_year": 99, "ytd_cur": 220, "ytd_prev_year": 170}},
                 restated={("IS", "q_prev_year")})
    status = cell_status(q2r, compare_periods(q1, q2r))
    assert status[("IS", "10", "q_prev_year")]["status"] == "restated"


def test_quarter_two_against_semiannual_report():
    q2 = _cells(2, "Q2", {("BS", "110"): {"end_period": 60, "begin_year": 40},
                          ("CF", "20"): {"ytd_cur": 300, "ytd_prev_year": 250}})
    h1 = _cells(3, "H1", {("BS", "110"): {"end_period": 60, "begin_year": 40},
                          ("CF", "20"): {"q_cur": 300, "q_prev_year": 260}})       # bán niên: mô hình gán cột là q_*
    checks = compare_same_date(q2, h1)
    assert sorted((c.statement, c.column, c.passed) for c in checks) == [
        ("BS", "begin_year", True), ("BS", "end_period", True), ("CF", "ytd_cur", True), ("CF", "ytd_prev_year", False)]


def test_verified_reread_turns_suspect_into_real_difference():
    q2 = _cells(2, "Q2", {("BS", "311"): {"end_period": 2156010734465}})
    h1 = _cells(3, "H1", {("BS", "311"): {"end_period": 2156010634465}})       # khác 1 chữ số: dạng đọc sai
    [check] = compare_same_date(q2, h1)
    assert check.suspect_misread
    assert cell_status(q2, [check])[("BS", "311", "end_period")]["status"] == "conflict"

    q2.verified.add(("BS", "311", "end_period"))
    h1.verified.add(("BS", "311", "end_period"))       # đọc lại cả hai bản ở ảnh nét hơn, vẫn ra như cũ
    [check] = compare_same_date(q2, h1)
    assert not check.suspect_misread
    assert cell_status(q2, [check])[("BS", "311", "end_period")]["status"] == "differs"


def test_year_end_is_next_year_begin_balance():
    from services.extraction.evidence import compare_year_start
    q4 = _cells(1, "Q4", {("BS", "110"): {"end_period": 70000, "begin_year": 40}, ("IS", "10"): {"q_cur": 5}})
    q1 = _cells(2, "Q1", {("BS", "110"): {"end_period": 90, "begin_year": 70000}, ("IS", "10"): {"q_cur": 6}})
    [check] = compare_year_start(q4, q1)
    assert (check.kind, check.statement, check.passed) == ("year_start", "BS", True)
    q1.values[("BS", "110")]["begin_year"] = D(64321)     # BCTC năm đã kiểm toán sửa số cuối quý 4: chênh lớn, không nghi đọc sai
    [check] = compare_year_start(q4, q1)
    assert not check.passed and not check.suspect_misread


def test_digit_slip_includes_one_missing_digit():
    # STB quý 4/2025: chữ số đầu dưới con dấu bị mất (15.980.444 đọc thành 5.980.444)
    from decimal import Decimal
    from services.extraction.evidence import digit_slip
    assert digit_slip(Decimal("5980444000000"), Decimal("15980444000000"))
    assert digit_slip(Decimal("1234567"), Decimal("1234867"))
    assert not digit_slip(Decimal("5980444"), Decimal("15980445"))
    assert not digit_slip(Decimal("100"), Decimal("250000"))


def test_second_reading_only_for_cells_without_any_check():
    q1 = _cells(1, "Q1", {("IS", "10"): {"q_cur": 100, "q_prev_year": 80}})
    q2 = _cells(2, "Q2", {("IS", "10"): {"q_cur": 120, "q_prev_year": 90, "ytd_cur": 220, "ytd_prev_year": 170},
                          ("BS", "b.ob1"): {"end_period": 5_000, "begin_year": 4_000},
                          ("BS", "b.ob2"): {"end_period": 7_000}})
    second = _cells(2, "Q2", {("IS", "10"): {"q_cur": 999},                 # có phép kiểm: không dùng lần đọc thứ hai
                              ("BS", "b.ob1"): {"end_period": 5, "begin_year": 4_100},   # 5 nghìn: cùng chữ số
                              })
    status = cell_status(q2, compare_periods(q1, q2), second)
    assert status[("IS", "10", "q_cur")]["status"] == "period"
    assert status[("BS", "b.ob1", "end_period")]["status"] == "second"
    assert status[("BS", "b.ob1", "begin_year")]["status"] == "second_differs"
    assert status[("BS", "b.ob1", "begin_year")]["second_printed"] == "4.100"
    assert status[("BS", "b.ob2", "end_period")]["status"] == "none"        # người đọc thứ hai không thấy dòng này


def test_second_reading_of_full_period_report_matches_either_column_pair():
    h1 = _cells(3, "H1", {("CF", "b.cf1"): {"q_cur": 300}})
    second = _cells(3, "H1", {("CF", "b.cf1"): {"ytd_cur": 300}})
    assert cell_status(h1, [], second, "fs_semiannual")[("CF", "b.cf1", "q_cur")]["status"] == "second"


def test_earnings_per_share_is_compared_only_with_the_second_reading():
    q2 = _cells(2, "Q2", {("IS", "10"): {"q_cur": 120}})
    q2.eps = {("IS", "eps70"): {"q_cur": D(1_234), "ytd_cur": D(2_000)}}
    second = _cells(2, "Q2", {})
    second.eps = {("IS", "eps70"): {"q_cur": D(1_234), "ytd_cur": D(2_600)}}
    assert cell_status(q2, [])[("IS", "eps70", "q_cur")]["status"] == "none"
    status = cell_status(q2, [], second)
    assert status[("IS", "eps70", "q_cur")]["status"] == "second"
    assert status[("IS", "eps70", "ytd_cur")]["status"] == "second_differs"
    assert status[("IS", "eps70", "ytd_cur")]["second_printed"] == "2.600"


def test_first_quarter_earnings_per_share_quarter_equals_year_to_date():
    q1 = _cells(1, "Q1", {})
    q1.eps = {("IS", "eps70"): {"q_cur": D(1_651), "ytd_cur": D(1_651), "q_prev_year": D(68), "ytd_prev_year": D(68)}}
    second = _cells(1, "Q1", {})
    second.eps = {("IS", "eps70"): {"q_cur": D(1_651), "ytd_cur": D(1_651), "q_prev_year": D(98), "ytd_prev_year": D(68)}}
    status = cell_status(q1, [], second, "fs_quarter")
    assert {status[("IS", "eps70", c)]["status"] for c in q1.eps[("IS", "eps70")]} == {"sum"}   # BSR quý 1/2026
    q1.eps[("IS", "eps70")]["q_prev_year"] = D(98)
    assert cell_status(q1, [], second, "fs_quarter")[("IS", "eps70", "q_prev_year")]["status"] == "conflict"


def test_row_missing_from_a_report_is_found_by_the_same_number_on_another_report():
    from services.extraction.evidence import missing_rows
    # Quý 1 và quý 2 cùng năm in cùng số đầu năm. Quý 2 đánh mã khác (TT99) nhưng có đúng số đó: không thiếu
    q1 = _cells(1, "Q1", {("BS", "330"): {"begin_year": 389}, ("BS", "337"): {"begin_year": 389},
                          ("BS", "300"): {"begin_year": 1000}})
    q1.sum_evidence = {("BS", k, "begin_year"): ["x"] for k in ("330", "337", "300")}
    q2 = _cells(2, "Q2", {("BS", "300"): {"begin_year": 1000}, ("BS", "331"): {"begin_year": 389}})
    assert missing_rows(q2, q1, "earlier") == []
    # Quý 2 không có dòng nào mang số 389: thiếu cả hai dòng 330, 337
    q2 = _cells(2, "Q2", {("BS", "300"): {"begin_year": 1000}})
    assert [m.key for m in missing_rows(q2, q1, "earlier")] == ["330", "337"]
    # Dòng KQKD có lũy kế ở quý trước thì quý này phải có dòng cùng mã hoặc cùng tên
    q1 = _cells(1, "Q1", {("IS", "b.oi"): {"ytd_cur": 50}})
    q1.sum_evidence = {("IS", "b.oi", "ytd_cur"): ["x"]}
    q2 = _cells(2, "Q2", {("IS", "b.nother"): {"ytd_cur": 70}})
    assert [m.key for m in missing_rows(q2, q1, "earlier")] == ["b.oi"]
    q2.printed = {("IS", "b.oi")}             # dòng có in nhưng để trống ("-"): không coi là thiếu
    assert missing_rows(q2, q1, "earlier") == []


def test_reviewer_confirms_first_reading_from_the_image():
    # VPB quý 3/2026: lãi cơ bản trên cổ phiếu lũy kế in 2.323, người đọc thứ hai đọc ra 4; người duyệt xem ảnh xác nhận
    q3 = _cells(3, "Q3", {("IS", "10"): {"q_cur": 120}})
    q3.eps = {("IS", "eps"): {"ytd_cur": D(2_323)}}
    second = _cells(3, "Q3", {})
    second.eps = {("IS", "eps"): {"ytd_cur": D(4)}}
    assert cell_status(q3, [], second)[("IS", "eps", "ytd_cur")]["status"] == "second_differs"
    q3.image_confirmed = {("IS", "eps", "ytd_cur"): D(2_323)}
    assert cell_status(q3, [], second)[("IS", "eps", "ytd_cur")]["status"] == "image_ok"
    q3.eps = {("IS", "eps"): {"ytd_cur": D(2_328)}}          # số đổi sau khi xác nhận: xác nhận hết hiệu lực
    assert cell_status(q3, [], second)[("IS", "eps", "ytd_cur")]["status"] == "second_differs"
