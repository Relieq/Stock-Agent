"""Hiểu yêu cầu: mô hình đổi câu hỏi tự do thành kế hoạch theo khuôn; code kiểm từng trường (mã có thật, kỳ hợp lệ, điền
kỳ gần nhất) và quyết định có phải hỏi lại người dùng không (Baocao/dinh-huong/agent-bao-cao.md mục 4)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Callable

from services.analyst.catalog import ALL_KEYS

KINDS = ("compare", "yoy", "rank")
PERIODS = ("Q1", "Q2", "Q3", "Q4", "H1", "FY", "latest")

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": list(KINDS)},
        "tickers": {"type": "array", "items": {"type": "string"}},
        "year": {"type": "integer"},
        "period": {"type": "string", "enum": list(PERIODS)},
        "basis": {"type": "string", "enum": ["quarter", "ytd"]},
        "metrics": {"type": "array", "items": {"type": "string", "enum": ALL_KEYS}},
        "unclear": {"type": "array", "items": {"type": "string"}},
        "advice_request": {"type": "boolean"},
    },
    "required": ["kind", "tickers", "year", "period", "basis", "metrics", "unclear", "advice_request"],
    "additionalProperties": False,
}

PROMPT = """Bạn là bộ phận hiểu yêu cầu của Soi, dịch vụ thông tin về kết quả kinh doanh của doanh nghiệp niêm yết Việt
Nam. Hôm nay là {today}. Đổi câu hỏi dưới đây thành kế hoạch theo khuôn JSON. Không trả lời câu hỏi, không tính toán.

