from decimal import Decimal as D

from services.analyst.guard import _clauses, check_draft, check_sentence, matches, numbers
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


def test_ordinary_analysis_with_co_the_is_not_advice():
    s = sheet()
    for t in ["Doanh thu có thể giữ được đà tăng.",
              "Chi phí có thể do bán hàng tăng.",
              "Công ty có thể tiếp tục bán ra cổ phiếu quỹ.",
              "Có thể đầu tư mạnh vào tài sản."]:
        kinds = [v.kind for v in check_sentence(t, [], s, {"TCB", "MWG"}, KNOWN).violations]
        assert "advice" not in kinds, t


def compare_sheet():
    s = sheet()
    s.add("compare", "LNST của cổ đông ngân hàng mẹ, thay đổi so với cùng kỳ, quý 3/2026: TCB +23,7%, VCB +15,6%; "
                     "TCB cao hơn VCB 8,1 điểm %", metric="npat_parent", measure="growth", order=["TCB", "VCB"],
          names=["lnst"])
    s.add("compare", "LNST của cổ đông ngân hàng mẹ, xếp theo quy mô, quý 3/2026: VCB 9.000 tỷ, TCB 7.943 tỷ; "
                     "VCB gấp 1,13 lần TCB", metric="npat_parent", measure="level", order=["VCB", "TCB"], names=["lnst"])
    s.add("rank", "LNST, thay đổi so với cùng kỳ, quý 3/2026, các ngân hàng (3 mã có số): TCB xếp thứ 2 trong 3; "
                  "thứ tự: VPB +60,1%, TCB +23,7%, VCB +15,6%", ticker="TCB", metric="npat_parent", measure="growth",
          order=["VPB", "TCB", "VCB"], names=["lnst"])
    return s


def kinds(text, uses, s=None, allowed=("TCB", "VCB")):
    return [v.kind for v in check_sentence(text, uses, s or compare_sheet(), set(allowed), KNOWN).violations]


def test_direction_words_must_match_the_numbers():
    assert kinds("LNST của TCB tăng 23,7%.", ["S1"]) == []
    assert kinds("LNST của TCB giảm 23,7%.", ["S1"]) == ["direction"]
    assert kinds("Chi phí dự phòng của TCB giảm 38,8%.", ["S2"]) == []          # chi phí: theo độ lớn
    assert kinds("LNST của TCB tăng, còn chi phí dự phòng giảm.", ["S1", "S2"]) == []
    assert kinds("LNST của TCB giảm, còn chi phí dự phòng tăng.", ["S1", "S2"]) == ["direction", "direction"]


def test_comparisons_follow_the_order_in_the_sheet():
    assert kinds("LNST của TCB tăng nhanh hơn VCB 8,1 điểm %.", ["S3"]) == []
    assert kinds("LNST của VCB tăng nhanh hơn TCB.", ["S3"]) == ["comparison"]
    assert kinds("Về quy mô, LNST của VCB cao hơn TCB, gấp 1,13 lần.", ["S4"]) == []
    assert kinds("Về quy mô, LNST của TCB lớn hơn VCB.", ["S4"]) == ["comparison"]
    # chủ ngữ ở vế trước: "TCB tăng 23,7%, cao hơn VCB"
    assert kinds("LNST của TCB tăng 23,7%, nhanh hơn VCB.", ["S1", "S3"]) == []
    assert kinds("LNST của TCB tăng nhanh hơn VCB.", ["S1"]) == ["comparison"]   # không ghi dòng so sánh


def test_missing_comparison_row_suggests_which_row_to_add():
    s = compare_sheet()
    v = check_sentence("LNST của TCB tăng nhanh hơn VCB.", ["S1"], s, {"TCB", "VCB"}, KNOWN).violations
    assert [x.kind for x in v] == ["comparison"]
    assert "ghi thêm dòng S3" in v[0].detail and "S4" not in v[0].detail      # ưu tiên dòng cùng loại (tốc độ thay đổi)
    # quy mô: gợi ý dòng quy mô
    v = check_sentence("Về quy mô, LNST của VCB cao hơn TCB.", ["S1"], s, {"TCB", "VCB"}, KNOWN).violations
    assert "ghi thêm dòng S4" in v[0].detail
    # xếp hạng: gợi ý dòng có mã đó trong thứ tự
    v = check_sentence("VPB tăng mạnh nhất nhóm.", ["S1"], s, {"TCB", "VPB"}, KNOWN).violations
    assert [x.kind for x in v] == ["comparison"] and "S5" in v[0].detail
    # không có dòng nào chứa đủ mã thì không gợi ý
    v = check_sentence("LNST của TCB tăng nhanh hơn FPT.", ["S1"], s, {"TCB", "FPT"}, KNOWN).violations
    assert [x.kind for x in v] == ["comparison"] and "ghi thêm" not in v[0].detail


