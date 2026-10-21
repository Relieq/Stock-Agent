from decimal import Decimal as D

from services.analyst.facts import Group, Pair, TickerData, build_sheet, chart_specs

B = D(10) ** 9


def bank(ticker, npat, npat_prev, prov=(917, 1499)):
    return TickerData(ticker, "TCTD", "quý 3/2026", {
        "npat_parent": Pair(D(npat) * B, D(npat_prev) * B, [{"document_id": 1, "page": 5}]),
        "provision": Pair(D(prov[0]) * B, D(prov[1]) * B),
        "opex": Pair(D(3000) * B, D(2800) * B), "toi": Pair(D(16588) * B, D(14242) * B)})


def test_yoy_metric_row_has_every_number_and_direction():
    sheet = build_sheet("yoy", [bank("TCB", 7943, 6419)], ["npat_parent", "provision"])
    s1, s2 = sheet.facts
    assert s1.text == ("LNST của cổ đông ngân hàng mẹ, TCB, quý 3/2026: 7.943 tỷ; cùng kỳ 6.419 tỷ; "
                       "thay đổi +23,7% (tăng 1.524 tỷ)")
    assert (s1.direction, s1.ticker, s1.sources) == ("up", "TCB", [{"document_id": 1, "page": 5}])
    assert s2.direction == "down" and "−38,8%" in s2.text and "giảm 582 tỷ" in s2.text


def test_losses_are_described_in_words():
    d = TickerData("ABC", "corporate", "quý 3/2026", {"npat_parent": Pair(D(-50) * B, D(-100) * B)})
    (f,) = build_sheet("yoy", [d], ["npat_parent"]).facts
    assert "lỗ thu hẹp từ 100 tỷ còn 50,0 tỷ" in f.text and "%" not in f.text and f.direction == "up"   # ty(): dưới 100 tỷ giữ 1 chữ số thập phân


def test_ratio_rows():
    sheet = build_sheet("yoy", [bank("TCB", 7943, 6419)], ["cir"])
    (f,) = sheet.facts
    assert f.text.startswith("Chi phí hoạt động trên tổng thu nhập hoạt động, TCB, quý 3/2026: 18,1%; cùng kỳ 19,7%")
    assert "−1,6 điểm %" in f.text and f.direction == "down"


def test_compare_rows_order_tickers():
    sheet = build_sheet("compare", [bank("TCB", 7943, 6419), bank("VCB", 9000, 7785)], ["npat_parent"])
    growth = next(f for f in sheet.facts if f.kind == "compare" and f.measure == "growth")
    level = next(f for f in sheet.facts if f.kind == "compare" and f.measure == "level")
    assert growth.order == ["TCB", "VCB"] and "TCB cao hơn VCB 8,1 điểm %" in growth.text
    assert level.order == ["VCB", "TCB"] and "VCB gấp 1,13 lần TCB" in level.text


def test_rank_rows_use_the_group():
    members = [bank("VPB", 1600, 1000), bank("TCB", 7943, 6419), bank("VCB", 9000, 7785)]
    sheet = build_sheet("rank", [members[1]], ["npat_parent"], {"TCTD": Group("các ngân hàng đang theo dõi", members)})
    rank = next(f for f in sheet.facts if f.kind == "rank" and f.measure == "growth")
    assert rank.order == ["VPB", "TCB", "VCB"] and "TCB xếp thứ 2 trong 3" in rank.text
    assert "trung vị nhóm +23,7%" in rank.text


def test_flags_become_rows():
    d = bank("TCB", 7943, 6419)
    d.flags = [("Lợi nhuận phần lớn ngoài hoạt động chính", "LNTT quý 100 tỷ.")]
    texts = [f.text for f in build_sheet("yoy", [d], ["npat_parent"]).facts]
    assert texts[-1] == "Cờ cảnh báo của thẻ KQKD, TCB, quý 3/2026: Lợi nhuận phần lớn ngoài hoạt động chính. LNTT quý 100 tỷ."


def test_chart_specs():
    specs = chart_specs("compare", [bank("TCB", 7943, 6419), bank("VCB", 9000, 7785)], ["npat_parent"])
    assert [s["type"] for s in specs] == ["paired", "bars"]
    assert specs[0]["items"] == [["TCB", 7943.0, 6419.0], ["VCB", 9000.0, 7785.0]]
    assert specs[1]["items"] == [["TCB", 23.7], ["VCB", 15.6]]


def corp(ticker, **pairs):
    return TickerData(ticker, "corporate", "quý 3/2026", {k: Pair(D(a) * B, D(b) * B) for k, (a, b) in pairs.items()})


def test_ratio_keeps_sign_when_loss_making():
    d = corp("ABC", gross_profit=(-100, 100), revenue=(1000, 1000))
    (f,) = build_sheet("yoy", [d], ["gross_margin"]).facts
    assert ": −10,0%; cùng kỳ 10,0%" in f.text and "−20,0 điểm %" in f.text and f.direction == "down"


def test_level_rank_of_expenses_uses_magnitude_even_if_stored_negative():
    members = [bank("AAA", 1, 1), bank("BBB", 1, 1), bank("CCC", 1, 1)]
    for m, v in zip(members, (-3000, -2000, -1000)):
        m.values["opex"] = Pair(D(v) * B, D(v) * B)
    sheet = build_sheet("rank", [members[1]], ["opex"], {"TCTD": Group("nhóm thử", members)})
    level = next(f for f in sheet.facts if f.kind == "rank" and f.measure == "level")
    assert level.order == ["AAA", "BBB", "CCC"] and "BBB xếp thứ 2 trong 3" in level.text
    assert "trung vị nhóm 2.000 tỷ" in level.text and "−" not in level.text


def test_flat_change_is_said_as_unchanged():
    d = corp("ABC", revenue=(100, 100), gross_profit=(10, 10))
    flat = build_sheet("yoy", [d], ["revenue"]).facts[0]
    assert flat.direction == "flat" and "không đổi so với cùng kỳ" in flat.text
    assert "tăng" not in flat.text and "%" not in flat.text
    d.values["revenue"] = Pair(D(100) * B, D(100) * B)
    (ratio,) = build_sheet("yoy", [d], ["gross_margin"]).facts
    assert "không đổi so với cùng kỳ" in ratio.text and "điểm %" not in ratio.text


def test_ties_in_compare_are_said_as_equal():
    a, b = bank("AAA", 200, 100), bank("BBB", 100, 50)
    sheet = build_sheet("compare", [a, b], ["npat_parent"])
    growth = next(f for f in sheet.facts if f.kind == "compare" and f.measure == "growth")
    assert "AAA và BBB bằng nhau" in growth.text and "cao hơn" not in growth.text
    c, d = bank("CCC", 100, 90), bank("DDD", 100, 80)
    level = next(f for f in build_sheet("compare", [c, d], ["npat_parent"]).facts if f.measure == "level")
    assert "CCC và DDD bằng nhau" in level.text and "gấp" not in level.text


def test_chart_unit_is_points_for_ratio_keys():
    specs = chart_specs("compare", [bank("TCB", 7943, 6419), bank("VCB", 9000, 7785)], ["cir"])
    assert [s["unit"] for s in specs] == ["điểm %"]
