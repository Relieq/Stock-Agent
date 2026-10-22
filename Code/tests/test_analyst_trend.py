"""Xu hướng nhiều quý và tỷ lệ cần số dư bình quân (ROE, NIM) của agent báo cáo: phần tính thuần, không cần CSDL hay
mô hình."""

from decimal import Decimal as D
from types import SimpleNamespace

from services.analyst import ratios, store, trend
from services.analyst.charts import svg
from services.analyst.facts import Pair, TickerData, build_sheet, build_trend, trend_charts, trend_fact
from services.analyst.guard import check_sentence, numbers
from services.analyst.plan import PLAN_SCHEMA, Plan, check_plan
from services.analyst.sheet import FactSheet
from services.analyst.writer import write
from services.metrics.card import Source, Value

B = D(10) ** 9
KNOWN = {"TCB", "VCB", "FPT", "MBB"}


# ---- tỷ lệ -------------------------------------------------------------------------------------------------------

def test_annual_factor_quarter_and_ytd():
    assert ratios.annual_factor("quarter", "Q3") == 4
    assert ratios.annual_factor("ytd", "Q1") == 4 and ratios.annual_factor("ytd", "H1") == 2
    assert ratios.annual_factor("ytd", "Q3") == D(12) / 9 and ratios.annual_factor("ytd", "FY") == 1


def test_annualised_ratio_uses_two_point_average_and_never_guesses():
    # 100 tỷ một quý, vốn đầu 1.900 cuối 2.100 -> 400 / 2.000 = 20%
    assert ratios.annualised_ratio(D(100), D(1900), D(2100), D(4)) == 20
    assert ratios.annualised_ratio(D(100), None, D(2100), D(4)) is None      # thiếu số dư đầu kỳ: để trống
    assert ratios.annualised_ratio(None, D(1900), D(2100), D(4)) is None
    assert ratios.annualised_ratio(D(100), D(-10), D(0), D(4)) is None        # bình quân không dương


BANK_BS = {"b.sbv": D(50), "b.interbank": D(100), "b.trading_sec": D(5), "b.loans": D(800), "b.inv_sec": D(150),
           "b.cash": D(10), "b.lt_invest": D(7), "b.deriv_asset": D(3)}


def test_earning_assets_sum_and_required_rows():
    assert ratios.earning_assets(BANK_BS, set()) == D(1105)          # không tính tiền mặt, góp vốn, phái sinh
    no_trading = {k: v for k, v in BANK_BS.items() if k != "b.trading_sec"}
    assert ratios.earning_assets(no_trading, set()) == D(1100)       # dòng không bắt buộc không in: 0
    assert ratios.earning_assets({k: v for k, v in BANK_BS.items() if k != "b.loans"}, set()) is None
    assert ratios.earning_assets(BANK_BS, {"b.trading_sec"}) is None  # ô "cần xem lại": không tính


def test_parent_equity_bank_minority_inside_or_outside_total_equity():
    inside = {"b.te": D(200), "b.mi": D(10), "b.tl": D(1800), "b.tle": D(2000)}
    assert ratios.parent_equity_bank(inside, set()) == D(190)
    outside = {"b.te": D(200), "b.mi": D(10), "b.tl": D(1790), "b.tle": D(2000)}
    assert ratios.parent_equity_bank(outside, set()) == D(200)
    assert ratios.parent_equity_bank({"b.te": D(200), "b.mi": D(10)}, set()) is None     # không xác định được
    assert ratios.parent_equity_bank({"b.te": D(200)}, set()) == D(200)                  # không có cổ đông thiểu số
    assert ratios.parent_equity_bank(inside, {"b.mi"}) is None
    # không in tổng nợ phải trả (BID): cộng các khoản nợ
    no_tl = {"b.te": D(200), "b.mi": D(10), "b.cust_dep": D(1500), "b.papers": D(300), "b.tle": D(2000)}
    assert ratios.parent_equity_bank(no_tl, set()) == D(190)


