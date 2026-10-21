"""Bảng số của một báo cáo: mỗi dòng (S1, S2, ...) là một sự kiện do code tính từ số đã kiểm chứng, kèm nguồn.

Mô hình viết lời chỉ được dùng số có trong các dòng này; bộ kiểm tra số (guard.py) so lại từng câu với đúng các dòng câu
đó ghi. Văn bản của dòng chứa sẵn mọi con số được phép nói (kỳ này, cùng kỳ, % thay đổi, chênh lệch...), nên bộ kiểm tra
lấy số được phép bằng chính cách đọc số trong câu.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Fact:
    id: str
    kind: str                     # metric, ratio, compare, rank, flag, reason
    text: str                     # câu đưa cho mô hình, chứa mọi con số được phép nói
    ticker: str | None = None
    metric: str | None = None
    direction: str | None = None  # up / down / flat: thay đổi so với cùng kỳ (chi phí tính theo độ lớn)
    measure: str | None = None    # dòng so sánh: growth (tốc độ thay đổi) hoặc level (quy mô)
    order: list[str] = field(default_factory=list)     # dòng so sánh: mã xếp từ lớn đến nhỏ
    names: list[str] = field(default_factory=list)     # tên chỉ tiêu viết thường, để nhận ra câu nói về dòng nào
    sources: list[dict] = field(default_factory=list)  # {document_id, page, label, raw, column}


@dataclass
class FactSheet:
    facts: list[Fact] = field(default_factory=list)

    def add(self, kind: str, text: str, **kw) -> Fact:
        fact = Fact(f"S{len(self.facts) + 1}", kind, text, **kw)
        self.facts.append(fact)
        return fact

    def get(self, fact_id: str) -> Fact | None:
        return next((f for f in self.facts if f.id == fact_id), None)

    def prompt_text(self) -> str:
        return "\n".join(f"{f.id}: {f.text}" for f in self.facts)

    def to_json(self) -> list[dict]:
        return [asdict(f) for f in self.facts]

    @classmethod
    def from_json(cls, rows: list[dict]) -> "FactSheet":
        return cls([Fact(**r) for r in rows])


def report_tickers(plan, sheet: FactSheet) -> set[str]:
    """Mã báo cáo được nói tới và được xin thêm số: mã của kế hoạch; câu hỏi "mã nào tốt nhất" (không nêu mã) thì các mã
    đứng đầu đã có dòng chỉ tiêu trong bảng số."""
    if plan.kind == "screen":
        return {f.ticker for f in sheet.facts if f.kind in ("metric", "ratio") and f.ticker}
    return set(plan.tickers)
