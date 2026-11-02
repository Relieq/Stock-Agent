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


def test_email_takes_cause_sentences_without_the_headline():
    card = Card(1, "STB", 2026, "Q3", "TCTD", [metric("npat_parent", "LNST", 3000 * B, 2000 * B, "+50,0%")], [], [])
    causes = {"sentences": [
        {"text": "LNST quý 3/2026 tăng 1.000 tỷ.", "kinds": ["metric"]},
        {"text": "Thu dịch vụ tăng 3.582 tỷ, làm LNST tăng.", "kinds": ["cause_part"]},
        {"text": "Dự phòng tăng 4.685 tỷ, làm LNST giảm.", "kinds": ["cause_part"]},
        {"text": "Theo công ty, thu từ dịch vụ tăng.", "kinds": ["metric", "reason"]},
    ]}
    _, body = card_email(card, {"name": "Sacombank", "reviewed": "Chưa soát xét", "causes": causes})
    assert "Vì sao lợi nhuận thay đổi" in body
    assert "- Thu dịch vụ tăng 3.582 tỷ, làm LNST tăng." in body and "- Theo công ty, thu từ dịch vụ tăng." in body
    assert "LNST quý 3/2026 tăng 1.000 tỷ." not in body and "Dự phòng" not in body
    _, plain = card_email(card, {"name": "Sacombank", "reviewed": "Chưa soát xét", "causes": None})
    assert "Vì sao" not in plain
