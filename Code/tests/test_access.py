"""Xin dùng thử từ trang giới thiệu: kiểm email, không lộ email nào đã có tài khoản, chặn gửi lặp và gửi dồn."""
import pytest

from services import access


class FakeConn:
    """Trả lời lần lượt các câu SELECT count(*) theo thứ tự access.save hỏi; ghi lại INSERT."""
    def __init__(self, is_user=0, recent_same=0, last_hour=0):
        self.counts = [is_user, recent_same, last_hour]
        self.inserted = []

    def execute(self, sql, params=()):
        if sql.lstrip().upper().startswith("INSERT"):
            self.inserted.append(params)
            return self
        self._one = (self.counts.pop(0),)
        return self

    def fetchone(self):
        return self._one

    def commit(self):
        pass


def test_clean_request_lowercases_email_and_limits_note():
    assert access.clean_request("  Ban@ViDu.com ", " quan tâm FPT ") == ("ban@vidu.com", "quan tâm FPT")
    for bad in ("", "khong-phai-email", "a@b", "x" * 250 + "@vidu.com"):
        with pytest.raises(ValueError):
            access.clean_request(bad, "")
    with pytest.raises(ValueError):
        access.clean_request("ban@vidu.com", "x" * (access.MAX_NOTE + 1))


def test_new_request_is_saved_and_admin_should_be_told():
    conn = FakeConn()
    assert access.save(conn, "ban@vidu.com", "") is True
    assert conn.inserted == [("ban@vidu.com", "")]


def test_existing_user_or_repeat_is_not_saved_but_not_an_error():
    for conn in (FakeConn(is_user=1), FakeConn(recent_same=1)):
        assert access.save(conn, "ban@vidu.com", "") is False
        assert conn.inserted == []


def test_too_many_requests_in_an_hour_is_refused():
    with pytest.raises(ValueError):
        access.save(FakeConn(last_hour=access.HOURLY_LIMIT), "ban@vidu.com", "")
