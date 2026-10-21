"""Agent tạo báo cáo theo yêu cầu: đồ thị trạng thái LangGraph (Baocao/dinh-huong/agent-bao-cao.md mục 3).

hiểu yêu cầu -> kiểm kho -> [thiếu BCTC đọc được: chờ xác nhận -> đưa vào hàng chờ đọc -> chờ bộ canh] -> tính bảng số
-> viết lời (xin thêm tối đa 3 lần) -> kiểm số (viết lại tối đa 2 lần, rồi bỏ câu sai) -> xong.

Mọi việc đụng CSDL hay mô hình đi qua `Deps`, để test chạy đồ thị với bản giả. Trạng thái lưu sau mỗi bước bằng
checkpointer (Postgres khi chạy thật), nên báo cáo dừng chờ được rồi chạy tiếp đúng chỗ.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from services.analyst.guard import check_draft
from services.analyst.plan import Checked, Plan, label
from services.analyst.sheet import FactSheet
from services.analyst.writer import drop_sentences, feedback_lines

MAX_NEED_ROUNDS = 3
MAX_REWRITES = 2
EMPTY_ERROR = "Kho chưa có số của các mã/kỳ này"
NO_SENTENCE_ERROR = "Không còn câu nào qua bộ kiểm tra số"


class State(TypedDict, total=False):
    report_id: int
    question: str
    plan: dict
    notes: list[str]
    ask: str
    missing: list[dict]
    confirmed: bool
    request_ids: list[int]
    sheet: list[dict]
    draft: dict
    need_rounds: int
    rewrites: int
    feedback: list[str]
    log: list[dict]
    route: str


class Deps(Protocol):
    def understand(self, question: str) -> Checked: ...
    def missing(self, plan: Plan) -> list[dict]: ...
    def request_reading(self, report_id: int, items: list[dict]) -> list[int]: ...
    def build_sheet(self, plan: Plan) -> tuple[FactSheet, list[dict], list[str], list[dict]]: ...
    def reuse(self, report_id: int, plan: Plan, sources: list[dict]) -> bool: ...
    def extra(self, plan: Plan, sheet: FactSheet, need: dict) -> None: ...
    def write(self, question: str, plan: Plan, sheet: FactSheet, feedback: list[str], allow_need: bool) -> dict: ...
    def known_tickers(self) -> set[str]: ...
    def save(self, report_id: int, **fields) -> None: ...


def _links_json(links) -> dict:
    return {k: [asdict(l) for l in v] for k, v in links.items()}


def build(deps: Deps, checkpointer=None):
    def understand(s: State) -> dict:
        deps.save(s["report_id"], status="planning")
        checked = deps.understand(s["question"])
        if checked.ask:
            deps.save(s["report_id"], status="needs_clarification", question_back=checked.ask)
            return {"ask": checked.ask, "route": "end"}
        deps.save(s["report_id"], plan=checked.plan.to_json(), notes=checked.notes)
        return {"plan": checked.plan.to_json(), "notes": checked.notes, "route": "inventory"}

    def inventory(s: State) -> dict:
        missing = deps.missing(Plan.from_json(s["plan"]))
        readable = [m for m in missing if m.get("can_read")]
        return {"missing": missing, "route": "confirm" if readable and "confirmed" not in s else "compute"}

    def confirm(s: State) -> dict:
        readable = [m for m in s["missing"] if m.get("can_read")]
        deps.save(s["report_id"], status="awaiting_confirmation", missing=readable)
        if interrupt({"missing": readable}) is not True:     # chỉ đồng ý khi xác nhận rõ ràng
            return {"confirmed": False, "route": "compute"}
        ids = deps.request_reading(s["report_id"], readable)
        deps.save(s["report_id"], status="waiting_data", request_ids=ids)
        return {"confirmed": True, "request_ids": ids, "route": "wait"}

    def wait(s: State) -> dict:
        interrupt({"waiting": s["request_ids"]})       # bộ canh chạy tiếp khi các yêu cầu đọc đã xong
        return {"route": "inventory"}

    def compute(s: State) -> dict:
        plan = Plan.from_json(s["plan"])
        deps.save(s["report_id"], status="writing")
        sheet, sources, notes, charts = deps.build_sheet(plan)
        basis = plan.basis
        notes = s.get("notes", []) + notes + [
            f"Không đọc được thêm BCTC {m['ticker']} {label(m['year'], m['period'], basis)}"
            + (f": {m['note']}" if m.get("note") else "") for m in s.get("missing", []) if not m.get("can_read")]
        if not sheet.facts:         # không có số nào: không gọi mô hình viết
            deps.save(s["report_id"], status="failed", error=EMPTY_ERROR, notes=notes, sources=sources, charts=charts)
            return {"notes": notes, "route": "end"}
        if deps.reuse(s["report_id"], plan, sources):
            return {"route": "end"}
        deps.save(s["report_id"], notes=notes, sources=sources, charts=charts)
        return {"sheet": sheet.to_json(), "notes": notes, "need_rounds": 0, "rewrites": 0, "feedback": [], "log": [],
                "route": "write"}

    def write(s: State) -> dict:
        plan, sheet = Plan.from_json(s["plan"]), FactSheet.from_json(s["sheet"])
        allow = s["need_rounds"] < MAX_NEED_ROUNDS
        draft = deps.write(s["question"], plan, sheet, s["feedback"], allow)
        needs = (draft.get("need") or []) if allow else []
        if needs:
            for need in needs:
                deps.extra(plan, sheet, need)
            return {"sheet": sheet.to_json(), "need_rounds": s["need_rounds"] + 1, "route": "write"}
        return {"draft": draft, "route": "check"}

    def check(s: State) -> dict:
        plan, sheet = Plan.from_json(s["plan"]), FactSheet.from_json(s["sheet"])
        allowed, known = set(plan.tickers), deps.known_tickers()
        violations, _, warnings = check_draft(s["draft"], sheet, allowed, known)
        n = sum(len(sec["sentences"]) for sec in s["draft"].get("sections", []))
        log = s["log"] + [{"attempt": s["rewrites"], "sentences": n, "violations": [asdict(v) for v in violations],
                           "warnings": warnings}]
        if violations and s["rewrites"] < MAX_REWRITES:
            return {"log": log, "rewrites": s["rewrites"] + 1, "feedback": feedback_lines(s["draft"], violations),
                    "route": "write"}
        final, dropped = drop_sentences(s["draft"], {(v.section, v.sentence) for v in violations})
        _, links, _ = check_draft(final, sheet, allowed, known)
        guard_log = {"attempts": log, "dropped": dropped}
        if not any(sec["sentences"] for sec in final.get("sections", [])):
            deps.save(s["report_id"], status="failed", error=NO_SENTENCE_ERROR, sheet=s["sheet"],
                      guard_log=guard_log)
            return {"log": log, "draft": final, "route": "end"}
        deps.save(s["report_id"], status="done", sheet=s["sheet"], result={"draft": final, "links": _links_json(links)},
                  guard_log=guard_log)
        return {"log": log, "draft": final, "route": "end"}

    g = StateGraph(State)
    for name, fn in (("understand", understand), ("inventory", inventory), ("confirm", confirm), ("wait", wait),
                     ("compute", compute), ("write", write), ("check", check)):
        g.add_node(name, fn)
    g.add_edge(START, "understand")
    route = lambda s: END if s["route"] == "end" else s["route"]   # noqa: E731
    g.add_conditional_edges("understand", route, ["inventory", END])
    g.add_conditional_edges("inventory", route, ["confirm", "compute"])
    g.add_conditional_edges("confirm", route, ["wait", "compute"])
    g.add_edge("wait", "inventory")
    g.add_conditional_edges("compute", route, ["write", END])
    g.add_conditional_edges("write", route, ["write", "check"])
    g.add_conditional_edges("check", route, ["write", END])
    return g.compile(checkpointer=checkpointer)
