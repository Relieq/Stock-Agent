from decimal import Decimal as D

from services.analyst.explanations import check_reason, check_section, parse_number, parse_pct


class FakeFacts:
    """Thay Facts: số theo (chỉ tiêu, cột), đơn vị đồng."""

    def __init__(self, **vals):
        self.vals = vals

    def metric(self, statement, metric, column):
        from services.metrics.card import Value
        v = self.vals.get(f"{metric}.{column}")
        return Value(None if v is None else D(v))


B = 10**9


def test_numbers_as_printed_in_letters():
    assert parse_number("2.757,6") == (D("2757.6"), D("0.05"))
    assert parse_number("(1.547,8)")[0] == D("-1547.8")
    assert parse_number("8.862.910") == (D("8862910"), D("0.5"))
    assert parse_pct("tăng 78%") == 78 and parse_pct("tương đương 20,36% so với cùng kỳ") == D("20.36")
    assert parse_pct("lợi nhuận thay đổi từ 10% trở lên so với cùng kỳ") is None     # trích quy định (BSR)


def test_headline_profit_and_change_are_checked_against_the_statement():
    # MWG quý 1/2026: "Lợi nhuận sau thuế hợp nhất quý 1/2026 đạt 2.757,6 tỷ VNĐ, tăng 78% so với cùng kỳ là 1.547,8 tỷ"
    facts = FakeFacts(**{"npat.q_cur": 2757_6 * B // 10 + 31_000_000, "npat.q_prev_year": 1547_8 * B // 10 - 20_000_000})
    sec = {"scope": "consolidated", "period_kind": "quarter", "metric_label": "Lợi nhuận sau thuế hợp nhất",
           "value_cur": "2.757,6", "value_prev": "1.547,8", "unit": "tỷ VNĐ", "change_text": "tăng 78%", "reasons": []}
    verdicts = [c.verdict for c in check_section(sec, facts).checks]
    assert verdicts == ["khớp", "khớp", "khớp"]
    sec["value_cur"] = "2.775,6"                      # sai một chữ số
    assert [c.verdict for c in check_section(sec, facts).checks][0] == "lệch"


def test_reasons_with_numbers_segments_and_words():
    facts = FakeFacts(**{"revenue.q_cur": 28118 * B, "revenue.q_prev_year": 18315 * B,
                         "cogs.q_cur": 19207 * B, "cogs.q_prev_year": 12626 * B})
    r = {"text": "Doanh thu tăng 54%", "about": "company", "line_item": "revenue", "direction": "up", "pct": "54%",
         "amount": None, "amount_unit": None}
    assert check_reason(r, facts, "quarter").verdict == "khớp"
    assert check_reason(r | {"pct": "45%"}, facts, "quarter").verdict == "lệch"
    # MWG: số của một chuỗi cửa hàng, BCTC không tách
    assert check_reason(r | {"about": "segment", "pct": "34%"}, facts, "quarter").verdict == "không kiểm được"
    # chỉ nói tăng/giảm: so chiều; chi phí tính theo độ lớn
    assert check_reason(r | {"pct": None, "line_item": "cogs"}, facts, "quarter").verdict == "khớp chiều"
    assert check_reason(r | {"pct": None, "line_item": "cogs", "direction": "down"}, facts, "quarter").verdict == "ngược chiều"
    assert check_reason(r | {"pct": None, "line_item": "unspecified"}, facts, "quarter").verdict == "không kiểm được"


def test_separate_statement_sections_are_not_checked_yet():
    sec = {"scope": "separate", "period_kind": "quarter", "metric_label": None, "value_cur": None, "value_prev": None,
           "unit": None, "change_text": None, "reasons": []}
    assert check_section(sec, None).checks[0].verdict == "không kiểm được"


def test_sign_flip_percent_as_letters_compute_it():
    # Lãi thuần ngoại hối 119.466 triệu thành lỗ 419.768 triệu: công văn ghi "-451,37%"
    facts = FakeFacts(**{"fx.q_cur": -419_768 * 10**6, "fx.q_prev_year": 119_466 * 10**6})
    r = {"text": "Lãi/(lỗ) thuần từ hoạt động kinh doanh ngoại hối giảm", "about": "company", "line_item": "fx",
         "direction": "down", "number_kind": "change", "pct": "-451,37%", "amount": None, "amount_unit": None}
    assert check_reason(r, facts, "quarter").verdict == "khớp"


def test_revenue_headline_is_checked_against_revenue():
    # VJC bán niên 2026: phần "Doanh thu bán hàng và cung cấp dịch vụ 51.536 tỷ đồng, tăng 44%"
    facts = FakeFacts(**{"revenue.ytd_cur": 51_536 * B, "revenue.ytd_prev_year": 35_837 * B,
                         "npat.ytd_cur": 1_372 * B, "npat.ytd_prev_year": 1_294 * B})
    sec = {"scope": "consolidated", "period_kind": "half_year", "metric_label": "Doanh thu bán hàng và cung cấp dịch vụ",
           "value_cur": "51.536", "value_prev": "35.837", "unit": "tỷ đồng", "change_text": "tăng trưởng 44%", "reasons": []}
    assert [c.verdict for c in check_section(sec, facts).checks] == ["khớp", "khớp", "khớp"]


def test_amount_change_across_zero_uses_signed_difference():
    # ACB quý 2/2026: lãi thuần chứng khoán đầu tư (21.303) so với 446.091 triệu: "giảm 467.394 triệu đồng"
    facts = FakeFacts(**{"invest_sec.q_cur": -21_303 * 10**6, "invest_sec.q_prev_year": 446_091 * 10**6})
    r = {"text": "Lãi thuần từ mua bán chứng khoán đầu tư giảm", "about": "company", "line_item": "invest_sec",
         "direction": "down", "number_kind": "change", "pct": None, "amount": "467.394", "amount_unit": "triệu đồng"}
    assert check_reason(r, facts, "quarter").verdict == "khớp"