def test_parent_equity_corporate():
    v = {"400": D(1000), "429": D(100)}
    assert ratios.parent_equity_corporate(v, set(), "429", True) == D(900)
    assert ratios.parent_equity_corporate({"400": D(1000)}, set(), None, False) == D(1000)
    assert ratios.parent_equity_corporate({"400": D(1000)}, set(), None, True) is None   # BCKQKD có tách: đọc sót
    assert ratios.parent_equity_corporate(v, {"400"}, "429", True) is None


class FakeStatement:
    def __init__(self, values):
        self.values = values


class FakeFacts:
    """Đủ thuộc tính như services.metrics.card.Facts cho phần tính ROE/NIM."""

    def __init__(self, template, bs, is_values, labels=None, missing=None, codes=None):
        self.template, self.document_id = template, 7
        self.statements = {"BS": FakeStatement(bs), "IS": FakeStatement(is_values)}
        self.rows = {("BS", c): SimpleNamespace(label=l, page=3) for c, l in (labels or {}).items()}
        self.missing = missing or set()
        self.codes = codes or {}

    def code(self, statement, metric):
        return self.codes.get(metric)

    def get(self, statement, code, column, expense=False):
        v = self.statements[statement].values.get(code, {}).get(column)
        return Value(v, Source(self.document_id, statement, code, column, 3, "", None) if v is not None else None)

    def metric(self, statement, metric, column):
        return self.get(statement, self.code(statement, metric), column)


def corp_facts(**kw):
    bs = {"400": {"begin_year": D(1900) * B, "end_period": D(2200) * B},
          "429": {"begin_year": D(100) * B, "end_period": D(200) * B}}
    is_values = {"61": {"q_cur": D(100) * B, "ytd_cur": D(100) * B}, "62": {"q_cur": D(5) * B}}
    return FakeFacts("TT99", bs, is_values, {"429": "8. Lợi ích cổ đông không kiểm soát"},
                     codes={"npat_parent": "61", "minority": "62"}, **kw)


def test_minority_row_found_by_label_in_equity_section():
    assert store.minority_code(corp_facts()) == "429"


def test_roe_q1_uses_begin_year_of_same_report():
    pair, why, prev = store.computed_ratio(None, "FPT", corp_facts(), set(), "roe", 2026, "Q1", "quarter",
                                           "fs_quarter", "Q1")
    # vốn của cổ đông mẹ: đầu năm 1.800, cuối kỳ 2.000 -> bình quân 1.900; 100 × 4 / 1.900
    assert why is None and prev is None and pair.prev is None
    assert round(pair.cur, 2) == D("21.05")
    assert {s["code"] for s in pair.sources} == {"61", "400"}


def test_roe_is_hidden_when_any_input_cell_needs_review():
    for cell in (("BS", "429", "begin_year"), ("BS", "400", "end_period"), ("IS", "61", "q_cur")):
        pair, why, _ = store.computed_ratio(None, "FPT", corp_facts(), {cell}, "roe", 2026, "Q1", "quarter",
                                            "fs_quarter", "Q1")
        assert pair.cur is None and "không tính được" in why


def test_roe_missing_when_minority_row_is_flagged_missing():
    f = corp_facts(missing={("BS", "429")})
    pair, why, _ = store.computed_ratio(None, "FPT", f, set(), "roe", 2026, "Q1", "quarter", "fs_quarter", "Q1")
    assert pair.cur is None


def test_nim_only_for_banks_and_ytd_annualised():
    bs = {k: {"begin_year": v * B, "end_period": v * B * D("1.1")} for k, v in BANK_BS.items()}
    f = FakeFacts("TCTD", bs, {"b.nii": {"ytd_cur": D(30) * B}}, codes={"nii": "b.nii"})
    pair, why, _ = store.computed_ratio(None, "TCB", f, set(), "nim", 2026, "H1", "ytd", "fs_semiannual", "H1")
    # tài sản sinh lãi 1.105 đầu năm, 1.215,5 cuối kỳ; 30 × 2 / 1.160,25
    assert why is None and round(pair.cur, 2) == D("5.17")
    assert store.balance(corp_facts(), set(), "nim", "end_period") is None


