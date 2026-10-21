from services.analyst.charts import svg
from services.analyst.render import context, sentence_html


def test_bars_and_paired_charts_are_svg_with_labels():
    s = svg({"type": "bars", "title": "LNST: thay đổi", "unit": "%", "items": [["VPB", 60.1], ["VCB", -5.2]],
             "highlight": ["VCB"]})
    assert s.startswith("<svg") and "VPB" in s and "60,1%" in s and "−5,2%" in s and "class=\"hl\"" in s
    p = svg({"type": "paired", "title": "LNST", "unit": "tỷ đồng", "items": [["TCB", 7943.0, 6419.0]], "highlight": []})
    assert "7.943" in p and "6.419" in p and "Kỳ này" in p and "Cùng kỳ" in p


def test_numbers_link_to_their_rows_and_text_is_escaped():
    html = str(sentence_html("LNST <b> đạt 7.943 tỷ.", [{"start": 13, "end": 21, "fact_id": "S1"}]))
    assert html == 'LNST &lt;b&gt; đạt <a class="num" href="#S1">7.943 tỷ</a>.'


def test_context_hides_dropped_sentences_from_users():
    row = {"id": 5, "question": "TCB?", "status": "done", "plan": {"kind": "yoy", "tickers": ["TCB"], "year": 2026,
           "period": "Q3", "basis": "quarter", "metrics": [], "unclear": [], "advice_request": False},
           "notes": ["ghi chú"], "charts": [], "missing": None, "question_back": None, "error": None,
           "sheet": [{"id": "S1", "kind": "metric", "text": "LNST 7.943 tỷ", "ticker": "TCB", "metric": None,
                      "direction": None, "measure": None, "order": [], "names": [],
                      "sources": [{"document_id": 9, "page": 4, "label": "LNST", "raw": "7.943.000"}]}],
           "result": {"draft": {"sections": [{"heading": "Lợi nhuận", "sentences": [{"text": "Đạt 7.943 tỷ.",
                                                                                      "uses": ["S1"]}]}]},
                      "links": {"0.0": [{"start": 4, "end": 12, "fact_id": "S1"}]}},
           "guard_log": {"attempts": [], "dropped": ["câu sai"]}, "created_at": None}
    user = context(row, admin=False)
    assert user["dropped"] == [] and user["plan_label"] == "quý 3/2026"
    assert user["sections"][0]["sentences"][0] == 'Đạt <a class="num" href="#S1">7.943 tỷ</a>.'
    assert user["facts"][0]["links"] == [("trang 4", "/tai-lieu/9/trang/4.png")]
    assert context(row, admin=True)["dropped"] == ["câu sai"]
    assert context(row, admin=False, absolute=True)["facts"][0]["links"][0][1].startswith("http")


def test_ratio_growth_chart_uses_percentage_points():
    s = svg({"type": "bars", "title": "ROE", "unit": "điểm %", "items": [["TCB", 1.25], ["LPB", -0.3]], "highlight": []})
    assert "1,3 điểm %" in s or "1,2 điểm %" in s
    assert "−0,3 điểm %" in s
