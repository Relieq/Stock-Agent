from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from services.analyst.graph import build
from services.analyst.plan import Checked, Plan
from services.analyst.sheet import FactSheet

GOOD = {"sections": [{"heading": "Lợi nhuận", "sentences": [{"text": "LNST của TCB đạt 7.943 tỷ.", "uses": ["S1"]}]}],
        "need": []}
BAD = {"sections": [{"heading": "Lợi nhuận", "sentences": [{"text": "LNST của TCB đạt 7.943 tỷ.", "uses": ["S1"]},
                                                           {"text": "LNST của TCB đạt 9.999 tỷ.", "uses": ["S1"]}]}],
       "need": []}


class FakeDeps:
    def __init__(self, ask=None, missing=(), drafts=(GOOD,), reuse=False):
        self.ask, self._missing, self.drafts, self._reuse = ask, list(missing), list(drafts), reuse
        self.saved, self.requested, self.writes, self.extras = [], [], [], []

    def understand(self, question):
        if self.ask:
            return Checked(None, self.ask)
        return Checked(Plan("yoy", ["TCB"], 2026, "Q3", "quarter"), None, ["ghi chú"])

    def missing(self, plan):
        return self._missing

    def request_reading(self, report_id, items):
        self.requested.append(items)
        self._missing = []
        return [101]

    def build_sheet(self, plan):
        s = FactSheet()
        s.add("metric", "LNST, TCB, quý 3/2026: 7.943 tỷ", ticker="TCB", metric="npat_parent", direction="up",
              names=["lnst"])
        return s, [{"document_id": 1, "version": "v"}], [], []

    def reuse(self, report_id, plan, sources):
        return self._reuse

    def extra(self, plan, sheet, need):
        self.extras.append(need)
        sheet.add("reason", "Nguyên nhân TCB nêu trong công văn giải trình (đã đối chiếu, khớp BCTC): dự phòng giảm")

    def write(self, question, plan, sheet, feedback, allow_need):
        self.writes.append((list(feedback), allow_need, len(sheet.facts)))
        return self.drafts.pop(0) if len(self.drafts) > 1 else self.drafts[0]

    def known_tickers(self):
        return {"TCB", "VCB"}

    def save(self, report_id, **fields):
        self.saved.append(fields)

    def last(self, key):
        return next(f[key] for f in reversed(self.saved) if key in f)


def run(deps, *resumes):
    app = build(deps, InMemorySaver())
    cfg = {"configurable": {"thread_id": "1"}}
    out = app.invoke({"report_id": 1, "question": "TCB quý 3?"}, cfg)
    for r in resumes:
        out = app.invoke(Command(resume=r), cfg)
    return app, cfg, out


def test_straight_through_to_done():
    deps = FakeDeps()
    run(deps)
    assert deps.last("status") == "done"
    assert deps.last("result")["draft"] == GOOD and deps.last("result")["links"]["0.0"][0]["fact_id"] == "S1"
    assert deps.last("guard_log")["attempts"][0]["violations"] == []


def test_missing_core_info_asks_back():
    deps = FakeDeps(ask="Bạn muốn xem mã nào?")
    run(deps)
    assert deps.last("status") == "needs_clarification" and deps.last("question_back") == "Bạn muốn xem mã nào?"


def test_confirmation_then_waiting_then_resume():
    deps = FakeDeps(missing=[{"ticker": "TCB", "year": 2025, "period": "Q3", "can_read": True, "note": ""}])
    app, cfg, _ = run(deps)
    assert deps.last("status") == "awaiting_confirmation"
    app.invoke(Command(resume=True), cfg)
    assert deps.requested and deps.last("status") == "waiting_data" and deps.last("request_ids") == [101]
    app.invoke(Command(resume=True), cfg)          # bộ canh: BCTC đã đọc xong
    assert deps.last("status") == "done"


def test_declining_reading_still_writes_with_what_is_there():
    deps = FakeDeps(missing=[{"ticker": "TCB", "year": 2025, "period": "Q3", "can_read": True, "note": ""}])
    run(deps, False)
    assert not deps.requested and deps.last("status") == "done"


