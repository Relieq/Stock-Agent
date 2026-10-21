from decimal import Decimal as D

from services.analyst.guard import check_draft, check_sentence, matches, numbers
from services.analyst.sheet import FactSheet

KNOWN = {"TCB", "VCB", "VPB", "FPT", "MWG", "HPG"}


def sheet():
    s = FactSheet()
    s.add("metric", "LNST của cổ đông ngân hàng mẹ, TCB, quý 3/2026: 7.943 tỷ; cùng kỳ 6.419 tỷ; "
                    "thay đổi +23,7% (tăng 1.524 tỷ)", ticker="TCB", metric="npat_parent", direction="up",
          names=["lnst của cổ đông ngân hàng mẹ", "lnst", "lợi nhuận sau thuế"])
    s.add("metric", "Chi phí dự phòng rủi ro tín dụng, TCB, quý 3/2026: 917 tỷ; cùng kỳ 1.499 tỷ; "
                    "thay đổi −38,8% (giảm 582 tỷ)", ticker="TCB", metric="provision", direction="down",
          names=["chi phí dự phòng rủi ro tín dụng", "dự phòng"])
    return s


def test_numbers_as_written_in_vietnamese():
    ns = numbers("LNST quý 3/2026 đạt 7.943 tỷ, tăng 23,7%, cao hơn 8,1 điểm % và gấp 1,13 lần; 9 tháng năm 2026")
    assert [(n.kind, n.value) for n in ns] == [("money", D("7943e9")), ("pct", D("23.7")), ("pp", D("8.1")),
                                               ("times", D("1.13"))]
    assert numbers("gần 7,9 nghìn tỷ")[0].qualifier == "approx"
    assert numbers("hơn 20%")[0].qualifier == "more"
    assert numbers("VN30 có 13 ngân hàng")[0].value == 13          # VN30 không phải số
    assert numbers("gấp đôi")[0].value == 2


def test_rounding_follows_the_last_printed_digit():
    fact = numbers("7.943 tỷ")[0]
    assert matches(numbers("7,9 nghìn tỷ")[0], fact)
    assert not matches(numbers("7,8 nghìn tỷ")[0], fact)
    assert matches(numbers("khoảng 7,6 nghìn tỷ")[0], fact)        # "khoảng": lệch tối đa 5%
    assert matches(numbers("hơn 7.900 tỷ")[0], fact)
    assert not matches(numbers("dưới 7.900 tỷ")[0], fact)
    assert matches(numbers("giảm 38,8%")[0], numbers("−38,8%")[0])  # so độ lớn; chiều kiểm riêng


def test_every_number_needs_a_cited_row():
    s = sheet()
    ok = check_sentence("LNST của TCB đạt 7.943 tỷ, tăng 23,7%.", ["S1"], s, {"TCB"}, KNOWN)
    assert ok.violations == [] and [l.fact_id for l in ok.links] == ["S1", "S1"]
    bad = check_sentence("LNST của TCB đạt 8.100 tỷ.", ["S1"], s, {"TCB"}, KNOWN)
    assert [v.kind for v in bad.violations] == ["unsourced_number"]
    assert [v.kind for v in check_sentence("LNST tăng 23,7%.", [], s, {"TCB"}, KNOWN).violations] == ["no_source"]
    assert [v.kind for v in check_sentence("LNST tăng.", ["S9"], s, {"TCB"}, KNOWN).violations] == ["unknown_fact"]
    # số của dòng khác (dự phòng) không dùng được khi câu chỉ ghi S1
    assert [v.kind for v in check_sentence("Dự phòng còn 917 tỷ.", ["S1"], s, {"TCB"}, KNOWN).violations] == \
        ["unsourced_number"]


def test_advice_language_and_foreign_tickers():
    s = sheet()
    kinds = [v.kind for v in check_sentence("Nhà đầu tư nên mua TCB.", ["S1"], s, {"TCB"}, KNOWN).violations]
    assert kinds == ["advice"]
    assert check_sentence("Soi không đưa khuyến nghị đầu tư.", [], s, {"TCB"}, KNOWN).violations == []
    kinds = [v.kind for v in check_sentence("TCB tốt hơn VPB.", ["S1"], s, {"TCB"}, KNOWN).violations]
    assert "foreign_ticker" in kinds
    s.add("rank", "Thứ tự: VPB +60,1%, TCB +23,7%", order=["VPB", "TCB"], measure="growth", names=["lnst"])
    assert "foreign_ticker" not in [v.kind for v in check_sentence("VPB tăng 60,1%.", ["S3"], s, {"TCB"}, KNOWN).violations]


def test_check_draft_indexes_sentences():
    draft = {"sections": [{"heading": "Lợi nhuận", "sentences": [
        {"text": "LNST của TCB đạt 7.943 tỷ.", "uses": ["S1"]},
        {"text": "LNST của TCB đạt 9.000 tỷ.", "uses": ["S1"]}]}], "need": []}
    violations, links, _ = check_draft(draft, sheet(), {"TCB"}, KNOWN)
    assert [(v.section, v.sentence, v.kind) for v in violations] == [(0, 1, "unsourced_number")]
    assert [l.fact_id for l in links["0.0"]] == ["S1"]


def test_month_year_is_not_a_quantity():
    assert [n.kind for n in numbers("LNST quý 3 trong tháng 9/2026 đạt 7.943 tỷ")] == ["money"]


def test_year_used_as_quantity_is_checked():
    assert numbers("đạt 2000 tỷ")[0].kind == "money"
    assert numbers("năm 2026 và 2025") == []


def test_unit_must_be_a_whole_word():
    assert numbers("tỷ lệ 5 tỷ lệ")[0].kind == "plain"
    assert numbers("3 đồng thời")[0].kind == "plain"


def test_advice_in_verb_form_is_not_excused_by_negation_words():
    s = sheet()

    def kinds(t, uses=("S1",)):
        return [v.kind for v in check_sentence(t, list(uses), s, {"TCB", "MWG"}, KNOWN).violations]

    assert "advice" in kinds("Nhà đầu tư không phải lo, nên mua TCB.")
    assert "advice" in kinds("Nên cân nhắc mua TCB.")
    assert "advice" in kinds("Có thể cân nhắc bán MWG.")
    assert kinds("Soi không đưa khuyến nghị đầu tư.") == []
    assert kinds("Đây không phải là khuyến nghị mua bán.") == []
    assert kinds("Chi phí tăng có thể do lạm phát.") == []
