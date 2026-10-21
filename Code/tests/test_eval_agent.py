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


def test_mutations_skip_unchanged_and_growth_word():
    text = "Doanh thu quý 3 của TCB là 5.000 tỷ đồng, tăng trưởng đều."
    muts = dict(agent_eval.mutations(text))
    assert "direction" not in muts                  # "tăng trưởng" không thành "giảm trưởng"
    assert all(t != text for t in muts.values())
    assert dict(agent_eval.mutations("TCB tăng trưởng và tăng 5%"))["direction"] == "TCB tăng trưởng và giảm 5%"
    assert "tốt hơn VIB." in dict(agent_eval.mutations(text, foreign="VIB"))["foreign_ticker"]


def _write_cache(provider="anthropic", usd=0.01, expl=0.002, missing=None, base=("a", "b"), status="done", fmt=2):
    d = {"status": status, "plan": {"tickers": ["TCB", "VCB"], "year": 2026}, "_usd": usd, "_seconds": 10.0,
         "guard_log": {"attempts": [{"sentences": 4, "violations": [
             {"section": 0, "sentence": 1, "kind": "number"}, {"section": 0, "sentence": 1, "kind": "direction"}]},
             {"sentences": 3, "violations": []}], "dropped": []},
         "result": {"draft": {"sections": [{"sentences": [{}, {}, {}]}]}}}
    if fmt:
        d |= {"_fmt": fmt, "_provider": provider, "_model": "m-1", "store_missing": missing or [], "base_facts": list(base),
              "_steps": {"explanation_read": {"usd": expl, "seconds": 4.0}, "writer": {"usd": usd - expl, "seconds": 6.0}}}
    return d


def test_provider_stats_separates_letter_cost_missing_data_and_units():
    caches = {"1": _write_cache(), "2": _write_cache(missing=[{"ticker": "VCB"}]), "3": _write_cache(fmt=0),
              "4": _write_cache(status="failed")}
    s = agent_eval.provider_stats(caches)
    st = s["st"]
    assert (st["done_full"], st["done_thin"], st["done_unknown"], st["not_done"]) == (1, 1, 1, 1)
    assert st["bad"] == 4 and st["sentences"] == 16                 # 1 câu có 2 lỗi: đếm câu một lần, lỗi hai lần
    assert s["kinds"] == {"number": 4, "direction": 4}
    assert abs(s["usd_expl"] - 0.006) < 1e-9 and abs(s["usd_write"] - 0.024) < 1e-9
    assert st["legacy"] == 1 and "chưa ghi" in s["models"] and "anthropic/m-1" in s["models"]
    text = "\n".join(agent_eval.format_stats("anthropic", s))
    assert "xong đủ số 1" in text and "xong nhưng thiếu số" in text and "đếm theo câu" in text and "đếm theo lỗi" in text


def test_compare_providers_flags_plan_and_sheet_mismatch():
    a = {"1": _write_cache(), "2": _write_cache(), "3": _write_cache(), "4": _write_cache(fmt=0)}
    b = {"1": _write_cache("openai"), "2": _write_cache("openai", base=("a", "c")), "3": _write_cache("openai"),
         "4": _write_cache("openai")}
    b["3"]["plan"] = {"tickers": ["TCB"], "year": 2026}
    res = agent_eval.compare_providers({"anthropic": a, "openai": b})
    assert (res["compared"], res["same"], res["unknown"]) == (4, 1, 1)
    assert len(res["plan_diff"]) == 1 and "[3]" in res["plan_diff"][0]
    assert len(res["sheet_diff"]) == 1 and "[2]" in res["sheet_diff"][0] and "từ dòng 2" in res["sheet_diff"][0]
    assert agent_eval.format_comparison(res)[0].startswith("so hai nhà")


def test_steps_delta_and_known_tickers():
    before = {"writer": {"usd": 0.1, "seconds": 5.0, "calls": 1}}
    after = {"writer": {"usd": 0.3, "seconds": 9.0, "calls": 2}, "explanation_read": {"usd": 0.002, "seconds": 3.0, "calls": 1},
             "idle": {"usd": 0.0, "seconds": 0.0, "calls": 0}}
    d = agent_eval.steps_delta(before, after)
    assert set(d) == {"writer", "explanation_read"} and abs(d["writer"]["usd"] - 0.2) < 1e-9
    docs = [{"plan": {"tickers": ["TCB"]}, "sheet": [{"ticker": "VIB"}, {"ticker": None}]}]
    golden = [{"tags": [], "expect": {"tickers": ["HPG"]}}, {"tags": ["mã không tồn tại"], "expect": {"tickers": ["XYZ"]}}]
    assert agent_eval.known_tickers(docs, golden) == {"TCB", "VIB", "HPG"}
