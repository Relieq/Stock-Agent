"""Chạy agent báo cáo thật: bảng `reports`, phụ thuộc thật của đồ thị (CSDL, mô hình), lưu trạng thái đồ thị bằng
PostgresSaver (mỗi báo cáo là một luồng), chạy tiếp các báo cáo chờ đọc BCTC (bộ canh gọi mỗi lượt)."""

from __future__ import annotations

import json
import traceback
from datetime import date
from statistics import median

import psycopg
from psycopg.types.json import Jsonb

from services.analyst import catalog, store, tools
from services.analyst.graph import build
from services.analyst.plan import Checked, Plan, check_plan, parse_request
from services.analyst.sheet import FactSheet
from services.analyst.writer import write
from services.db import database_url
from services.notify import notify_admin, send_email
from services.users import User, site_url

REPORTS_PER_DAY = 20
JSON_FIELDS = {"plan", "notes", "missing", "sources", "charts", "sheet", "result", "guard_log", "usage"}
RUNNING = ("planning", "writing")
NEED_TOOLS = ("metric", "reasons")


def _conn() -> psycopg.Connection:
    return psycopg.connect(database_url(), autocommit=True)


def _dumps(o) -> str:
    return json.dumps(o, ensure_ascii=False, default=str)


def create(conn, user: User, question: str) -> int:
    used = conn.execute("SELECT count(*) FROM reports WHERE user_id = %s AND created_at > now() - interval '1 day'"
                        " AND reused_from IS NULL", (user.id,)).fetchone()[0]
    if used >= REPORTS_PER_DAY:
        raise PermissionError(f"Đã dùng hết {REPORTS_PER_DAY} báo cáo trong 24 giờ qua")
    return conn.execute("INSERT INTO reports (user_id, question) VALUES (%s, %s) RETURNING id",
                        (user.id, question.strip()[:1000])).fetchone()[0]


def save(conn, report_id: int, **fields) -> None:
    if not fields:
        return
    cols, vals = [], []
    for k, v in fields.items():
        cols.append(f"{k} = %s")
        vals.append(Jsonb(v, dumps=_dumps) if k in JSON_FIELDS else v)
    if fields.get("status") in ("done", "failed"):
        cols.append("finished_at = now()")
    conn.execute(f"UPDATE reports SET {', '.join(cols)} WHERE id = %s", (*vals, report_id))


def get(conn, report_id: int) -> dict | None:
    cur = conn.execute("SELECT r.*, u.email FROM reports r JOIN users u ON u.id = r.user_id WHERE r.id = %s",
                       (report_id,))
    row = cur.fetchone()
    return dict(zip([c.name for c in cur.description], row)) if row else None


def mine(conn, user_id: int, limit: int = 30) -> list[dict]:
    cur = conn.execute("SELECT id, question, status, created_at FROM reports WHERE user_id = %s"
                       " ORDER BY created_at DESC LIMIT %s", (user_id, limit))
    return [dict(zip([c.name for c in cur.description], r)) for r in cur.fetchall()]


def estimate_read_usd() -> float:
    """Chi phí ước tính đọc một BCTC: trung vị các BCTC đã đọc (services/costs.py), chưa có thì 0,1 USD."""
    from services.costs import report as cost_report
    values = [d.tally.usd for d in cost_report().docs if d.tally.usd > 0]
    return round(median(values), 3) if values else 0.1


