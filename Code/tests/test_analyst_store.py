"""Chọn cột và ẩn ô "cần xem lại" khi nạp số cho agent báo cáo (không cần CSDL)."""

from decimal import Decimal

from services.analyst import store
from services.extraction.rules import BANK_INCOME_PARTS
from services.metrics.card import Source, Value


def test_columns_quarter_basis():
    assert store.columns("fs_quarter", "Q3", "quarter") == (("q_cur",), ("q_prev_year",))


def test_columns_ytd_of_quarter_report_uses_only_ytd_columns():
    assert store.columns("fs_quarter", "Q3", "ytd") == (("ytd_cur",), ("ytd_prev_year",))
    assert store.columns("fs_quarter", "Q2", "ytd") == (("ytd_cur",), ("ytd_prev_year",))


def test_columns_ytd_falls_back_to_quarter_columns_only_when_they_are_the_same_thing():
    both = (("ytd_cur", "q_cur"), ("ytd_prev_year", "q_prev_year"))
    assert store.columns("fs_quarter", "Q1", "ytd") == both
    assert store.columns("fs_semiannual", "H1", "ytd") == both
    assert store.columns("fs_annual", "FY", "ytd") == both


class FakeFacts:
    """Chỉ có metric() và code() như Facts thật."""

    def __init__(self, values, codes=None):
        self.values = values          # (metric, column) -> Value
        self.codes = codes or {}

    def metric(self, statement, metric, column):
        return self.values.get((metric, column), Value(None))

    def code(self, statement, metric):
        return self.codes.get(metric)


def src(code, col):
    return Source(1, "IS", code, col, 1, "", None)


def test_first_hides_cell_marked_for_review():
    f = FakeFacts({("npat", "q_cur"): Value(Decimal(5), src("60", "q_cur"))})
    assert store._first(f, "npat", ("q_cur",), {("IS", "60", "q_cur")}).value is None
    assert store._first(f, "npat", ("q_cur",), set()).value == Decimal(5)


def test_first_hides_bank_total_summed_from_hidden_part():
    f = FakeFacts({("toi", "q_cur"): Value(Decimal(100), None, "Cộng các khoản")})
    hidden = {("IS", BANK_INCOME_PARTS[2], "q_cur")}
    assert store._first(f, "toi", ("q_cur",), hidden).value is None
    # ô ẩn ở cột khác thì không ảnh hưởng
    assert store._first(f, "toi", ("q_cur",), {("IS", BANK_INCOME_PARTS[2], "q_prev_year")}).value == Decimal(100)


def test_first_hides_parent_profit_computed_from_hidden_npat_or_minority():
    f = FakeFacts({("npat_parent", "q_cur"): Value(Decimal(80), None, "NPAT trừ lợi ích không kiểm soát")},
                  {"npat": "60", "minority": "62"})
    assert store._first(f, "npat_parent", ("q_cur",), {("IS", "60", "q_cur")}).value is None
    assert store._first(f, "npat_parent", ("q_cur",), {("IS", "62", "q_cur")}).value is None
    assert store._first(f, "npat_parent", ("q_cur",), set()).value == Decimal(80)


def test_first_keeps_derived_value_for_other_metrics():
    f = FakeFacts({("pbt", "q_cur"): Value(Decimal(7), None)}, {"npat": "60", "minority": "62"})
    assert store._first(f, "pbt", ("q_cur",), {("IS", "60", "q_cur")}).value == Decimal(7)


def test_first_falls_through_to_next_column_when_first_is_empty():
    f = FakeFacts({("npat", "q_cur"): Value(Decimal(9), src("60", "q_cur"))})
    assert store._first(f, "npat", ("ytd_cur", "q_cur"), set()).value == Decimal(9)


def test_flags_on_computed_parent_profit_drop_when_an_input_is_hidden():
    from services.metrics.card import Flag
    f = FakeFacts({("npat_parent", "q_cur"): Value(Decimal(-5), None, "NPAT trừ lợi ích không kiểm soát"),
                   ("npat_parent", "q_prev_year"): Value(Decimal(3), None, "NPAT trừ lợi ích không kiểm soát")},
                  {"npat": "60", "minority": "62"})
    flags = [Flag("sign_change", "Lỗ hoặc đổi dấu lợi nhuận", "chuyển từ lãi sang lỗ"),
             Flag("low_base", "Tăng trưởng do nền so sánh thấp", "nền thấp"),
             Flag("cash", "Có lãi nhưng dòng tiền kinh doanh âm", "dòng tiền", [src("20", "ytd_cur")])]
    assert [t for t, _ in store.visible_flags(flags, f, set())] == [x.title for x in flags]
    # ô LNST cùng kỳ "cần xem lại": hai cờ dựa trên LNST mẹ tính ra bị bỏ, cờ khác giữ
    assert [t for t, _ in store.visible_flags(flags, f, {("IS", "60", "q_prev_year")})] == \
        ["Có lãi nhưng dòng tiền kinh doanh âm"]
    assert [t for t, _ in store.visible_flags(flags, f, {("IS", "62", "q_cur")})] == \
        ["Có lãi nhưng dòng tiền kinh doanh âm"]
    # ô ẩn ở cột lũy kế không ảnh hưởng cờ tính trên số quý; ô nguồn của cờ bị ẩn thì bỏ cờ đó
    assert len(store.visible_flags(flags, f, {("IS", "60", "ytd_cur")})) == 3
    assert [t for t, _ in store.visible_flags(flags, f, {("IS", "20", "ytd_cur")})] == \
        ["Lỗ hoặc đổi dấu lợi nhuận", "Tăng trưởng do nền so sánh thấp"]
    # LNST mẹ có nguồn riêng (không phải số tính): ô NPAT bị ẩn không ảnh hưởng
    g = FakeFacts({("npat_parent", "q_cur"): Value(Decimal(-5), src("61", "q_cur")),
                   ("npat_parent", "q_prev_year"): Value(Decimal(3), src("61", "q_prev_year"))},
                  {"npat": "60", "minority": "62"})
    assert len(store.visible_flags(flags[:2], g, {("IS", "60", "q_cur")})) == 2
