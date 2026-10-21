from types import SimpleNamespace

from services.analyst import report
from services.analyst.plan import Plan
from services.analyst.sheet import FactSheet


def _deps(calls):
    d = object.__new__(report.RealDeps)
    d.conn, d.client, d._served = None, None, set()
    return d


def test_extra_loc_yeu_cau_la_va_trung(monkeypatch):
    calls = []
    monkeypatch.setattr(report.tools, "more_metric", lambda conn, plan, sheet, t, k: calls.append(("metric", t, k)))
    monkeypatch.setattr(report.tools, "reasons", lambda conn, client, plan, sheet, t: calls.append(("reasons", t)))
    d = _deps(calls)
    plan, sheet = Plan("compare", ["TCB", "LPB"], 2026, "Q3", "quarter"), FactSheet()
    for need in (
        {"tool": "metric", "ticker": "tcb", "metric": "npat_parent"},      # hợp lệ (chữ thường được chuẩn hóa)
        {"tool": "metric", "ticker": "TCB", "metric": "npat_parent"},      # trùng
        {"tool": "metric", "ticker": "FPT", "metric": "npat_parent"},      # mã ngoài kế hoạch
        {"tool": "metric", "ticker": "TCB", "metric": "khong_co"},         # chỉ tiêu ngoài danh mục
        {"tool": "sql", "ticker": "TCB", "metric": "x"},                   # công cụ lạ
        {"tool": "reasons", "ticker": "LPB", "metric": "none"},            # hợp lệ
        {"tool": "reasons", "ticker": "LPB", "metric": "khac"},            # trùng (reasons không phân theo chỉ tiêu)
        "không phải dict",
    ):
        d.extra(plan, sheet, need)
    assert calls == [("metric", "TCB", "npat_parent"), ("reasons", "LPB")]


def test_is_waiting_chi_nhan_dung_cho_cho():
    def state(*values):
        return SimpleNamespace(tasks=[SimpleNamespace(interrupts=[SimpleNamespace(value=v) for v in values])])

    assert report.is_waiting(state({"waiting": [1, 2]}))
    assert not report.is_waiting(state({"missing": []}))      # đang chờ xác nhận, chưa phải chờ đọc
    assert not report.is_waiting(SimpleNamespace(tasks=[]))
    assert not report.is_waiting(state("waiting"))


class _Cur:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Conn:
    def execute(self, sql, params=None):
        return _Cur([("LPB", 2026, "Q3", "không có file trên Vietstock")])


def test_missing_ghi_ly_do_khi_yeu_cau_that_bai(monkeypatch):
    monkeypatch.setattr(report, "estimate_read_usd", lambda: 0.1)
    monkeypatch.setattr(report.store, "missing", lambda conn, plan: [
        {"ticker": "LPB", "year": 2026, "period": "Q3", "can_read": True, "note": ""},
        {"ticker": "TCB", "year": 2026, "period": "Q3", "can_read": True, "note": ""}])
    monkeypatch.setattr(report, "get", lambda conn, rid: {"request_ids": [7]})
    d = object.__new__(report.RealDeps)
    d.conn, d.report_id = _Conn(), 5
    out = d.missing(Plan("compare", ["TCB", "LPB"], 2026, "Q3", "quarter"))
    lpb, tcb = out
    assert not lpb["can_read"] and lpb["note"] == "không có file trên Vietstock"
    assert tcb["can_read"]


def test_request_reading_khong_tao_lai(monkeypatch):
    monkeypatch.setattr(report, "get", lambda conn, rid: {"request_ids": [11, 12]})
    d = object.__new__(report.RealDeps)
    d.conn = None
    assert d.request_reading(5, [{"ticker": "TCB", "year": 2026, "period": "Q3"}]) == [11, 12]


def test_request_reading_giu_ly_do_khong_gui_duoc(monkeypatch):
    import services.ondemand as ondemand
    saved = []

    def fake_request(conn, user, ticker, year, period):
        if ticker == "LPB":
            raise PermissionError("Đã dùng hết 5 yêu cầu mới trong 24 giờ qua")
        return 21, "queued"

    monkeypatch.setattr(ondemand, "request_ticker", fake_request)
    items = [{"ticker": "TCB", "year": 2026, "period": "Q3", "can_read": True},
             {"ticker": "LPB", "year": 2026, "period": "Q3", "can_read": True}]
    monkeypatch.setattr(report, "get", lambda conn, rid: {"request_ids": None, "missing": [dict(m) for m in items]})
    monkeypatch.setattr(report, "save", lambda conn, rid, **f: saved.append(f))
    d = object.__new__(report.RealDeps)
    d.conn, d.user = None, None
    assert d.request_reading(5, items) == [21]
    assert saved[0]["missing"][1]["error"].startswith("không gửi được yêu cầu đọc: Đã dùng hết")
    assert "error" not in saved[0]["missing"][0]
    assert saved[1] == {"request_ids": [21]}


