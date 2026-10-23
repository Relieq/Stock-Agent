from pathlib import Path

import pytest

from services.feedback import DAILY_LIMIT, MAX_LEN, clean_message, email_body, safe_page, save


def test_chi_nhan_duong_dan_trong_trang():
    assert safe_page("/the/FPT") == "/the/FPT"
    for bad in ("https://evil.example", "//evil.example/x", "/\\evil", "", None, "the/FPT"):
        assert safe_page(bad) == "/"


def test_noi_dung_rong_hoac_qua_dai_bi_tu_choi():
    assert clean_message("  số sai  ") == "số sai"
    with pytest.raises(ValueError):
        clean_message("   ")
    with pytest.raises(ValueError):
        clean_message("x" * (MAX_LEN + 1))


class FakeConn:
    def __init__(self, sent_today):
        self.sent_today, self.inserted, self.committed = sent_today, [], False

    def execute(self, sql, params):
        conn = self

        class R:
            def fetchone(self):
                if sql.startswith("SELECT count"):
                    return (conn.sent_today,)
                conn.inserted.append(params)
                return (7,)
        return R()

    def commit(self):
        self.committed = True


def test_luu_kem_trang_va_chan_gui_lap():
    conn = FakeConn(0)
    assert save(conn, 5, "//evil", " ô này sai ") == 7
    assert conn.inserted == [(5, "/", "ô này sai")] and conn.committed
    with pytest.raises(ValueError):
        save(FakeConn(DAILY_LIMIT), 5, "/", "lần nữa")


def test_email_co_nguoi_gui_va_trang():
    body = email_body("a@x", "/the/FPT", "số sai")
    assert "a@x" in body and "/the/FPT" in body and "số sai" in body


def test_o_gop_y_chi_hien_khi_da_dang_nhap():
    html = (Path(__file__).resolve().parents[1] / "services" / "api" / "templates" / "base.html").read_text(
        encoding="utf-8")
    form = html.index('action="/gop-y"')
    assert html.index("{% if me %}{% set qp") < form < html.index("</section>{% endif %}")