def computed_ticker(roe):
    return TickerData("FPT", "corporate", "quý 2/2026", {"roe": Pair(roe, None, [{"document_id": 1}])})


def test_roe_row_says_annualised_and_no_prior_year():
    (f,) = build_sheet("yoy", [computed_ticker(D("21.06"))], ["roe"]).facts
    assert f.text.startswith("ROE (quy năm), FPT, quý 2/2026: 21,1% (LNST của cổ đông công ty mẹ quy năm")
    assert "chưa có số cùng kỳ" in f.text and f.kind == "ratio"
    assert build_sheet("yoy", [computed_ticker(None)], ["roe"]).facts == []      # không tính được: không có dòng


def test_roe_not_in_default_metric_set():
    sheet = build_sheet("yoy", [TickerData("FPT", "corporate", "quý 2/2026", {
        "revenue": Pair(D(100) * B, D(90) * B), "gross_profit": Pair(D(40) * B, D(35) * B)})], [])
    assert all(f.metric != "roe" for f in sheet.facts)


# ---- xu hướng ----------------------------------------------------------------------------------------------------

def test_quarters_back_crosses_year():
    assert trend.quarters_back(2026, "Q2", 4) == [(2025, 3), (2025, 4), (2026, 1), (2026, 2)]


def test_streak_and_extremes():
    dirs = [None, "up", "up", "down"]
    assert trend.streak(dirs, 2, "up") == 2 and trend.streak(dirs, 3, "up") == 0
    assert trend.last_streak(dirs) == ("down", 1)
    series = [{"value": "5"}, {"value": None}, {"value": "7"}, {"value": "6"}]
    assert trend.extremes(series, False) == (2, 0)


def bank_q(y, q, v, prev, ticker="TCB"):
    if v is None:
        return (y, q, None)
    return (y, q, TickerData(ticker, "TCTD", f"quý {q}/{y}",
                             {"npat_parent": Pair(D(v) * B, D(prev) * B, [{"document_id": 10 * q + y % 10}])}))


def tcb_points(ticker="TCB", values=(5000, 6000, 7000, 6500)):
    prev = (4800, 5000, 6500, 6000)
    return [bank_q(y, q, v, p, ticker) for (y, q), v, p in zip(trend.quarters_back(2026, "Q2", 4), values, prev)]


def tcb_sheet():
    return build_trend({"TCB": ("TCTD", tcb_points())}, ["npat_parent"])


def test_trend_row_has_every_quarter_change_and_extremes():
    s = tcb_sheet()
    f = s.facts[0]
    assert f.kind == "trend" and f.ticker == "TCB" and len(f.series) == 4 and f.direction is None
    assert f.text.startswith("Xu hướng LNST của cổ đông ngân hàng mẹ, TCB, 4 quý từ quý 3/2025 đến quý 2/2026: "
                             "quý 3/2025 5.000 tỷ, quý 4/2025 6.000 tỷ, quý 1/2026 7.000 tỷ, quý 2/2026 6.500 tỷ")
    assert "quý 2/2026 −7,1% (giảm 500 tỷ)" in f.text and "quý 2/2026 so với quý 3/2025: +30,0%" in f.text
    assert "cao nhất trong 4 quý có số là quý 1/2026 (7.000 tỷ)" in f.text
    assert "là quý thứ 4 liên tiếp tăng" in f.text       # so với cùng kỳ
    assert len(f.sources) == 4
    # quý cuối: dòng chỉ tiêu so với cùng kỳ như báo cáo một mã
    assert s.facts[1].kind == "metric" and "6.500 tỷ" in s.facts[1].text