def test_missing_doc_ly_do_khong_gui_duoc(monkeypatch):
    monkeypatch.setattr(report, "estimate_read_usd", lambda: 0.1)
    monkeypatch.setattr(report.store, "missing", lambda conn, plan: [
        {"ticker": "LPB", "year": 2026, "period": "Q3", "can_read": True, "note": ""}])
    monkeypatch.setattr(report, "get", lambda conn, rid: {"request_ids": [], "missing": [
        {"ticker": "LPB", "year": 2026, "period": "Q3", "error": "không gửi được yêu cầu đọc: hết hạn mức"}]})
    d = object.__new__(report.RealDeps)
    d.conn, d.report_id = None, 5
    (m,) = d.missing(Plan("yoy", ["LPB"], 2026, "Q3", "quarter"))
    assert not m["can_read"] and "hết hạn mức" in m["note"]


def test_missing_khong_tinh_chi_phi_khi_khong_thieu(monkeypatch):
    def boom():
        raise AssertionError("không được gọi")

    monkeypatch.setattr(report, "estimate_read_usd", boom)
    monkeypatch.setattr(report.store, "missing", lambda conn, plan: [])
    d = object.__new__(report.RealDeps)
    d.conn, d.report_id = None, 5
    assert d.missing(Plan("yoy", ["LPB"], 2026, "Q3", "quarter")) == []


def test_reuse_khoa_khong_phu_thuoc_thu_tu_ma(monkeypatch):
    keys = []
    monkeypatch.setattr(report, "save", lambda conn, rid, **f: keys.append(f.get("plan_key")) if "plan_key" in f else None)

    class Conn:
        def execute(self, sql, params):
            return SimpleNamespace(fetchone=lambda: None)

    for tickers in (["TCB", "LPB"], ["LPB", "TCB"]):
        d = object.__new__(report.RealDeps)
        d.conn, d.user = Conn(), SimpleNamespace(id=1)
        d.reuse(5, Plan("compare", tickers, 2026, "Q3", "quarter"), [])
    assert keys[0] == keys[1]


class _Lock:
    def __init__(self, got):
        self.got, self.sql = got, []

    def execute(self, sql, params=None):
        self.sql.append(sql)
        return SimpleNamespace(fetchone=lambda: (self.got,))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_run_env(monkeypatch, status, pending, lock=True, invoked=None, mails=None):
    conn = _Lock(lock)
    monkeypatch.setattr(report, "_conn", lambda: conn)
    monkeypatch.setattr(report, "_checkpointer", lambda: conn)
    monkeypatch.setattr(report, "RealDeps", lambda c, rid, cl: SimpleNamespace(flush_usage=lambda: None))
    state = SimpleNamespace(tasks=[SimpleNamespace(interrupts=[SimpleNamespace(value=pending)])] if pending else [])
    monkeypatch.setattr(report, "build", lambda deps, saver: SimpleNamespace(
        get_state=lambda cfg: state, invoke=lambda *a, **k: invoked.append(a)))
    row = {"status": status, "question": "q", "email": "a@b", "request_ids": [1]}
    monkeypatch.setattr(report, "get", lambda c, rid: dict(row))
    monkeypatch.setattr(report, "send_email", lambda *a: mails.append(a))
    return conn


def test_run_khong_chay_khi_co_luot_khac_giu_khoa(monkeypatch):
    invoked, mails = [], []
    _fake_run_env(monkeypatch, "writing", None, lock=False, invoked=invoked, mails=mails)
    assert report.run(5, resume=True, expect="waiting") == "writing"
    assert invoked == [] and mails == []


def test_run_chi_chay_tiep_dung_diem_dung(monkeypatch):
    invoked, mails = [], []
    _fake_run_env(monkeypatch, "waiting_data", {"waiting": [1]}, invoked=invoked, mails=mails)
    assert report.run(5, resume=True, expect="missing") == "waiting_data"      # nút Đọc thêm bấm lặp: bỏ qua
    assert invoked == []
    _fake_run_env(monkeypatch, "done", None, invoked=invoked, mails=mails)
    assert report.run(5, resume=True, expect="waiting") == "done"               # báo cáo đã xong: không gửi lại thư
    assert invoked == [] and mails == []