class RealDeps:
    def __init__(self, conn, report_id: int, client=None):
        self.conn, self.report_id = conn, report_id
        row = conn.execute("SELECT u.id, u.email, u.role, u.daily_quota FROM reports r JOIN users u ON u.id = r.user_id"
                           " WHERE r.id = %s", (report_id,)).fetchone()
        self.user = User(*row)
        if client is None:
            from services.llm import VisionClient
            client = VisionClient()
        self.client = client
        self._served: set[tuple[str, str, str]] = set()     # các yêu cầu xin thêm đã đáp trong lần chạy này

    def understand(self, question: str) -> Checked:
        companies = self.conn.execute("SELECT ticker, name FROM companies WHERE tracked ORDER BY ticker").fetchall()
        plan = parse_request(self.client, question, date.today(), companies)
        known = {t for (t,) in self.conn.execute("SELECT ticker FROM companies")}

        def exists(t: str) -> bool:
            from services.ondemand import company_from_vietstock
            try:
                return company_from_vietstock(t) is not None
            except Exception:
                return False

        return check_plan(plan, known, exists, lambda ts: store.latest(self.conn, ts))

    def missing(self, plan: Plan) -> list[dict]:
        est = estimate_read_usd()
        out = [m | {"usd": est} for m in store.missing(self.conn, plan)]
        ids = (get(self.conn, self.report_id) or {}).get("request_ids") or []
        if ids and out:
            # yêu cầu đọc của báo cáo này đã thất bại hoặc bị từ chối thì không hẹn đọc lại, ghi lý do vào báo cáo
            bad = {(t, y, p): n for t, y, p, n in self.conn.execute(
                """SELECT ticker, fiscal_year, fiscal_period, note FROM processing_requests
                   WHERE id = ANY(%s) AND status IN ('failed', 'rejected')""", (ids,)).fetchall()}
            for m in out:
                key = (m["ticker"], m["year"], m["period"])
                if key in bad:
                    m["can_read"], m["note"] = False, bad[key] or "yêu cầu đọc không thành công"
        return out

    def request_reading(self, report_id: int, items: list[dict]) -> list[int]:
        row = get(self.conn, report_id) or {}
        if row.get("request_ids"):      # nút này có thể chạy lại sau sự cố: không tạo yêu cầu thứ hai
            return list(row["request_ids"])
        from services.ondemand import request_ticker
        ids = []
        for m in items:
            try:
                rid, _ = request_ticker(self.conn, self.user, m["ticker"], m["year"], m["period"])
                ids.append(rid)
            except (ValueError, PermissionError) as e:
                notes = (get(self.conn, report_id) or {}).get("notes") or []
                save(self.conn, report_id, notes=notes + [f"Không gửi được yêu cầu đọc {m['ticker']}: {e}"])
        save(self.conn, report_id, request_ids=ids)
        return ids

    def build_sheet(self, plan: Plan):
        return store.sheet_for_plan(self.conn, plan)

    def reuse(self, report_id: int, plan: Plan, sources: list[dict]) -> bool:
        key = json.dumps({k: v for k, v in plan.to_json().items() if k != "unclear"}, sort_keys=True)
        skey = json.dumps(sources, sort_keys=True)
        save(self.conn, report_id, plan_key=key, sources_key=skey)
        row = self.conn.execute(
            """SELECT id, result, guard_log, sheet, notes, charts, sources FROM reports
               WHERE user_id = %s AND status = 'done' AND plan_key = %s AND sources_key = %s AND id <> %s
               ORDER BY id DESC LIMIT 1""", (self.user.id, key, skey, report_id)).fetchone()
        if row is None:
            return False
        rid, result, guard_log, sheet, notes, charts, srcs = row
        save(self.conn, report_id, status="done", result=result, guard_log=guard_log, sheet=sheet, notes=notes,
             charts=charts, sources=srcs, reused_from=rid)
        return True

    def extra(self, plan: Plan, sheet: FactSheet, need: dict) -> None:
        """Đáp yêu cầu xin thêm số của mô hình. Bỏ qua yêu cầu lạ (công cụ ngoài danh sách, mã không thuộc kế hoạch,
        chỉ tiêu ngoài danh mục) hoặc đã đáp rồi."""
        if not isinstance(need, dict):
            return
        tool = need.get("tool")
        ticker = str(need.get("ticker") or "").strip().upper()
        metric = str(need.get("metric") or "")
        if tool not in NEED_TOOLS or ticker not in plan.tickers:
            return
        if tool == "metric" and metric not in catalog.ALL_KEYS:
            return
        key = (tool, ticker, metric if tool == "metric" else "")
        if key in self._served:
            return
        self._served.add(key)
        if tool == "reasons":
            tools.reasons(self.conn, self.client, plan, sheet, ticker)
        else:
            tools.more_metric(self.conn, plan, sheet, ticker, metric)

    def write(self, question, plan, sheet, feedback, allow_need) -> dict:
        return write(self.client, question, plan, sheet, feedback, allow_need)

    def known_tickers(self) -> set[str]:
        return {t for (t,) in self.conn.execute("SELECT ticker FROM companies")}

    def save(self, report_id: int, **fields) -> None:
        save(self.conn, report_id, **fields)

    def flush_usage(self) -> None:
        """Cộng chi phí lần chạy này vào reports.usage (một báo cáo có thể chạy nhiều lần: trước và sau khi chờ)."""
        snap = self.client.steps_snapshot() if hasattr(self.client, "steps_snapshot") else {}
        if not snap:
            return
        old = (get(self.conn, self.report_id) or {}).get("usage") or {}
        for step, u in snap.items():
            o = old.setdefault(step, {"calls": 0, "seconds": 0.0, "input_tokens": 0, "output_tokens": 0, "usd": 0.0})
            for k in o:
                o[k] += u.get(k, 0)
        save(self.conn, self.report_id, usage=old)


