from services.api.reports import SAMPLES, can_view
from services.users import User


def test_only_owner_and_admin_can_view():
    owner, other, admin = User(1, "a@x", "user", 3), User(2, "b@x", "user", 3), User(3, "c@x", "admin", 3)
    row = {"user_id": 1}
    assert can_view(row, owner) and can_view(row, admin) and not can_view(row, other) and not can_view(row, None)


def test_samples_cover_the_three_kinds():
    assert len(SAMPLES) == 3