def test_trend_row_with_missing_quarter_and_losses():
    pts = [bank_q(2025, 3, None, None), bank_q(2025, 4, -100, 50), bank_q(2026, 1, 200, 100), bank_q(2026, 2, 300, 250)]
    f = trend_fact(FactSheet(), "TCB", "TCTD", "npat_parent", pts)
    assert "quý 3/2025 chưa có số" in f.text
    assert "quý 1/2026 chuyển từ lỗ 100 tỷ sang lãi 200 tỷ" in f.text      # lỗ ở một quý: không ghi %
    assert "quý 1/2026 +300" not in f.text and "quý 2/2026 +50,0% (tăng 100 tỷ)" in f.text
    assert trend_fact(FactSheet(), "TCB", "TCTD", "npat_parent", pts[:2]) is None   # dưới 2 quý có số


def test_trend_of_ratio_in_percentage_points():
    pts = [(2026, q, TickerData("FPT", "corporate", f"quý {q}/2026", {
        "gross_profit": Pair(D(g) * B, None), "revenue": Pair(D(100) * B, None)})) for q, g in ((1, 38), (2, 40))]
    f = trend_fact(FactSheet(), "FPT", "corporate", "gross_margin", pts)
    assert "quý 1/2026 38,0%, quý 2/2026 40,0%" in f.text and "quý 2/2026 +2,0 điểm %" in f.text


def test_trend_chart_is_a_line_per_ticker():
    (spec, *_) = trend_charts({"TCB": ("TCTD", tcb_points()), "MBB": ("TCTD", tcb_points("MBB"))}, ["npat_parent"])
    assert spec["type"] == "line" and spec["labels"] == ["Q3/2025", "Q4/2025", "Q1/2026", "Q2/2026"]
    assert [s["name"] for s in spec["series"]] == ["TCB", "MBB"] and spec["series"][0]["values"][0] == 5000.0
    out = svg(spec)
    assert out.count("<polyline") == 2 and "Q1/2026" in out


def test_line_chart_breaks_at_missing_quarter():
    out = svg({"type": "line", "title": "LNST", "unit": "tỷ đồng", "labels": ["a", "b", "c", "d"],
               "series": [{"name": "TCB", "values": [1.0, 2.0, None, 3.0]}]})
    assert out.count("<polyline") == 2 and out.count("<circle") == 3


def test_multi_ticker_trend_compares_last_quarter():
    s = build_trend({"TCB": ("TCTD", tcb_points()), "MBB": ("TCTD", tcb_points("MBB", (1, 2, 3, 4000)))},
                    ["npat_parent"])
    assert [f.kind for f in s.facts].count("trend") == 2 and any(f.kind == "compare" for f in s.facts)


# ---- bộ kiểm tra câu xu hướng -------------------------------------------------------------------------------------

def flagged(text, uses=("S1", "S2"), sheet=None):
    r = check_sentence(text, list(uses), sheet or tcb_sheet(), {"TCB", "MBB"}, KNOWN)
    return [v.kind for v in r.violations]


def test_trend_counts_are_not_read_as_figures():
    assert numbers("tăng 3 quý liên tiếp, cao nhất trong 4 quý, quý thứ 2 liên tiếp") == []


def test_streak_claims():
    assert flagged("LNST của TCB tăng 2 quý liên tiếp đến quý 1/2026.") == []
    assert flagged("LNST của TCB tăng quý thứ 2 liên tiếp trong quý 1/2026.") == []
    assert flagged("LNST của TCB tăng 3 quý liên tiếp.") == ["trend"]          # quý 2/2026 giảm
    assert flagged("LNST của TCB tăng 3 quý liên tiếp đến quý 1/2026.") == ["trend"]
    assert flagged("So với cùng kỳ năm trước, LNST của TCB tăng 4 quý liên tiếp.") == []
    assert flagged("LNST của TCB giảm 2 quý liên tiếp.") == ["trend"]


