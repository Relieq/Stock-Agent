"""Nguyên nhân từ công văn giải trình đưa vào bảng số (không cần CSDL, không gọi mô hình)."""

from types import SimpleNamespace

from services.analyst import tools
from services.analyst.explanations import Check
from services.analyst.guard import numbers
from services.analyst.plan import Plan
from services.analyst.sheet import FactSheet


def test_words_only_removes_every_number():
    t = tools.words_only("Thu nhập lãi thuần tăng 15,2% nhờ tín dụng tăng 1.200 tỷ đồng, gấp đôi cùng kỳ")
    assert numbers(t) == []
    assert "tăng … nhờ tín dụng tăng …" in t and "…" in t


def test_unchecked_reason_keeps_only_words():
    for verdict in ("không kiểm được", "khớp chiều"):
        line = tools.reason_line("TCB", Check("Chi phí dự phòng giảm 38,8% còn 917 tỷ", verdict))
        assert numbers(line) == [], verdict
        assert "Chi phí dự phòng giảm" in line
    line = tools.reason_line("TCB", Check("Chi phí dự phòng giảm 38,8% còn 917 tỷ", "khớp"))
    assert "38,8%" in line and "917 tỷ" in line          # đã đối chiếu khớp BCTC: giữ nguyên số
    assert tools.reason_line("TCB", Check("Chi phí dự phòng giảm 50%", "lệch")) is None


class _Conn:
    def execute(self, sql, params=None):
        return SimpleNamespace(fetchone=lambda: (77, "Q3"))


def test_reasons_strip_numbers_of_unchecked_causes(monkeypatch):
    monkeypatch.setattr(tools, "load_letter", lambda conn, client, doc_id, cache_dir=None: {"sections": [
        {"scope": "consolidated", "period_kind": "quarter"}]})
    monkeypatch.setattr(tools, "facts_for", lambda *a: None)
    monkeypatch.setattr(tools, "check_section", lambda sec, facts: SimpleNamespace(checks=[
        Check("lợi nhuận kỳ này", "khớp"),
        Check("Thu nhập lãi thuần tăng 17,9%", "khớp"),
        Check("Tín dụng tăng trưởng 12% so với đầu năm", "không kiểm được"),
        Check("Chi phí hoạt động giảm 300 tỷ", "khớp chiều"),
        Check("Thu nhập khác tăng 900 tỷ", "lệch")]))
    sheet = FactSheet()
    out = tools.reasons(_Conn(), None, Plan("yoy", ["TCB"], 2026, "Q3", "quarter"), sheet, "TCB")
    texts = [f.text for f in out]
    assert len(texts) == 3
    assert "17,9%" in texts[0]
    assert numbers(texts[1]) == [] and "Tín dụng tăng trưởng" in texts[1] and "theo công ty" in texts[1]
    assert numbers(texts[2]) == [] and "Chi phí hoạt động giảm" in texts[2]