- kind: compare nếu người dùng muốn so từ hai mã trở lên với nhau trong cùng kỳ; yoy nếu hỏi về một mã (kể cả khi xin
  lời khuyên mua bán); rank nếu muốn biết một mã đứng đâu trong nhóm/ngành ("đứng thứ mấy", "so với các ngân hàng
  khác", "so với trung bình ngành").
- tickers: mã chứng khoán 3 ký tự người dùng nhắc, viết hoa. Người dùng có thể gọi bằng tên công ty (ví dụ
  "Techcombank" là TCB, "Vietcombank" là VCB, "Hòa Phát" là HPG, "Novaland" là NVL). Mã hoặc công ty ngoài danh sách
  đang theo dõi vẫn ghi ra (hệ thống sẽ tự tìm và kiểm mã có tồn tại không); chỉ ghi vào unclear khi không đoán được mã.
  Không tự thêm mã người dùng không nhắc; không có mã nào thì để mảng rỗng. Các mã đang theo dõi: {companies}.
- year, period: kỳ người dùng hỏi. period là Q1..Q4 (quý), H1 (6 tháng đầu năm, nửa đầu năm, bán niên), FY (cả năm,
  "năm 2025"). "9 tháng" là Q3 lũy kế. "quý gần nhất", "quý vừa rồi", "mới nhất" hoặc không nói kỳ thì period = latest
  và year = 0. Nói quý mà không nói năm thì year = {year}.
- basis: ytd nếu hỏi lũy kế ("9 tháng", "từ đầu năm", "6 tháng", "cả năm"); còn lại quarter.
- metrics: chỉ tiêu người dùng nhắc cụ thể, chọn trong: {metrics}. Không nhắc thì để rỗng. "lợi nhuận", "lãi", "LNST"
  là npat_parent; "lợi nhuận trước thuế" là pbt; "doanh thu" là revenue (ngân hàng: toi); "thu nhập lãi" là nii;
  "dự phòng" là provision; "biên gộp" là gross_margin; "chi phí hoạt động" là opex.
- unclear: điều bạn không chắc (ví dụ tên công ty không đoán được mã), mỗi ý một câu ngắn; không có thì để rỗng.
- advice_request: true nếu câu hỏi xin lời khuyên mua/bán/nắm giữ, giá mục tiêu, có nên đầu tư.

Câu hỏi: {question}"""


def label(year: int, period: str, basis: str) -> str:
    if period == "H1":
        return f"6 tháng đầu năm {year}"
    if period == "FY":
        return f"năm {year}"
    q = int(period[1])
    if basis == "ytd" and q > 1:
        return f"lũy kế {3 * q} tháng năm {year}"
    return f"quý {q}/{year}"


@dataclass
class Plan:
    kind: str
    tickers: list[str]
    year: int
    period: str
    basis: str
    metrics: list[str] = field(default_factory=list)
    unclear: list[str] = field(default_factory=list)
    advice_request: bool = False

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> "Plan":
        return cls(**d)

    def label(self) -> str:
        return label(self.year, self.period, self.basis)


def parse_request(client, question: str, today: date, companies: list[tuple[str, str]]) -> Plan:
    prompt = PROMPT.format(today=today.strftime("%d/%m/%Y"), year=today.year, metrics=", ".join(ALL_KEYS),
                           companies=", ".join(f"{t} ({n})" for t, n in companies), question=question.strip()[:1000])
    return Plan(**client.json_from_images(prompt, [], PLAN_SCHEMA, "plan_request"))


@dataclass
class Checked:
    plan: Plan | None
    ask: str | None = None                            # hỏi lại người dùng khi thiếu thông tin cốt lõi
    notes: list[str] = field(default_factory=list)    # điều code đã tự điền/sửa, hiện trên báo cáo


TICKER_RE = re.compile(r"^[A-Z0-9]{3}$")


def check_plan(plan: Plan, known: set[str], exists: Callable[[str], bool],
               latest: Callable[[list[str]], tuple[int, str] | None], year_now: int | None = None) -> Checked:
    """`known`: mã đã có trong bảng công ty; `exists(mã)`: tìm trên Vietstock cho mã ngoài danh sách; `latest(mã)`: kỳ
    quý gần nhất đã có BCTC kiểm chứng của mọi mã; `year_now`: năm dùng khi kỳ có nêu mà thiếu năm."""
    notes: list[str] = []
    tickers: list[str] = []
    for t in plan.tickers:
        t = t.strip().upper()
        if t and t not in tickers:
            tickers.append(t)
    if not tickers:
        return Checked(None, 'Bạn muốn xem mã chứng khoán nào? Ví dụ: "so sánh KQKD quý 3/2026 của VCB và TCB".')
    bad = [t for t in tickers if not TICKER_RE.match(t) or (t not in known and not exists(t))]
    if bad:
        return Checked(None, f"Không tìm thấy mã {', '.join(bad)}. Bạn kiểm tra lại mã giúp (mã gồm 3 ký tự, ví dụ FPT).")
    kind = plan.kind
    if kind == "compare" and len(tickers) == 1:
        kind = "yoy"
        notes.append("Chỉ có một mã nên báo cáo so với cùng kỳ năm trước.")
    elif kind == "yoy" and len(tickers) > 1:
        kind = "compare"
        notes.append("Có nhiều mã nên báo cáo so các mã với nhau, kèm thay đổi so với cùng kỳ.")
    year, period, basis = plan.year, plan.period, plan.basis
    filled_latest = period == "latest"
    if filled_latest:
        found = latest(tickers)
        if found is None:
            return Checked(None, "Chưa có BCTC nào của các mã này trong kho. Bạn ghi rõ kỳ (ví dụ quý 2/2026) để hệ "
                                 "thống đi lấy.")
        year, period = found
    elif not year:
        year = year_now if year_now is not None else date.today().year
        notes.append(f"Bạn không nói năm: dùng năm {year}.")
    if period in ("H1", "FY"):
        basis = "ytd"
    if period == "Q1":
        basis = "quarter"
    if filled_latest:
        notes.append(f"Bạn không nói kỳ: dùng kỳ gần nhất đã có số của mọi mã ({label(year, period, basis)}).")
    if plan.advice_request:
        notes.append("Soi chỉ cung cấp thông tin từ BCTC, không đưa khuyến nghị mua bán.")
    metrics = [m for m in plan.metrics if m in ALL_KEYS]
    return Checked(Plan(kind, tickers, year, period, basis, metrics, plan.unclear, plan.advice_request), None, notes)