def test_extreme_claims():
    assert flagged("LNST quý 1/2026 của TCB cao nhất trong 3 quý.") == []        # 3 quý cuối của khung
    assert flagged("LNST quý 1/2026 của TCB cao nhất trong 4 quý.") == []
    assert flagged("LNST quý 1/2026 của TCB cao nhất trong 5 quý.") == ["trend"]    # bảng số chỉ có 4 quý
    assert flagged("LNST quý 3/2025 của TCB cao nhất trong 2 quý.") == ["trend"]    # ngoài 2 quý cuối
    assert flagged("LNST quý 2/2026 của TCB cao nhất trong 4 quý.") == ["trend"]
    assert flagged("LNST quý 2/2026 của TCB đạt 6.500 tỷ, thấp nhất trong 4 quý.") == ["trend"]
    assert flagged("LNST quý 3/2025 của TCB thấp nhất trong các quý.") == []
    assert flagged("LNST quý 1/2026 của TCB đạt 7.000 tỷ, mức cao nhất kể từ quý 3/2025.") == []
    assert flagged("LNST quý 4/2025 của TCB tăng mạnh nhất trong 4 quý.") == []      # +20,0% so với quý trước
    assert flagged("LNST quý 1/2026 của TCB tăng mạnh nhất trong các quý.") == ["trend"]
    assert flagged("LNST quý 2/2026 của TCB giảm mạnh nhất trong 4 quý.") == []


def test_quarter_on_quarter_claims():
    assert flagged("LNST của TCB quý 2/2026 giảm 7,1% so với quý trước.") == []
    assert flagged("LNST của TCB quý 2/2026 tăng 7,1% so với quý trước.") == ["trend"]
    assert flagged("LNST của TCB quý 2/2026 giảm từ quý 1.") == []
    assert flagged("LNST của TCB quý 2/2026 tăng từ quý 1.") == ["trend"]
    assert flagged("LNST của TCB quý 2/2026 thấp hơn quý trước.") == []
    assert flagged("LNST của TCB quý 2/2026 cao hơn quý trước.") == ["trend"]
    assert flagged("LNST của TCB quý 2/2026 tăng so với quý 3/2025.") == []
    assert flagged("LNST của TCB quý 2/2026 tăng 30,0% so với quý 3/2025.") == []
    assert flagged("LNST của TCB có xu hướng tăng qua các quý.") == []
    assert flagged("LNST của TCB có xu hướng giảm qua các quý.") == ["trend"]


def test_change_number_carries_its_direction():
    assert flagged("LNST quý 4/2025 của TCB đạt 6.000 tỷ, tăng 20,0%.") == []
    assert flagged("LNST quý 4/2025 của TCB đạt 6.000 tỷ, giảm 16,7%.") == ["trend"]


def test_trend_claim_without_trend_row_is_flagged():
    assert flagged("LNST của TCB tăng 3 quý liên tiếp.", uses=["S2"]) == ["trend"]
    assert flagged("LNST quý 2/2026 của TCB tăng 8,3% so với cùng kỳ.", uses=["S2"]) == []
    # "so với quý 2/2025" khi nói quý 2/2026 là so với cùng kỳ, không phải xu hướng
    assert flagged("LNST quý 2/2026 của TCB tăng 8,3% so với quý 2/2025.", uses=["S2"]) == []


def test_trend_claim_checks_the_named_ticker():
    s = build_trend({"TCB": ("TCTD", tcb_points()), "MBB": ("TCTD", tcb_points("MBB", (1000, 2000, 3000, 4000)))},
                    ["npat_parent"])
    trend_ids = [f.id for f in s.facts if f.kind == "trend"]
    assert flagged("LNST của MBB tăng 3 quý liên tiếp.", trend_ids, s) == []
    assert flagged("LNST của TCB tăng 3 quý liên tiếp.", trend_ids, s) == ["trend"]
    assert flagged("LNST của MBB và TCB đều tăng 3 quý liên tiếp.", trend_ids, s) == ["trend"]


# ---- kế hoạch, lời dặn ---------------------------------------------------------------------------------------------

def plan(**kw):
    base = dict(kind="trend", tickers=["tcb"], year=0, period="latest", basis="quarter", metrics=[], unclear=[],
                advice_request=False)
    return Plan(**(base | kw))


