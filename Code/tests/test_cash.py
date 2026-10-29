from decimal import Decimal as D
from types import SimpleNamespace

from services.extraction.validate import Statement
from services.metrics.card import Facts
from services.metrics.cash import bridge, cash_quality, period_days

B = D(10**9)
LABELS = {"01": "Lợi nhuận trước thuế", "08": "Lợi nhuận từ hoạt động kinh doanh trước thay đổi vốn lưu động"}


def _facts(template="TT99", cf=None, is_=None, bs=None, multiplier=D(1)):
    """Facts dựng tay: mỗi báo cáo là {mã: {cột: số tỷ}}."""
    f = Facts.__new__(Facts)
    f.document_id, f.template, f.missing, f.flip_is = 1, template, set(), False
    f.statements, f.rows = {}, {}
    for name, rows in (("CF", cf), ("IS", is_), ("BS", bs)):
        if rows is None:
            continue
        f.statements[name] = Statement(name, multiplier, {c: {k: D(v) * B for k, v in cols.items()}
                                                          for c, cols in rows.items()})
        for i, c in enumerate(rows):
            f.rows[(name, c)] = SimpleNamespace(page=5 + i, label=LABELS.get(c, f"dòng {c}"), values_raw={})
    return f


# MWG quý 3/2026, LCTT lũy kế 9 tháng (tỷ đồng, làm tròn từ số đã kiểm chứng)
MWG_CF = {"01": {"ytd_cur": "11599.674"}, "08": {"ytd_cur": "11384.366"}, "09": {"ytd_cur": "-1721.388"},
          "10": {"ytd_cur": "-7953.171"}, "11": {"ytd_cur": "4794.780"}, "12": {"ytd_cur": "-40.122"},
          "14": {"ytd_cur": "-1336.956"}, "15": {"ytd_cur": "-2083.943"},
          "20": {"ytd_cur": "3043.566", "ytd_prev_year": "6708"}}


def test_bridge_groups_by_effect_on_cash_without_signs():
    table, reason = bridge(_facts(cf=MWG_CF), set())
    assert reason is None
    down = [(r["name"], r["value"].value) for r in table["down"]]
    up = [(r["name"], r["value"].value) for r in table["up"]]
    assert down[0] == ("Nhập thêm hàng, tồn kho tăng", D("7953.171") * B)     # khoản lớn nhất đứng đầu
    assert all(v > 0 for _, v in down + up)                                  # không còn số âm
    assert up == [("Nợ nhà cung cấp và các khoản phải trả nhiều hơn", D("4794.780") * B)]
    assert ("Các khoản nhỏ khác", D("40.122") * B) in down                   # 0,35% mốc đầu
    assert table["start"].value == D("11384.366") * B and table["end"].value == D("3043.566") * B
    total = table["start"].value - sum(r["value"].value for r in table["down"]) + sum(r["value"].value for r in table["up"])
    assert total == table["end"].value


def test_bridge_refuses_when_lines_do_not_add_up_or_cell_is_hidden():
    bad = {**MWG_CF, "10": {"ytd_cur": "-7900"}}
    assert bridge(_facts(cf=bad), set())[0] is None
    table, reason = bridge(_facts(cf=MWG_CF), {("CF", "10", "ytd_cur")})
    assert table is None and "xem lại" in reason


def test_bridge_computes_start_when_line_08_is_not_printed():
    cf = {"01": {"ytd_cur": "100"}, "02": {"ytd_cur": "20"}, "09": {"ytd_cur": "-50"}, "20": {"ytd_cur": "70"}}
    table, _ = bridge(_facts(cf=cf), set())
    assert table["start"].value == 120 * B and table["start"].computed


def test_direct_method_cash_flow_has_no_bridge():
    LABELS["01"] = "Tiền thu từ bán hàng, cung cấp dịch vụ"
    try:
        table, reason = bridge(_facts(cf={"01": {"ytd_cur": "500"}, "20": {"ytd_cur": "70"}}), set())
    finally:
        LABELS["01"] = "Lợi nhuận trước thuế"
    assert table is None and "trực tiếp" in reason


def test_banks_and_securities_firms_are_skipped():
    assert cash_quality(_facts(template="TCTD", cf=MWG_CF), 2026, "Q3") == (None, None)
    assert cash_quality(_facts(template="CTCK", cf=MWG_CF), 2026, "Q3") == (None, None)


def test_summary_ratio_and_balances():
    is_ = {"10": {"ytd_cur": "147827", "ytd_prev_year": "113607"}, "11": {"ytd_cur": "115886", "ytd_prev_year": "91360"},
           "60": {"ytd_cur": "9634", "ytd_prev_year": "4989"}}
    bs = {"130": {"end_period": "3800", "begin_year": "2173"}, "140": {"end_period": "35054", "begin_year": "27267"}}
    out, _ = cash_quality(_facts(cf=MWG_CF, is_=is_, bs=bs), 2026, "Q3")
    assert round(out["summary"]["ytd_cur"]["ratio"]) == 32 and round(out["summary"]["ytd_prev_year"]["ratio"]) == 134
    inv = out["balances"][0]
    assert inv["name"] == "Hàng tồn kho" and round(inv["days"]) == 83
    assert round(inv["change"]) == 29 and round(inv["flow_change"]) == 27


def test_period_days():
    assert period_days(2026, "Q3") == 273
    assert period_days(2028, "Q1") == 91        # năm nhuận
    assert period_days(2026, "Q4") == 365


def test_first_quarter_uses_quarter_column_but_other_quarters_do_not():
    is_ = {"60": {"q_cur": "100", "q_prev_year": "80"}}
    cf = {"20": {"ytd_cur": "50", "ytd_prev_year": "40"}}
    out, _ = cash_quality(_facts(cf=cf, is_=is_), 2026, "Q1")
    assert out["summary"]["ytd_cur"]["ratio"] == 50
    out, reason = cash_quality(_facts(cf=cf, is_=is_), 2026, "Q4")
    assert out is None and "lũy kế" in reason