def test_unreadable_missing_items_skip_confirmation():
    deps = FakeDeps(missing=[{"ticker": "TCB", "year": 2026, "period": "Q3", "can_read": False, "note": "chờ duyệt"}])
    run(deps)
    assert deps.last("status") == "done"


def test_rewrites_then_drops_still_wrong_sentences():
    deps = FakeDeps(drafts=[BAD, BAD, BAD])
    run(deps)
    assert len(deps.writes) == 3 and deps.writes[1][0]           # lần 2, 3 có phản hồi lỗi
    assert [s["text"] for s in deps.last("result")["draft"]["sections"][0]["sentences"]] == ["LNST của TCB đạt 7.943 tỷ."]
    assert deps.last("guard_log")["dropped"] == ["LNST của TCB đạt 9.999 tỷ."]
    deps = FakeDeps(drafts=[BAD, GOOD])
    run(deps)
    assert len(deps.writes) == 2 and deps.last("guard_log")["dropped"] == []


def test_need_rounds_are_capped():
    asking = {"sections": [], "need": [{"tool": "reasons", "ticker": "TCB", "metric": "none"}]}
    deps = FakeDeps(drafts=[asking, asking, asking, GOOD])
    run(deps)
    assert len(deps.extras) == 3 and deps.writes[3][1] is False   # lần thứ 4 không được xin thêm
    assert deps.last("status") == "done"


def test_reuse_ends_without_writing():
    deps = FakeDeps(reuse=True)
    run(deps)
    assert deps.writes == []


def test_empty_draft_fails_instead_of_done():
    deps = FakeDeps(drafts=[{"sections": [], "need": []}])
    run(deps)
    assert deps.last("status") == "failed" and deps.last("error") == "Không còn câu nào qua bộ kiểm tra số"
    assert deps.last("guard_log")["attempts"] and deps.last("sheet")


def test_all_sentences_dropped_fails():
    only_bad = {"sections": [{"heading": "Lợi nhuận", "sentences": [{"text": "LNST của TCB đạt 9.999 tỷ.", "uses": ["S1"]}]}],
                "need": []}
    deps = FakeDeps(drafts=[only_bad])
    run(deps)
    assert deps.last("status") == "failed" and deps.last("guard_log")["dropped"] == ["LNST của TCB đạt 9.999 tỷ."]


def test_only_explicit_true_counts_as_consent():
    deps = FakeDeps(missing=[{"ticker": "TCB", "year": 2025, "period": "Q3", "can_read": True, "note": ""}])
    run(deps, {"done": True})
    assert not deps.requested and deps.last("status") == "done"


def test_unreadable_note_uses_period_label():
    deps = FakeDeps(missing=[{"ticker": "TCB", "year": 2026, "period": "Q3", "can_read": False, "note": "chờ duyệt"},
                             {"ticker": "VCB", "year": 2026, "period": "Q2", "can_read": False, "note": ""}])
    run(deps)
    notes = deps.last("notes")
    assert "Không đọc được thêm BCTC TCB quý 3/2026: chờ duyệt" in notes
    assert "Không đọc được thêm BCTC VCB quý 2/2026" in notes


def test_resume_after_restart_with_new_app():
    saver = InMemorySaver()
    cfg = {"configurable": {"thread_id": "1"}}
    deps = FakeDeps(missing=[{"ticker": "TCB", "year": 2025, "period": "Q3", "can_read": True, "note": ""}])
    app = build(deps, saver)
    app.invoke({"report_id": 1, "question": "TCB quý 3?"}, cfg)
    app.invoke(Command(resume=True), cfg)
    assert deps.last("status") == "waiting_data"
    new_deps = FakeDeps()                                   # tiến trình mới: BCTC đã đọc xong
    build(new_deps, saver).invoke(Command(resume=True), cfg)
    assert new_deps.last("status") == "done" and not new_deps.requested