def check(p, latest=(2026, "Q2")):
    return check_plan(p, KNOWN, exists=lambda t: False, latest=lambda ts: latest, year_now=2026)


def test_schema_has_quarters():
    assert "trend" in PLAN_SCHEMA["properties"]["kind"]["enum"] and "quarters" in PLAN_SCHEMA["required"]
    assert {"roe", "nim", "gross_margin"} <= set(PLAN_SCHEMA["properties"]["metrics"]["items"]["enum"])


def test_trend_plan_defaults_to_four_latest_quarters():
    c = check(plan())
    assert c.ask is None and (c.plan.kind, c.plan.tickers, c.plan.year, c.plan.period) == ("trend", ["TCB"], 2026, "Q2")
    assert c.plan.quarters == 0 and c.plan.label() == "4 quý đến quý 2/2026"
    assert any("4 quý gần nhất" in n for n in c.notes)


def test_trend_plan_validation():
    assert check(plan(tickers=[])).ask.startswith("Bạn muốn xem mã")
    assert check(plan(quarters=20)).plan.quarters == 8
    assert check(plan(quarters=1)).plan.quarters == 2
    c = check(plan(year=2026, period="H1", basis="ytd", quarters=3))
    assert (c.plan.period, c.plan.basis, c.plan.quarters) == ("Q2", "quarter", 3)
    c = check(plan(tickers=["TCB", "VCB"]))
    assert c.plan.kind == "trend" and c.plan.tickers == ["TCB", "VCB"]       # nhiều mã vẫn là xu hướng
    assert check(plan(kind="yoy", quarters=4)).plan.quarters == 0             # loại khác: không có số quý


def test_old_saved_plans_without_quarters_still_load():
    old = {k: v for k, v in plan(kind="yoy").to_json().items() if k != "quarters"}
    assert Plan.from_json(old).quarters == 0


class FakeWriter:
    def __init__(self):
        self.prompt = ""

    def json_from_images(self, prompt, images, schema, schema_name, **kw):
        self.prompt = prompt
        return {"sections": [], "need": []}


def test_writer_gets_trend_and_ratio_rules():
    c = FakeWriter()
    p = check(plan(metrics=["roe"])).plan
    sheet = build_sheet("yoy", [computed_ticker(D(20))], ["roe"])
    write(c, "ROE của FPT 4 quý", p, sheet, [], False)
    assert "liên tiếp" in c.prompt and "quy năm" in c.prompt and "xu hướng nhiều quý" in c.prompt


def test_superlative_tied_to_named_quarter():
    assert flagged("LNST của TCB cao nhất ở quý 1/2026 với 7.000 tỷ và thấp nhất ở quý 3/2025 với 5.000 tỷ.") == []
    assert flagged("LNST của TCB cao nhất ở quý 2/2026 với 6.500 tỷ và thấp nhất ở quý 3/2025 với 5.000 tỷ.") == ["trend"]
    assert flagged("LNST của TCB ở quý 3/2025 là thấp nhất.") == []
    assert flagged("LNST của TCB ở quý 4/2025 là thấp nhất.") == ["trend"]
    assert flagged("LNST của TCB ở quý 1/2026 cao nhất và ở quý 3/2025 thấp nhất.") == []


def test_ratio_abbreviations_are_not_tickers():
    pts = [(2026, q, TickerData("MBB", "TCTD", f"quý {q}/2026", {"nim": Pair(D(v), None)})) for q, v in ((1, "3.8"),
                                                                                                    (2, "4.2"))]
    s = build_trend({"MBB": ("TCTD", pts)}, ["nim"])
    assert flagged("NIM quy năm của MBB tăng từ 3,8% ở quý 1/2026 lên 4,2% ở quý 2/2026, tức là tăng 0,4 điểm % so "
                   "với quý liền trước.", ["S1"], s) == []
    assert flagged("NIM quy năm của MBB giảm 0,4 điểm % so với quý liền trước.", ["S1"], s) == ["trend"]
