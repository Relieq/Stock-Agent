"""Hiểu yêu cầu: mô hình đổi câu hỏi gõ tự nhiên thành kế hoạch theo khuôn; code kiểm từng trường (mã có thật, kỳ hợp lệ, điền
kỳ gần nhất) và quyết định có phải hỏi lại người dùng không (Baocao/dinh-huong/agent-bao-cao.md mục 4)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Callable

from services.analyst.catalog import ALL_KEYS
from services.analyst.trend import DEFAULT_QUARTERS, MAX_QUARTERS

KINDS = ("compare", "yoy", "rank", "screen", "trend")
SECTORS = ("all", "TCTD", "corporate", "CTCK")
MEASURES = ("growth", "level")
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
        "sector": {"type": "string", "enum": list(SECTORS)},
        "measure": {"type": "string", "enum": list(MEASURES)},
        "quarters": {"type": "integer"},
    },
    "required": ["kind", "tickers", "year", "period", "basis", "metrics", "unclear", "advice_request", "sector",
                 "measure", "quarters"],
    "additionalProperties": False,
}

PROMPT = """Bạn là bộ phận hiểu yêu cầu của Soi, dịch vụ thông tin về kết quả kinh doanh của doanh nghiệp niêm yết Việt
Nam. Hôm nay là {today}. Đổi câu hỏi dưới đây thành kế hoạch theo khuôn JSON. Không trả lời câu hỏi, không tính toán.

