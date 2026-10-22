"""Nguyên nhân từ công văn giải trình trên thẻ KQKD: chọn phần công văn, gắn nhãn đối chiếu, giữ lời đầy đủ (không CSDL)."""
from services.analyst.explanations import Check, SectionResult
from services.metrics.letters import _section, build_view


def test_section_prefers_same_scope_and_quarter():
    secs = [{"scope": "separate", "period_kind": "quarter"}, {"scope": "consolidated", "period_kind": "ytd"},
            {"scope": "consolidated", "period_kind": "quarter"}]
    assert _section(secs, "consolidated") is secs[2]
    assert _section(secs[:1], "consolidated") is None
    assert _section(secs[:2], "consolidated") is secs[1]


def test_view_splits_headline_and_reasons_with_full_text():
    long = "Doanh thu thuần tăng 75% nhờ hợp nhất mảng bán lẻ " + "x" * 120
    sec = {"scope": "consolidated", "period_kind": "quarter", "reasons": [{"text": long}, {"text": "Chi phí bán hàng tăng"}]}
    res = SectionResult("consolidated", "quarter", "LNST", [
        Check("lợi nhuận kỳ này", "khớp", "4.551.971 triệu VND", "4.552,0 tỷ"),
        Check(long[:120], "không kiểm được", note="số của một mảng"),
        Check("Chi phí bán hàng tăng", "lệch", "37%", "+30,0%")])
    v = build_view(sec, res)
    assert [h.text for h in v.headline] == ["lợi nhuận kỳ này"] and v.headline[0].css == "ok"
    assert v.reasons[0].text == long and v.reasons[0].css == "muted" and v.reasons[0].detail == "số của một mảng"
    assert v.reasons[1].css == "bad" and v.reasons[1].detail == "công ty nêu 37%, BCTC +30,0%"


def test_view_without_matching_bctc_shows_no_unchecked_reasons():
    sec = {"scope": "consolidated", "period_kind": "quarter", "reasons": [{"text": "Lãi tăng"}]}
    res = SectionResult("consolidated", "quarter", None, [Check("cả phần", "không kiểm được", note="chưa có BCTC")])
    v = build_view(sec, res)
    assert v.reasons == [] and v.headline[0].detail == "chưa có BCTC"
