"""Viết lời báo cáo từ bảng số (Baocao/dinh-huong/agent-bao-cao.md mục 7): mô hình chọn ý và viết câu, mỗi câu ghi các
dòng số nó dùng; được xin thêm số hoặc nguyên nhân. Câu sai sau khi kiểm (guard.py) được gửi lại để viết lại, vẫn sai thì
bỏ."""

from __future__ import annotations

import copy

from services.analyst.catalog import ALL_KEYS
from services.analyst.guard import KINDS, Violation
from services.analyst.plan import Plan
from services.analyst.sheet import FactSheet

WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "heading": {"type": "string"},
                "sentences": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}, "uses": {"type": "array", "items": {"type": "string"}}},
                    "required": ["text", "uses"], "additionalProperties": False}},
            },
            "required": ["heading", "sentences"], "additionalProperties": False}},
        "need": {"type": "array", "items": {
            "type": "object",
            "properties": {"tool": {"type": "string", "enum": ["metric", "reasons"]}, "ticker": {"type": "string"},
                           "metric": {"type": "string"}},
            "required": ["tool", "ticker", "metric"], "additionalProperties": False}},
    },
    "required": ["sections", "need"],
    "additionalProperties": False,
}

PROMPT = """Bạn viết báo cáo ngắn về kết quả kinh doanh cho Soi, dịch vụ thông tin từ BCTC (không phải tư vấn đầu tư).

Yêu cầu của người dùng: {question}
Kế hoạch: {plan}

Bảng số (mọi con số đã được tính sẵn từ BCTC đã kiểm chứng; mỗi dòng có mã S...):
{sheet}

Cách viết:
- Viết 2 đến 4 mục, mỗi mục có tiêu đề ngắn và 2 đến 6 câu. Mục đầu trả lời thẳng câu hỏi.
- Mỗi câu ghi trong "uses" mã các dòng bảng số mà câu dùng, đúng mã như trong bảng số, ví dụ "uses": ["S12", "S31"].
  Câu không có số vẫn ghi dòng nó dựa vào.
- Câu so sánh giữa hai mã (cao hơn, thấp hơn, nhanh hơn, chậm hơn) hay câu nói cao nhất/thấp nhất phải ghi cả
  dòng so sánh hoặc xếp hạng tương ứng trong bảng số, ngoài các dòng chỉ tiêu.
- Mỗi câu phải tự đứng được vì câu trước có thể bị bỏ: không mở câu bằng "Tỷ lệ này", "Con số này", "Mức này"; nhắc lại tên
  chỉ tiêu và mã.
- Chỉ dùng con số có trong các dòng đã ghi, chép đúng như bảng (được làm tròn bớt, ví dụ 7.943 tỷ thành 7,9 nghìn tỷ). Không
  tự tính số mới (không cộng, trừ, chia, không tự tính %), không ước đoán, không dùng số ngoài bảng.
- Từ tăng/giảm, cao hơn/thấp hơn, nhanh hơn/chậm hơn, cao nhất/thấp nhất phải đúng như bảng.
- Không nêu mã chứng khoán không có trong bảng số.
- Nguyên nhân ghi "theo công ty, chưa kiểm được bằng số" thì viết rõ là theo công ty.{screen}
- Không khuyến nghị mua, bán, nắm giữ; không nói về giá cổ phiếu, định giá hay triển vọng.{advice}
- Tiếng Việt đời thường, ngắn gọn; giữ thuật ngữ BCTC (LNST, LNTT, BCTC...). Không nhắc mã dòng (S1...) trong câu.
- need: xin thêm số khi thật cần để trả lời tốt hơn: tool "metric" với ticker và metric (một trong: {metrics}); tool
  "reasons" với ticker và metric "none" để lấy nguyên nhân công ty nêu trong công văn giải trình. {need_rule}
{feedback}"""


SCREEN_RULES = """
- Câu hỏi "mã nào tốt nhất": mục đầu nói rõ tiêu chí xếp hạng (dòng "Xếp hạng theo ..." của bảng số) và nêu 3 đến 5 mã
  đứng đầu mỗi nhóm kèm số. Xếp riêng từng nhóm, không so ngân hàng với doanh nghiệp hay công ty chứng khoán. "Tốt nhất"
  chỉ theo tiêu chí này, không phải đánh giá cổ phiếu.
- Mã đứng đầu có cờ cảnh báo (nền so sánh thấp, lợi nhuận đến từ ngoài hoạt động chính...) thì nói rõ để người đọc
  không hiểu nhầm. Người dùng hỏi tại sao thì xin reasons cho các mã đứng đầu và giải thích bằng số trong bảng."""


def write(client, question: str, plan: Plan, sheet: FactSheet, feedback: list[str], allow_need: bool) -> dict:
    advice = ("\n- Người dùng hỏi có nên mua/bán: mở đầu bằng một câu nói rõ Soi không đưa khuyến nghị đầu tư, rồi trình "
              "bày thông tin." if plan.advice_request else "")
    need_rule = ("Đã đủ số thì để need rỗng; khi xin thêm, sections có thể để rỗng." if allow_need
                 else "Không xin thêm nữa: need phải rỗng, viết bằng số đã có.")
    fb = ("Bản trước có các câu sai sau; viết lại cả bài, sửa đúng các câu này:\n" + "\n".join(f"- {l}" for l in feedback)
          if feedback else "")
    if plan.kind == "screen":
        what = f"xếp hạng toàn bộ các mã đang theo dõi, kỳ {plan.label()}"
    else:
        what = f"loại {plan.kind}, mã {', '.join(plan.tickers)}, kỳ {plan.label()}"
    prompt = PROMPT.format(question=question.strip()[:1000], plan=what, sheet=sheet.prompt_text(), advice=advice,
                           metrics=", ".join(ALL_KEYS), need_rule=need_rule, feedback=fb,
                           screen=SCREEN_RULES if plan.kind == "screen" else "")
    return client.json_from_images(prompt, [], WRITE_SCHEMA, "write_report")


def feedback_lines(draft: dict, violations: list[Violation]) -> list[str]:
    out = []
    for v in violations:
        text = draft["sections"][v.section]["sentences"][v.sentence]["text"]
        out.append(f'"{text}": {KINDS[v.kind]} ({v.detail})')
    return out


def drop_sentences(draft: dict, bad: set[tuple[int, int]]) -> tuple[dict, list[str]]:
    """Bỏ các câu còn sai sau khi đã viết lại; mục không còn câu nào thì bỏ cả mục."""
    final = copy.deepcopy(draft)
    dropped: list[str] = []
    sections = []
    for s, section in enumerate(final.get("sections", [])):
        keep = []
        for i, sentence in enumerate(section["sentences"]):
            (dropped.append(sentence["text"]) if (s, i) in bad else keep.append(sentence))
        if keep:
            sections.append(section | {"sentences": keep})
    final["sections"] = sections
    final["need"] = []
    return final, dropped
