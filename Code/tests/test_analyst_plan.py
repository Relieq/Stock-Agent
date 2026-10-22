from datetime import date

from services.analyst import catalog
from services.analyst.plan import PLAN_SCHEMA, Plan, check_plan, label, parse_request

KNOWN = {"TCB", "VCB", "FPT"}


class FakeClient:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def json_from_images(self, prompt, images, schema, schema_name, **kw):
        self.calls.append((prompt, schema_name))
        return self.answer


def plan(**kw):
    base = dict(kind="compare", tickers=["vcb", "TCB"], year=2026, period="Q3", basis="quarter", metrics=[],
                unclear=[], advice_request=False)
    return Plan(**(base | kw))


def check(p, latest=(2026, "Q3")):
    return check_plan(p, KNOWN, exists=lambda t: t == "ABC", latest=lambda ts: latest, year_now=2026)


def no_latest(ts):
    raise AssertionError("không được tra kỳ gần nhất khi kỳ đã nêu")


def test_schema_has_no_nullable_enum():
    for prop in PLAN_SCHEMA["properties"].values():
        assert "null" not in str(prop.get("type"))
    assert set(PLAN_SCHEMA["required"]) == set(PLAN_SCHEMA["properties"])


def test_parse_request_sends_question_and_reads_plan():
    client = FakeClient(plan().to_json())
    p = parse_request(client, "so sánh VCB và TCB quý 3", date(2026, 10, 21), [("TCB", "Techcombank")])
    assert p.tickers == ["vcb", "TCB"] and client.calls[0][1] == "plan_request"
    assert "so sánh VCB và TCB quý 3" in client.calls[0][0] and "21/10/2026" in client.calls[0][0]


def test_tickers_are_normalised_and_unknown_ones_asked_back():
    c = check(plan())
    assert c.ask is None and c.plan.tickers == ["VCB", "TCB"]
    assert check(plan(tickers=[])).ask.startswith("Bạn muốn xem mã")
    assert "XYZ" in check(plan(tickers=["XYZ"])).ask
    assert check(plan(tickers=["ABC", "VCB"])).ask is None          # mã ngoài danh sách nhưng có trên Vietstock


def test_kind_follows_number_of_tickers_and_latest_is_filled():
    c = check(plan(tickers=["FPT"]))
    assert c.plan.kind == "yoy" and c.notes
    c = check(plan(kind="yoy"))
    assert c.plan.kind == "compare"
    c = check(plan(period="latest", year=0), latest=(2026, "Q2"))
    assert (c.plan.year, c.plan.period) == (2026, "Q2") and "quý 2/2026" in c.notes[-1]
    assert check(plan(period="latest", year=0), latest=None).ask
    assert check(plan(period="H1")).plan.basis == "ytd"
    assert check(plan(period="Q1", basis="ytd")).plan.basis == "quarter"
    assert check(plan(advice_request=True)).notes[-1].startswith("Soi chỉ cung cấp thông tin")
    assert check(plan(metrics=["npat_parent", "khong_co"])).plan.metrics == ["npat_parent"]


def test_concrete_period_without_year_uses_current_year_not_latest():
    c = check_plan(plan(period="Q3", year=0), KNOWN, exists=lambda t: False, latest=no_latest, year_now=2026)
    assert (c.plan.year, c.plan.period) == (2026, "Q3") and "năm 2026" in c.notes[-1]
    assert "kỳ gần nhất" not in " ".join(c.notes)


def test_basis_follows_final_period_after_latest_fill():
    c = check(plan(period="latest", year=0, basis="ytd"), latest=(2026, "Q1"))
    assert c.plan.basis == "quarter" and c.plan.period == "Q1"
    assert "quý 1/2026" in c.notes[-1]


def test_labels():
    assert label(2026, "Q3", "quarter") == "quý 3/2026"
    assert label(2026, "Q3", "ytd") == "lũy kế 9 tháng năm 2026"
    assert label(2026, "H1", "ytd") == "6 tháng đầu năm 2026"
    assert label(2025, "FY", "ytd") == "năm 2025"


def test_catalog_keys():
    assert catalog.keys_for("TCTD", []) == ["nii", "toi", "provision", "pbt", "npat_parent", "cir"]
    assert catalog.keys_for("corporate", ["provision", "revenue"]) == ["revenue"]
    assert catalog.common_keys({"TCTD", "corporate"}, []) == ["pbt", "npat_parent"]
    assert catalog.common_keys({"TCTD"}, ["nii"]) == ["nii"]
    assert "lnst" in catalog.names("TCTD", "npat_parent")


def test_screen_needs_no_ticker_and_uses_the_latest_quarter_most_tickers_have():
    p = plan(kind="screen", tickers=[], period="latest", year=0, sector="TCTD", measure="level")
    c = check_plan(p, KNOWN, exists=lambda t: False, latest=no_latest, year_now=2026,
                   latest_all=lambda sector: (2026, "Q2") if sector == "TCTD" else None)
    assert c.ask is None and (c.plan.kind, c.plan.tickers, c.plan.year, c.plan.period) == ("screen", [], 2026, "Q2")
    assert (c.plan.sector, c.plan.measure) == ("TCTD", "level") and "phần lớn các mã" in c.notes[-1]


def test_screen_with_named_tickers_becomes_rank_or_compare():
    c = check(plan(kind="screen", tickers=["TCB"]))
    assert c.plan.kind == "rank" and "vị trí" in c.notes[0]
    c = check(plan(kind="screen", tickers=["TCB", "VCB"], sector="TCTD", measure="level"))
    assert c.plan.kind == "compare" and (c.plan.sector, c.plan.measure) == ("all", "growth")   # chỉ dùng cho screen


def test_ask_back_lists_the_five_question_kinds():
    ask = check(plan(kind="yoy", tickers=[])).ask
    assert ask.startswith("Bạn muốn xem mã") and ask.count("\n- ") == 5 and "tốt nhất" in ask and "xu hướng" in ask


def test_old_saved_plans_without_sector_still_load():
    old = {k: v for k, v in plan().to_json().items() if k not in ("sector", "measure")}
    assert Plan.from_json(old).sector == "all"