- kind: compare nếu người dùng muốn so từ hai mã trở lên với nhau trong cùng kỳ; yoy nếu hỏi về một mã (kể cả khi xin
  lời khuyên mua bán); rank nếu muốn biết một mã đứng đâu trong nhóm/ngành ("đứng thứ mấy", "so với các ngân hàng
  khác", "so với trung bình ngành"); screen nếu hỏi công ty/mã nào tốt nhất, đứng đầu, top mấy mà không nêu mã cụ thể
  nào ("công ty nào có KQKD tốt nhất", "top 5 ngân hàng lãi nhiều nhất", "mã nào tăng trưởng mạnh nhất"); trend nếu
  hỏi diễn biến qua nhiều quý của một hay nhiều mã ("xu hướng", "qua các quý", "4 quý gần nhất", "từng quý", "từ quý
  4/2025 đến quý 2/2026", "có tăng liên tiếp không"). "Quý gần nhất" (một quý) không phải trend. Câu hỏi
  chung chung không nêu công ty và không hỏi mã nào hơn ("kết quả kinh doanh thế nào?") thì là yoy với tickers rỗng.
- tickers: mã chứng khoán 3 ký tự người dùng nhắc, viết hoa. Người dùng có thể gọi bằng tên công ty (ví dụ
  "Techcombank" là TCB, "Vietcombank" là VCB, "Hòa Phát" là HPG, "Novaland" là NVL). Mã hoặc công ty ngoài danh sách
  đang theo dõi vẫn ghi ra (hệ thống sẽ tự tìm và kiểm mã có tồn tại không); chỉ ghi vào unclear khi không đoán được mã.
  Không tự thêm mã người dùng không nhắc; không có mã nào thì để mảng rỗng. Các mã đang theo dõi: {companies}.
- year, period: kỳ người dùng hỏi. period là Q1..Q4 (quý), H1 (6 tháng đầu năm, nửa đầu năm, bán niên), FY (cả năm,
  "năm 2025"). "9 tháng" là Q3 lũy kế. "quý gần nhất", "quý vừa rồi", "mới nhất" hoặc không nói kỳ thì period = latest
  và year = 0. Nói quý mà không nói năm thì year = {year}.
- quarters: loại trend: số quý người dùng nói ("4 quý gần nhất" là 4; "từ quý 4/2025 đến quý 2/2026" là 3, khi đó
  year, period là quý cuối); không nói số quý thì 0. Loại khác: 0.
- basis: ytd nếu hỏi lũy kế ("9 tháng", "từ đầu năm", "6 tháng", "cả năm"); còn lại quarter.
- metrics: chỉ tiêu người dùng nhắc cụ thể, chọn trong: {metrics}. Không nhắc thì để rỗng. "lợi nhuận", "lãi", "LNST"
  là npat_parent; "lợi nhuận trước thuế" là pbt; "doanh thu" là revenue (ngân hàng: toi); "thu nhập lãi" là nii;
  "dự phòng" là provision; "biên gộp", "biên lợi nhuận gộp" là gross_margin; "chi phí hoạt động" là opex; "ROE",
  "lợi nhuận trên vốn chủ sở hữu" là roe; "NIM", "biên lãi thuần" là nim.
- unclear: điều bạn không chắc (ví dụ tên công ty không đoán được mã), mỗi ý một câu ngắn; không có thì để rỗng.
- advice_request: true nếu câu hỏi xin lời khuyên mua/bán/nắm giữ, giá mục tiêu, có nên đầu tư.
- sector: nhóm công ty người dùng nói tới: TCTD (ngân hàng), CTCK (công ty chứng khoán), corporate (nhóm phi tài chính
  có nêu rõ: "doanh nghiệp sản xuất", "bán lẻ", "bất động sản", "trừ ngân hàng"); nói chung chung "công ty", "doanh
  nghiệp", "mã", "cổ phiếu" hoặc không nói nhóm thì all.
- measure: level nếu xếp theo độ lớn ("lãi nhiều nhất", "doanh thu lớn nhất", "lợi nhuận cao nhất"); growth nếu xếp theo
  mức tăng so với cùng kỳ ("tăng mạnh nhất", "tăng trưởng tốt nhất"), nói "tốt nhất", "làm ăn tốt nhất" hoặc không nói.

Câu hỏi: {question}"""


def trend_label(year: int, period: str, quarters: int) -> str:
    n = quarters or DEFAULT_QUARTERS
    return f"{n} quý đến quý {period[1]}/{year}"


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
    sector: str = "all"                 # loại screen: nhóm được xếp (all = xếp riêng từng nhóm)
    measure: str = "growth"             # loại screen: xếp theo tăng trưởng so với cùng kỳ hay theo độ lớn
    quarters: int = 0                   # loại trend: số quý người dùng nói (0 = không nói: 4 quý gần nhất)

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> "Plan":
        return cls(**d)

    def label(self) -> str:
        if self.kind == "trend":
            return trend_label(self.year, self.period, self.quarters)
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


ASK_TICKER = """Bạn muốn xem mã chứng khoán nào? Soi trả lời được năm loại câu hỏi về KQKD:
- so sánh nhiều mã cùng kỳ, ví dụ "so sánh KQKD quý 2/2026 của VCB và TCB";
- một mã so với cùng kỳ năm trước, ví dụ "FPT quý 2/2026 làm ăn thế nào so với cùng kỳ";
- vị trí của một mã trong nhóm, ví dụ "LNST quý 2/2026 của MBB đứng thứ mấy trong các ngân hàng";
- mã nào tốt nhất trong các mã đang theo dõi, ví dụ "ngân hàng nào có lợi nhuận quý 2/2026 tăng mạnh nhất";
- xu hướng nhiều quý của một hay nhiều mã, ví dụ "LNST của TCB 4 quý gần nhất"."""


def check_plan(plan: Plan, known: set[str], exists: Callable[[str], bool],
               latest: Callable[[list[str]], tuple[int, str] | None], year_now: int | None = None,
               latest_all: Callable[[str], tuple[int, str] | None] | None = None) -> Checked:
    """`known`: mã đã có trong bảng công ty; `exists(mã)`: tìm trên Vietstock cho mã ngoài danh sách; `latest(mã)`: kỳ
    quý gần nhất đã có BCTC kiểm chứng của mọi mã; `year_now`: năm dùng khi kỳ có nêu mà thiếu năm; `latest_all(nhóm)`:
    quý gần nhất mà phần lớn các mã đang theo dõi của nhóm đã có BCTC kiểm chứng (loại screen)."""
    notes: list[str] = []
    tickers: list[str] = []
    for t in plan.tickers:
        t = t.strip().upper()
        if t and t not in tickers:
            tickers.append(t)
    kind = plan.kind
    sector = plan.sector if plan.sector in SECTORS else "all"
    measure = plan.measure if plan.measure in MEASURES else "growth"
    if kind == "screen" and tickers:        # đã nêu mã: xếp các mã đó với nhau, hoặc vị trí của một mã trong nhóm
        kind = "rank" if len(tickers) == 1 else "compare"
        notes.append("Bạn đã nêu mã nên báo cáo " + ("xem vị trí của mã này trong nhóm." if kind == "rank"
                                                      else "so các mã này với nhau."))
    if not tickers and kind != "screen":
        return Checked(None, ASK_TICKER)
    bad = [t for t in tickers if not TICKER_RE.match(t) or (t not in known and not exists(t))]
    if bad:
        return Checked(None, f"Không tìm thấy mã {', '.join(bad)}. Bạn kiểm tra lại mã giúp (mã gồm 3 ký tự, ví dụ FPT).")
    quarters = plan.quarters if isinstance(plan.quarters, int) and plan.quarters > 0 else 0
    if kind == "trend":
        if quarters == 1:
            quarters = 2
            notes.append("Xu hướng cần ít nhất 2 quý: dùng 2 quý.")
        elif quarters > MAX_QUARTERS:
            quarters = MAX_QUARTERS
            notes.append(f"Xu hướng tối đa {MAX_QUARTERS} quý: dùng {MAX_QUARTERS} quý gần nhất.")
    else:
        quarters = 0
    if kind == "compare" and len(tickers) == 1:
        kind = "yoy"
        notes.append("Chỉ có một mã nên báo cáo so với cùng kỳ năm trước.")
    elif kind == "yoy" and len(tickers) > 1:
        kind = "compare"
        notes.append("Có nhiều mã nên báo cáo so các mã với nhau, kèm thay đổi so với cùng kỳ.")
    year, period, basis = plan.year, plan.period, plan.basis
    filled_latest = period == "latest"
    if filled_latest:
        found = latest_all(sector) if kind == "screen" and latest_all else latest(tickers) if tickers else None
        if found is None:
            return Checked(None, "Chưa có BCTC nào của các mã này trong kho. Bạn ghi rõ kỳ (ví dụ quý 2/2026) để hệ "
                                 "thống đi lấy.")
        year, period = found
    elif not year:
        year = year_now if year_now is not None else date.today().year
        notes.append(f"Bạn không nói năm: dùng năm {year}.")
    if kind == "trend":         # xu hướng tính theo số riêng từng quý, kết thúc ở quý cuối của kỳ hỏi
        if period in ("H1", "FY"):
            period = "Q2" if period == "H1" else "Q4"
            notes.append(f"Xu hướng tính theo từng quý: kết thúc ở quý {period[1]}/{year}.")
        if basis == "ytd":
            notes.append("Xu hướng tính theo số riêng từng quý, không theo lũy kế.")
        basis = "quarter"
        if not quarters:
            notes.append(f"Bạn không nói số quý: dùng {DEFAULT_QUARTERS} quý gần nhất.")
    if period in ("H1", "FY"):
        basis = "ytd"
    if period == "Q1":
        basis = "quarter"
    if filled_latest:
        notes.append("Bạn không nói kỳ: dùng kỳ gần nhất " + ("mà phần lớn các mã đang theo dõi đã có số" if kind == "screen"
                     else "đã có số của mọi mã") + f" ({label(year, period, basis)}).")
    if kind == "trend" and period not in ("Q1", "Q2", "Q3", "Q4"):
        return Checked(None, "Bạn muốn xem xu hướng đến quý nào? Ví dụ \"LNST của TCB 4 quý đến quý 2/2026\".")
    if plan.advice_request:
        notes.append("Soi chỉ cung cấp thông tin từ BCTC, không đưa khuyến nghị mua bán.")
    metrics = [m for m in plan.metrics if m in ALL_KEYS]
    if kind != "screen":                # nhóm và tiêu chí xếp chỉ dùng cho loại screen
        sector, measure = "all", "growth"
    return Checked(Plan(kind, tickers, year, period, basis, metrics, plan.unclear, plan.advice_request, sector, measure,
                        quarters), None, notes)
