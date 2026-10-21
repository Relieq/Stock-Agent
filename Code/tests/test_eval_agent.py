import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("agent_eval", Path(__file__).parent.parent / "eval" / "agent.py")
agent_eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent_eval)


def test_score_plan_compares_fields():
    expect = {"kind": "compare", "tickers": ["VCB", "TCB"], "year": 2026, "period": "Q3", "basis": "quarter",
              "advice_request": False}
    got = dict(expect, tickers=["tcb", "VCB"])
    assert all(agent_eval.score_plan(got, expect).values())
    assert agent_eval.score_plan(dict(expect, period="Q2"), expect)["period"] is False


def test_mutations_change_meaning():
    muts = dict(agent_eval.mutations("LNST của TCB tăng 23,7%, nhanh hơn VCB."))
    assert muts["number"] != "LNST của TCB tăng 23,7%, nhanh hơn VCB." and "26,1%" in muts["number"]
    assert "giảm" in muts["direction"] and "chậm hơn" in muts["comparison"]
    assert "nên mua" in muts["advice"]
