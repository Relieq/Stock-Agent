from services.analyst.guard import Violation
from services.analyst.plan import Plan
from services.analyst.sheet import FactSheet
from services.analyst.writer import WRITE_SCHEMA, drop_sentences, feedback_lines, write

DRAFT = {"sections": [{"heading": "Lợi nhuận", "sentences": [{"text": "A tăng 10%.", "uses": ["S1"]},
                                                             {"text": "B giảm 5%.", "uses": ["S1"]}]},
                      {"heading": "Khác", "sentences": [{"text": "C 3 tỷ.", "uses": ["S1"]}]}], "need": []}


class FakeClient:
    def __init__(self):
        self.prompts = []

    def json_from_images(self, prompt, images, schema, schema_name, **kw):
        self.prompts.append((prompt, schema_name, schema))
        return DRAFT


def test_prompt_carries_question_sheet_rules_and_feedback():
    sheet = FactSheet()
    sheet.add("metric", "LNST, TCB, quý 3/2026: 7.943 tỷ")
    plan = Plan("yoy", ["TCB"], 2026, "Q3", "quarter", advice_request=True)
    c = FakeClient()
    assert write(c, "TCB quý 3 thế nào?", plan, sheet, ["\"A\": lỗi"], allow_need=False) == DRAFT
    prompt, step, schema = c.prompts[0]
    assert step == "write_report" and schema is WRITE_SCHEMA
    assert "TCB quý 3 thế nào?" in prompt and "S1: LNST, TCB, quý 3/2026: 7.943 tỷ" in prompt
    assert "\"A\": lỗi" in prompt and "need phải rỗng" in prompt and "không đưa khuyến nghị" in prompt


def test_prompt_explains_uses_comparison_rows_and_standalone_sentences():
    sheet = FactSheet()
    sheet.add("metric", "LNST, TCB, quý 3/2026: 7.943 tỷ")
    c = FakeClient()
    write(c, "TCB?", Plan("yoy", ["TCB"], 2026, "Q3", "quarter"), sheet, [], allow_need=True)
    prompt = c.prompts[0][0]
    assert '"uses": ["S12", "S31"]' in prompt
    assert "dòng so sánh hoặc xếp hạng" in prompt
    assert "không mở câu bằng" in prompt and "Tỷ lệ này" in prompt


def test_feedback_and_dropping_sentences():
    v = [Violation(0, 1, "unsourced_number", "5%")]
    assert feedback_lines(DRAFT, v) == ['"B giảm 5%.": số không có trong các dòng câu đã ghi (5%)']
    final, dropped = drop_sentences(DRAFT, {(0, 1), (1, 0)})
    assert [s["text"] for sec in final["sections"] for s in sec["sentences"]] == ["A tăng 10%."]
    assert [sec["heading"] for sec in final["sections"]] == ["Lợi nhuận"]
    assert dropped == ["B giảm 5%.", "C 3 tỷ."]
