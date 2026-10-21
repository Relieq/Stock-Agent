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
