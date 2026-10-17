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