def _checkpointer():
    from langgraph.checkpoint.postgres import PostgresSaver
    return PostgresSaver.from_conn_string(database_url())


def setup_checkpoints() -> None:
    with _checkpointer() as saver:
        saver.setup()


def is_waiting(state) -> bool:
    """Luồng đang dừng đúng ở chỗ chờ đọc BCTC (không phải chờ xác nhận hay đã xong)."""
    for task in getattr(state, "tasks", ()) or ():
        for it in getattr(task, "interrupts", ()) or ():
            value = getattr(it, "value", None)
            if isinstance(value, dict) and "waiting" in value:
                return True
    return False


def run(report_id: int, resume=None, client=None) -> str:
    """Chạy (resume=None) hoặc chạy tiếp (resume=True/False: trả lời xác nhận, hoặc True khi BCTC đã đọc xong) một
    báo cáo. Trả về trạng thái sau khi chạy."""
    from langgraph.types import Command
    with _conn() as conn, _checkpointer() as saver:
        deps = RealDeps(conn, report_id, client)
        app = build(deps, saver)
        cfg = {"configurable": {"thread_id": str(report_id)}, "recursion_limit": 60}
        before = get(conn, report_id)
        try:
            if resume is None:
                app.invoke({"report_id": report_id, "question": before["question"]}, cfg)
            else:
                app.invoke(Command(resume=resume), cfg)
        except Exception as e:
            err = traceback.format_exc()
            save(conn, report_id, status="failed", error=str(e)[:2000])
            notify_admin(f"[Soi] Báo cáo {report_id} lỗi", err)
        finally:
            deps.flush_usage()
        after = get(conn, report_id)
        if after["status"] == "done" and before.get("request_ids"):
            send_email(after["email"], "[Soi] Báo cáo của bạn đã xong",
                       f"Báo cáo cho câu hỏi \"{after['question']}\" đã xong sau khi hệ thống đọc thêm BCTC:\n"
                       f"{site_url()}/bao-cao/{report_id}")
        return after["status"]


def resume_waiting(conn) -> list[str]:
    """Bộ canh gọi mỗi lượt: báo cáo đang chờ mà mọi yêu cầu đọc đã xong (đọc được hay không) thì chạy tiếp. Chỉ chạy
    tiếp luồng thật sự dừng ở chỗ chờ (đọc trạng thái đồ thị), tránh đánh thức nhầm luồng đã chạy tiếp hoặc hỏng."""
    rows = conn.execute(
        """SELECT r.id FROM reports r WHERE r.status = 'waiting_data' AND NOT EXISTS (
             SELECT 1 FROM processing_requests p WHERE p.id = ANY(r.request_ids) AND p.status IN ('queued', 'processing'))
           ORDER BY r.id""").fetchall()
    if not rows:
        return []
    ready = []
    with _checkpointer() as saver:
        app = build(None, saver)         # chỉ để đọc trạng thái, không chạy nút nào
        for (rid,) in rows:
            if is_waiting(app.get_state({"configurable": {"thread_id": str(rid)}})):
                ready.append(rid)
    return [f"báo cáo {rid}: chạy tiếp sau khi đọc BCTC -> {run(rid, resume=True)}" for rid in ready]
