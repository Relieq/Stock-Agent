from datetime import date

from services.watcher import __main__ as watcher


def test_since_defaults_to_start_of_current_quarter():
    # Mùa BCTC quý trước rơi vào quý hiện tại; khởi động lại giữa mùa không được bỏ qua BCTC đã phát hiện
    assert watcher._quarter_start(date(2026, 10, 18)) == date(2026, 10, 1)
    assert watcher._quarter_start(date(2027, 1, 25)) == date(2027, 1, 1)
    assert watcher._quarter_start(date(2026, 8, 31)) == date(2026, 7, 1)


class _Conn:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params):
        return self

    def fetchall(self):
        return self.rows


def test_failed_document_is_retried_once(monkeypatch):
    monkeypatch.setattr(watcher, "_retried", set())
    rows = [(1, "FPT", "t", None, None, "downloaded"), (2, "VCB", "t", None, None, "failed")]
    assert [r[0] for r in watcher._pending_extraction(_Conn(rows), date(2026, 10, 1), 2026)] == [1, 2]
    # Lượt sau: BCTC 2 vẫn lỗi thì không thử nữa
    assert [r[0] for r in watcher._pending_extraction(_Conn(rows[1:]), date(2026, 10, 1), 2026)] == []


def test_downtime_notice_only_after_more_than_two_passes():
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 10, 19, 16, 0, tzinfo=timezone.utc)
    assert watcher.downtime_notice(None, now, 15) is None                         # lần chạy đầu tiên
    assert watcher.downtime_notice(now - timedelta(minutes=20), now, 15) is None   # khởi động lại sau khi sửa code
    text = watcher.downtime_notice(now - timedelta(hours=17, minutes=17), now, 15)
    assert "17 giờ 17 phút" in text and "23:00 19/10" in text


def test_stuck_download_is_reported_once():
    from datetime import datetime, timedelta, timezone
    from services.watcher.__main__ import stuck_notice
    now = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
    rows = [(22191, "TCX", "BCTC quý 3 năm 2026", now - timedelta(hours=7), "https://static2.vietstock.vn/x.zip")]
    body, ids = stuck_notice(rows, set(), now)
    assert ids == [22191] and "TCX" in body and "7 giờ" in body
    assert stuck_notice(rows, {22191}, now) == (None, [])
