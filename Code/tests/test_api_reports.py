from services.api.reports import SAMPLES, can_view
from services.users import User


def test_only_owner_and_admin_can_view():
    owner, other, admin = User(1, "a@x", "user", 3), User(2, "b@x", "user", 3), User(3, "c@x", "admin", 3)
    row = {"user_id": 1}
    assert can_view(row, owner) and can_view(row, admin) and not can_view(row, other) and not can_view(row, None)


def test_samples_cover_the_four_kinds():
    assert len(SAMPLES) == 4


def test_xac_nhan_hien_so_tien_kieu_viet_va_bao_bctc_het_han_muc():
    from services.api.reports import confirm_view
    items = [{"ticker": "FPT", "year": 2025, "period": "Q3", "can_read": True, "usd": 0.083},
             {"ticker": "TCB", "year": 2025, "period": "Q3", "can_read": True, "usd": 0.083},
             {"ticker": "VCB", "year": 2025, "period": "Q3", "can_read": False, "note": "đang chờ duyệt tay"}]
    v = confirm_view(items, used=4, quota=5)
    assert v["remaining"] == 1 and v["skipped"] == 1
    assert [i["state"] for i in v["rows"]] == ["read", "quota", "no"]
    assert v["rows"][0]["label"] == "quý 3/2025" and v["rows"][0]["usd"] == "0,08"
    assert confirm_view([], used=9, quota=5)["remaining"] == 0
    assert not v["over_budget"] and confirm_view(items, used=0, quota=5, over_budget=True)["over_budget"]


def test_tran_chi_phi_thang_chan_bao_cao_moi_tru_quan_tri():
    from services.api.reports import budget_block
    user, admin = User(1, "a@x", "user", 3), User(3, "c@x", "admin", 3)
    msg = budget_block(user, spend=5.2, budget=5.0)
    assert msg and "trần chi phí tháng" in msg
    assert budget_block(user, spend=5.0, budget=5.0)            # chạm trần cũng chặn
    assert budget_block(user, spend=4.9, budget=5.0) is None
    assert budget_block(admin, spend=9.0, budget=5.0) is None    # quản trị vẫn tạo được


def test_trang_xac_nhan_bao_cham_tran():
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "services" / "api" / "templates" / "report.html").read_text(
        encoding="utf-8")
    assert "confirm.over_budget" in html and "tháng sau" in html
