from datetime import datetime, timedelta, timezone

import services.users as users
from services.health import watcher_status

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def test_suc_khoe_bao_loi_khi_bo_canh_im_qua_lau():
    assert watcher_status(NOW - timedelta(minutes=20), NOW) == {"ok": True, "watcher_minutes_since_beat": 20}
    assert not watcher_status(NOW - timedelta(minutes=121), NOW)["ok"]
    assert not watcher_status(None, NOW)["ok"]


class FakeConn:
    def __init__(self, recent):
        self.recent, self.inserted = recent, 0

    def execute(self, sql, params):
        conn = self

        class R:
            def fetchone(self):
                if "count(*)" in sql:
                    return (conn.recent,)
                return (1, "a@x", "user", 3)
        if sql.startswith("INSERT INTO login_tokens"):
            conn.inserted += 1
        return R()


def test_qua_5_link_mot_gio_thi_khong_gui_nua(monkeypatch):
    sent = []
    monkeypatch.setattr(users, "send_email", lambda to, subj, body: sent.append(to) or True)
    conn = FakeConn(users.MAX_LINKS_PER_HOUR - 1)
    assert users.start_login(conn, "a@x")[0] and conn.inserted == 1
    conn = FakeConn(users.MAX_LINKS_PER_HOUR)
    assert users.start_login(conn, "a@x") == (False, None) and conn.inserted == 0
    assert sent == ["a@x"]


def test_khong_chuyen_huong_ra_ngoai_sau_dang_nhap():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "services" / "api" / "accounts.py").read_text(encoding="utf-8")
    assert 'startswith("/") else' not in src      # kiểu kiểm cũ cho lọt "//trang-ngoai"


def test_muc_sua_so_ghi_chenh_va_phan_tram():
    from decimal import Decimal as D
    from services.metrics.card import revision_gap, ty_signed
    assert revision_gap(D("15987971e6"), D("17278633e6")) == "số mới thấp hơn 1.291 tỷ, −7,5%"
    assert revision_gap(D("5e9"), D("-2e9")) == "số mới cao hơn 7,0 tỷ"
    assert ty_signed(D("-940909e6")) == "âm 941 tỷ"
