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
