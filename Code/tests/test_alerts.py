from decimal import Decimal as D

from services.alerts import card_email
from services.metrics.card import Card, Metric, Value

B = D(10) ** 9


def metric(key, name, cur, prev, change):
    return Metric(key, name, Value(cur), Value(prev), Value(None), Value(None), q_change=change)


def test_email_lines_do_not_repeat_the_value_inside_the_change():
    card = Card(1, "TCB", 2026, "Q3", "TCTD", [
        metric("nii", "Thu nhập lãi thuần", 11700 * B, 9925 * B, "+17,9% (từ 9.925 tỷ lên 11.700 tỷ)"),
        metric("npat_parent", "LNST của cổ đông ngân hàng mẹ", 7943 * B, None, ""),
    ], [], [])
    subject, body = card_email(card, {"name": "Techcombank", "reviewed": "Chưa soát xét"})
    assert subject == "[Soi] TCB quý 3/2026: LNST 7.943 tỷ"
    assert "- Thu nhập lãi thuần quý: +17,9% (từ 9.925 tỷ lên 11.700 tỷ)" in body
    assert "- LNST của cổ đông ngân hàng mẹ quý: 7.943 tỷ" in body       # không có số cùng kỳ: chỉ ghi số kỳ này
    assert "((" not in body and "))" not in body