def test_run_thu_xong_chi_khi_chay_tiep_cho_doc(monkeypatch):
    invoked, mails = [], []
    _fake_run_env(monkeypatch, "done", {"waiting": [1]}, invoked=invoked, mails=mails)
    assert report.run(5, resume=True, expect="waiting") == "done"
    assert len(invoked) == 1 and len(mails) == 1 and "đã xong" in mails[0][1]
    invoked.clear(), mails.clear()
    _fake_run_env(monkeypatch, "done", {"missing": []}, invoked=invoked, mails=mails)      # chạy tiếp từ xác nhận
    assert report.run(5, resume=True, expect="missing") == "done"
    assert len(invoked) == 1 and mails == []


def test_run_loi_van_nha_khoa_va_thu_loi_khong_lam_hong(monkeypatch):
    invoked, mails = [], []
    conn = _fake_run_env(monkeypatch, "failed", {"waiting": [1]}, invoked=invoked, mails=mails)

    def boom(*a, **k):
        raise RuntimeError("mô hình lỗi")

    monkeypatch.setattr(report, "build", lambda deps, saver: SimpleNamespace(
        get_state=lambda cfg: SimpleNamespace(tasks=[SimpleNamespace(interrupts=[SimpleNamespace(value={"waiting": 1})])]),
        invoke=boom))
    monkeypatch.setattr(report, "save", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("không ghi được")))
    monkeypatch.setattr(report, "notify_admin", lambda *a: (_ for _ in ()).throw(RuntimeError("SMTP hỏng")))
    assert report.run(5, resume=True, expect="waiting") == "failed"
    assert "đã được báo" in mails[0][2] or "gặp lỗi" in mails[0][1]
    assert any("pg_advisory_unlock" in s for s in conn.sql)


def test_fail_stale_danh_dau_loi_bao_cao_ket(monkeypatch):
    saved, admin = [], []

    class Conn:
        def __init__(self):
            self.locks = []

        def execute(self, sql, params=None):
            if "FROM reports WHERE created_at" in sql:
                return SimpleNamespace(fetchall=lambda: [(7,), (8,)])
            if "pg_try_advisory_lock" in sql:
                got = params[1] == 7                # báo cáo 8 còn lượt chạy sống giữ khóa
                return SimpleNamespace(fetchone=lambda: (got,))
            if "SELECT status" in sql:
                return SimpleNamespace(fetchone=lambda: ("writing", None))
            self.locks.append(sql)
            return SimpleNamespace()

    c = Conn()
    monkeypatch.setattr(report, "save", lambda conn, rid, **f: saved.append((rid, f)))
    monkeypatch.setattr(report, "notify_admin", lambda *a: admin.append(a))
    assert report.fail_stale(c) == ["báo cáo 7: bị gián đoạn -> failed"]
    assert saved == [(7, {"status": "failed", "error": report.STALE_ERROR})]
    assert len(admin) == 1 and len(c.locks) == 1


def test_fail_stale_bao_loi_bao_cao_cho_doc_chua_gui_yeu_cau(monkeypatch):
    """Web chết giữa lúc bấm "Đọc thêm" và lúc gửi yêu cầu: chưa có danh sách yêu cầu (NULL) -> lỗi; có yêu cầu hoặc danh sách rỗng thì giữ."""
    saved, admin = [], []
    state = {7: ("waiting_data", None), 8: ("waiting_data", [41]), 9: ("waiting_data", [])}

    class Conn:
        def execute(self, sql, params=None):
            if "FROM reports WHERE created_at" in sql:
                assert "request_ids IS NULL" in sql and "cardinality" not in sql
                return SimpleNamespace(fetchall=lambda: [(7,), (8,), (9,)])
            if "pg_try_advisory_lock" in sql:
                return SimpleNamespace(fetchone=lambda: (True,))
            if "SELECT status" in sql:
                return SimpleNamespace(fetchone=lambda: state[params[0]])
            return SimpleNamespace()

    monkeypatch.setattr(report, "save", lambda conn, rid, **f: saved.append((rid, f)))
    monkeypatch.setattr(report, "notify_admin", lambda *a: admin.append(a))
    # danh sách rỗng (9) là hợp lệ: mọi yêu cầu bị từ chối, bộ canh chạy tiếp để viết với số đã có
    assert report.fail_stale(Conn()) == ["báo cáo 7: bị gián đoạn -> failed"]
    assert saved == [(7, {"status": "failed", "error": report.NOT_SENT_ERROR})]
    assert len(admin) == 1
