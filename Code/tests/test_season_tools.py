from datetime import date, datetime, timezone
from decimal import Decimal

from services.metrics.calendar import Entry, current_quarter, deadline, quarter_end
from services.metrics.card import Card, Metric, Value
from services.metrics.service import growth


def _card(cur, prev):
    m = Metric("npat_parent", "LNST", Value(Decimal(cur)), Value(Decimal(prev)), Value(None), Value(None))
    return Card(1, "AAA", 2026, "Q2", "TT99", [m], [], [])


def test_growth_groups_follow_loss_wording_rules():
    assert growth(_card(120, 100)) == {"group": "up", "pct": 20.0}
    assert growth(_card(80, 100))["group"] == "down"
    assert growth(_card(50, -10)) == {"group": "to_profit", "pct": None}    # không in % khi có kỳ lỗ
    assert growth(_card(-5, 10))["group"] == "to_loss"
    assert growth(_card(-5, -10))["group"] == "loss"


def test_deadlines_and_current_quarter():
    assert quarter_end(2026, "Q3") == date(2026, 9, 30)
    assert deadline(2026, "Q3", consolidated=False) == date(2026, 10, 20)
    assert deadline(2026, "Q3", consolidated=True) == date(2026, 10, 30)
    assert current_quarter(date(2026, 10, 13)) == (2026, "Q3")
    assert current_quarter(date(2027, 1, 5)) == (2026, "Q4")


def test_calendar_status():
    end = quarter_end(2026, "Q3")
    e = Entry("AAA", "A", True, end, deadline(2026, "Q3", True), None, 26, 6)
    assert e.expected == date(2026, 10, 26)
    assert e.status(date(2026, 10, 20)) == "pending"
    assert e.status(date(2026, 10, 31)) == "overdue"
    e.published = datetime(2026, 11, 1, 3, tzinfo=timezone.utc)
    assert e.status(date(2026, 11, 2)) == "late"
