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


class _Http(Exception):
    def __init__(self, status):
        super().__init__(f"http {status}")
        self.status_code = status


def test_error_classification_and_retries():
    from services.llm import ProviderUnavailable
    t = agent_eval.is_transient
    assert t(_Http(429)) and t(_Http(503)) and t(_Http(408)) and t(ProviderUnavailable("x", sticky=True))
    assert t(type("APIConnectionError", (Exception,), {})("mất mạng"))
    assert not t(_Http(401)) and not t(_Http(400)) and not t(ProviderUnavailable("từ chối", sticky=False))
    assert not t(RuntimeError("bị cắt do vượt giới hạn độ dài")) and not t(ValueError("json sai"))

    calls = []

    def flaky(fail_times, exc):
        def fn():
            calls.append(1)
            if len(calls) <= fail_times:
                raise exc
            return "ok"
        return fn

    sleeps = []
    assert agent_eval.with_retries(flaky(2, _Http(503)), sleep=sleeps.append) == ("ok", None)
    assert len(calls) == 3 and len(sleeps) == 2                       # thử lại tối đa 2 lần
    calls.clear()
    res, fail = agent_eval.with_retries(flaky(9, _Http(503)), sleep=lambda s: None)
    assert res is None and fail[0] == "transient_exhausted" and len(calls) == 3
    calls.clear()
    res, fail = agent_eval.with_retries(flaky(9, RuntimeError("cắt")), sleep=lambda s: None)
    assert fail[0] == "deterministic" and len(calls) == 1               # lỗi tất định không thử lại


def test_summary_counts_failed_runs_and_missing_questions():
    failed = _write_cache(status="failed") | {"_error_kind": "deterministic", "error": "RuntimeError('cắt')"}
    failed.pop("guard_log")
    s = agent_eval.provider_stats({"1": _write_cache(), "2": failed}, eligible_n=44)
    assert s["st"]["not_done"] == 1 and s["errors"] == {"deterministic": 1} and s["eligible"] == 44
    text = "\n".join(agent_eval.format_stats("openai", s))
    assert "2/44 câu đã có kết quả" in text and "không xong 1" in text and "deterministic" in text
    rows = [{"expect": {"tickers": ["TCB"]}, "tags": []}, {"expect": {"tickers": []}, "tags": []},
            {"expect": {"tickers": ["XYZ"]}, "tags": ["mã không tồn tại"]}]
    assert len(agent_eval.eligible(rows)) == 1


def test_account_problems_stop_instead_of_retry_or_cache():
    from services.llm import ProviderUnavailable
    quota = _Http(429)
    quota.args = ("Error code: 429 - {'error': {'code': 'insufficient_quota'}}",)
    credit = _Http(400)
    credit.args = ("Your credit balance is too low to access the Anthropic API",)
    other400 = _Http(400)
    other400.args = ("invalid request: schema",)
    rate = _Http(429)
    rate.args = ("Rate limit reached for requests",)
    a = agent_eval.is_account_problem
    assert a(quota) and a(credit) and a(_Http(402)) and a(ProviderUnavailable("hết billing", sticky=True))
    assert not a(rate) and not a(other400) and not a(_Http(503)) and not a(RuntimeError("quota"))
    assert not agent_eval.is_transient(quota) and agent_eval.is_transient(rate)     # 429 hết hạn mức không bị thử lại
    assert not agent_eval.is_transient(credit) and not agent_eval.is_transient(other400)

    calls = []

    def boom(exc):
        def fn():
            calls.append(1)
            raise exc
        return fn

    res, fail = agent_eval.with_retries(boom(quota), sleep=lambda s: None)
    assert fail[0] == "account" and len(calls) == 1                     # dừng ngay, không thử lại
    assert agent_eval.with_retries(boom(credit), sleep=lambda s: None)[1][0] == "account"
    assert agent_eval.with_retries(boom(other400), sleep=lambda s: None)[1][0] == "deterministic"
    calls.clear()
    assert agent_eval.with_retries(boom(rate), sleep=lambda s: None)[1][0] == "transient_exhausted" and len(calls) == 3