def test_superlatives_use_the_rank_order():
    s = compare_sheet()
    assert [v.kind for v in check_sentence("VPB tăng mạnh nhất nhóm.", ["S5"], s, {"TCB"}, KNOWN).violations] == []
    assert [v.kind for v in check_sentence("VCB tăng nhanh nhất nhóm.", ["S5"], s, {"TCB", "VCB"}, KNOWN).violations] \
        == ["comparison"]
    assert [v.kind for v in check_sentence("VCB tăng chậm nhất nhóm.", ["S5"], s, {"TCB", "VCB"}, KNOWN).violations] \
        == []


def test_loss_wording_and_unresolved_clauses():
    s = FactSheet()
    s.add("metric", "LNST, ABC, quý 3/2026: −50 tỷ; cùng kỳ −100 tỷ; lỗ thu hẹp từ 100 tỷ còn 50 tỷ", ticker="ABC",
          metric="npat_parent", direction="up", names=["lnst"])
    assert [v.kind for v in check_sentence("ABC lỗ giảm còn 50 tỷ.", ["S1"], s, {"ABC"}, {"ABC"}).violations] == []
    r = check_sentence("Mọi thứ đều tăng.", ["S1"], s, {"ABC"}, {"ABC"})
    assert r.violations == []            # câu không nói chỉ tiêu hay mã nào: không đoán chiều, chỉ cảnh báo
    assert r.warnings and r.warnings[0].startswith("không rõ chiều")


# --- Vòng sửa 1: các câu đúng từng bị bắt nhầm, các câu sai từng bị bỏ lọt ---

def growth_sheet():
    s = FactSheet()
    s.add("rank", "Thay đổi so với cùng kỳ, quý 3/2026: AAA +10%, BBB −5%, CCC −20%; thứ tự: AAA, BBB, CCC",
          measure="growth", order=["AAA", "BBB", "CCC"], names=["lnst"])
    return s


def loss_sheet():
    s = FactSheet()
    s.add("metric", "LNST, ABC, quý 3/2026: 50 tỷ; cùng kỳ −100 tỷ; chuyển từ lỗ sang lãi", ticker="ABC",
          direction="up", names=["lnst"])
    s.add("metric", "LNST, XYZ, quý 3/2026: −80 tỷ; cùng kỳ 20 tỷ", ticker="XYZ", direction="down", names=["lnst"])
    s.add("metric", "Lãi/lỗ tỷ giá, ABC, quý 3/2026: 30 tỷ; cùng kỳ 10 tỷ", ticker="ABC", direction="up",
          names=["lãi/lỗ tỷ giá"])
    return s


def test_scale_and_growth_are_read_per_clause():
    assert kinds("Về quy mô, VCB cao hơn TCB, nhưng TCB tăng nhanh hơn.", ["S3", "S4"]) == []
    assert kinds("Về quy mô, VCB cao hơn TCB; LNST của TCB tăng 23,7%.", ["S1", "S4"]) == []
    assert kinds("Điểm nhấn là VCB lớn hơn TCB về LNST.", ["S4"]) == []         # "Điểm nhấn" không phải "điểm %"
    assert kinds("Điểm nhấn là TCB lớn hơn VCB về LNST.", ["S4"]) == ["comparison"]


def test_decimal_comma_does_not_split_clauses():
    assert len(_clauses("LNST của TCB tăng 23,7%")) == 1
    assert len(_clauses("TCB tăng 23,7%, còn VCB tăng 15,6%")) == 2


