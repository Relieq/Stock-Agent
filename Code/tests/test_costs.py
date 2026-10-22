"""Tổng chi phí: bản chốt trước ngày mở sổ cộng các lần gọi trong sổ từ thời điểm chốt (không CSDL, không gọi mô hình)."""
import json
import tempfile
from pathlib import Path

from services import costs


def test_report_uses_baseline_plus_ledger_after_cutoff(monkeypatch):
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as d:
        d = Path(d)
        (d / "llm_cost_baseline.json").write_text(json.dumps({"cutoff": "2026-10-22T13:00:00+00:00", "entries": [
            ["2026-10-20", "statement_IS", None, 3, 100, 50, 0.5]]}), encoding="utf-8")
        ledger = d / "llm_calls.jsonl"
        ledger.write_text("\n".join(json.dumps(x) for x in [
            {"at": "2026-10-22T19:59:00+0700", "step": "statement_IS", "usd": 9.0},     # trước lúc chốt: đã nằm trong bản chốt
            {"at": "2026-10-22T20:30:00+0700", "step": "explanation_read", "usd": 0.002, "input_tokens": 10},
            {"at": "2026-10-22T13:31:00+0000", "step": "statement_IS", "usd": 0.1}]) + "\n", encoding="utf-8")
        monkeypatch.setattr(costs, "raw_data_dir", lambda: d)
        monkeypatch.setattr(costs, "_records", lambda: iter(()))
        monkeypatch.setenv("LLM_LEDGER", str(ledger))
        rep = costs.report()
        assert rep.ledger_since == "2026-10-22T13:00:00+00:00"
        assert round(rep.total.usd, 3) == 0.602 and rep.total.calls == 5
        assert round(rep.by_step["statement_IS"].usd, 3) == 0.6 and rep.by_day["2026-10-22"].calls == 2
        costs.add_reports(rep, conn=None)          # có sổ: không cộng thêm báo cáo agent (sổ đã gồm)
        assert rep.total.calls == 5