def test_single_ticker_clause_keeps_the_right_side():
    assert kinds("VCB tăng 15,6%, còn TCB tăng nhanh hơn.", ["S3"]) == []
    assert kinds("VCB tăng 15,6%, còn TCB tăng chậm hơn.", ["S3"]) == ["comparison"]
    assert kinds("So với VCB, TCB tăng nhanh hơn.", ["S3"]) == []
    assert kinds("So với VCB, TCB tăng chậm hơn.", ["S3"]) == ["comparison"]
    assert kinds("LNST của TCB tăng 23,7%, nhanh hơn VCB.", ["S1", "S3"]) == []          # VCB sau từ so sánh: vế sau
    assert kinds("LNST của TCB tăng 23,7%, chậm hơn VCB.", ["S1", "S3"]) == ["comparison"]


def test_comparison_without_two_sides_is_a_warning_not_a_guess():
    r = check_sentence("Tăng nhanh hơn.", ["S3"], compare_sheet(), {"TCB", "VCB"}, KNOWN)
    assert r.violations == [] and any("so sánh" in w for w in r.warnings)


def test_decline_words_flip_the_comparison():
    g = growth_sheet()
    allowed = ("AAA", "BBB", "CCC")
    assert kinds("CCC giảm mạnh nhất nhóm.", ["S1"], g, allowed) == []
    assert kinds("AAA giảm mạnh nhất nhóm.", ["S1"], g, allowed) == ["comparison"]
    assert kinds("CCC giảm nhanh hơn BBB.", ["S1"], g, allowed) == []
    assert kinds("BBB giảm nhanh hơn CCC.", ["S1"], g, allowed) == ["comparison"]
    assert kinds("BBB giảm ít hơn CCC.", ["S1"], g, allowed) == []
    assert kinds("CCC giảm ít hơn BBB.", ["S1"], g, allowed) == ["comparison"]
    # "giảm ít nhất" chưa rõ nghĩa trong bảng xếp theo tăng trưởng: chỉ cảnh báo
    r = check_sentence("AAA giảm ít nhất nhóm.", ["S1"], g, set(allowed), KNOWN)
    assert r.violations == [] and r.warnings


def test_loss_inversion_only_for_loss_right_before_the_verb():
    s, allowed = loss_sheet(), ("ABC", "XYZ")
    assert kinds("LNST của XYZ giảm do khoản lỗ mở rộng.", ["S2"], s, allowed) == []
    assert kinds("LNST của ABC tăng so với khoản lỗ 100 tỷ cùng kỳ.", ["S1"], s, allowed) == []
    assert kinds("Lãi/lỗ tỷ giá tăng.", ["S3"], s, allowed) == []
    assert kinds("ABC lỗ giảm còn 50 tỷ.", ["S1"], s, allowed) == []
    assert kinds("ABC lỗ tăng.", ["S1"], s, allowed) == ["direction"]


def test_negation_and_compound_words_are_not_direction():
    assert kinds("Chi phí dự phòng của TCB không tăng.", ["S2"]) == []
    assert kinds("Chi phí dự phòng của TCB giảm 38,8%, nhờ công ty tăng cường quản trị rủi ro.", ["S2"]) == []
    r = check_sentence("Chi phí dự phòng của TCB không tăng.", ["S2"], sheet(), {"TCB"}, KNOWN)
    assert r.warnings
    assert kinds("LNST của TCB tăng vốn điều lệ, giảm giá cổ phiếu.", ["S1"]) == []


def test_connectors_split_clauses_and_mixed_words_warn():
    assert kinds("LNST của TCB tăng nhờ chi phí dự phòng giảm.", ["S1", "S2"]) == []
    assert kinds("LNST của TCB giảm nhờ chi phí dự phòng tăng.", ["S1", "S2"]) == ["direction", "direction"]
    r = check_sentence("LNST của TCB tăng và giảm.", ["S1"], sheet(), {"TCB"}, KNOWN)
    assert r.violations == [] and r.warnings


def test_one_of_the_fastest_is_not_a_strict_superlative():
    assert kinds("TCB là một trong những ngân hàng tăng nhanh nhất.", ["S5"]) == []
    assert kinds("TCB là ngân hàng tăng nhanh nhất.", ["S5"]) == ["comparison"]
