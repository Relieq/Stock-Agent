"""Bộ kiểm tra số trong văn bản do mô hình viết (không gọi mô hình).

Với từng câu: mọi con số phải khớp một số trong các dòng bảng số câu đó ghi (sai số theo chữ số cuối như in và 0,1% giá
trị; "khoảng/gần" lệch tối đa 5%; "hơn/trên" thì số thật lớn hơn, "dưới" thì nhỏ hơn); từ chỉ chiều và so sánh phải khớp
số liệu; không có ngôn ngữ khuyến nghị đầu tư; không nhắc mã ngoài kế hoạch và ngoài các dòng câu ghi.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from services.analyst.sheet import Fact, FactSheet

MONEY = (("nghìn tỷ", Decimal(10) ** 12), ("ngàn tỷ", Decimal(10) ** 12), ("tỷ", Decimal(10) ** 9),
         ("triệu", Decimal(10) ** 6), ("đồng", Decimal(1)))
_UNIT = r"(nghìn tỷ|ngàn tỷ|tỷ|triệu|đồng|điểm phần trăm|điểm %|%|phần trăm|lần)"
# Sau đơn vị phải hết từ: "tỷ lệ", "đồng thời" là từ khác, không phải đơn vị tiền
_UNIT_END = r"(?!\w)(?!\s+(?:lệ|thời|ý)(?!\w))"
NUMBER = re.compile(r"(?<![\w.,])([-−+]?)(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)(?!\w)(?:\s*" + _UNIT
                    + _UNIT_END + r")?")
WORD_TIMES = {"gấp đôi": 2, "gấp ba": 3}
# Kỳ, năm, ngày tháng, tên chỉ số: không phải số liệu
# Năm đứng một mình được bỏ qua, trừ khi theo sau là đơn vị ("đạt 2000 tỷ" là số liệu, không phải năm)
IGNORE = re.compile(r"(?i)\b(?:quý|Q)\s*[1-4]\b(?:\s*[/-]\s*\d{4})?|\b(?:năm|nam)\s+\d{4}|\b\d{1,2}/(?:19|20)\d{2}\b"
                    r"|\b(?:19|20)\d{2}\b(?!\s*(?:tỷ|triệu|đồng|%|lần|điểm|nghìn|ngàn)" + _UNIT_END + r")"
                    r"|\b\d{1,2}\s*tháng|\bVN\d+\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?(?!\d)|\bH[12]\b")
APPROX = re.compile(r"(khoảng|gần|xấp xỉ|ước|chừng)\s*$")
MORE = re.compile(r"(hơn|trên|vượt)\s*$")
LESS = re.compile(r"(dưới|chưa đến|chưa tới|không tới)\s*$")
# Dạng động từ ("nên mua", "có thể cân nhắc bán") luôn bị bắt; "có thể" chỉ tính khi đi với "cân nhắc" hoặc "nên",
# để câu phân tích như "có thể giữ được đà tăng" không bị coi là khuyến nghị; "khuyến nghị" (danh từ) có thể được phủ định
ADVICE = re.compile(r"(?i)(nên|khuyên|có thể\s+(?:cân nhắc|nên))\s+(?:\S+\s+){0,2}?"
                    r"(mua|bán|nắm giữ|giữ|tích lũy|chốt lời|cắt lỗ|đầu tư)\b"
                    r"|giá mục tiêu"
                    r"|cơ hội (đầu tư|mua)|định giá (hấp dẫn|rẻ)|thời điểm (tốt để )?(mua|bán)|khuyến nghị")
NEGATED = re.compile(r"(?i)không\s+(?:\S+\s+){0,2}$")
TICKER = re.compile(r"\b[A-Z]{3}\b")

KINDS = {
    "unsourced_number": "số không có trong các dòng câu đã ghi",
    "no_source": "câu có số nhưng không ghi dòng số nào",
    "unknown_fact": "câu ghi mã dòng không có trong bảng số",
    "advice": "ngôn ngữ khuyến nghị đầu tư",
    "foreign_ticker": "nhắc mã ngoài kế hoạch và ngoài các dòng câu ghi",
    "direction": "từ tăng/giảm ngược với số liệu",
    "comparison": "so sánh (cao hơn/thấp hơn, cao nhất/thấp nhất) ngược với số liệu hoặc không có dòng so sánh",
}


@dataclass
class Num:
    value: Decimal      # tiền: đồng; loại khác: như in
    kind: str           # money, pct, pp, times, plain
    decimals: int       # số chữ số sau dấu phẩy như in
    scale: Decimal      # đơn vị tiền như in (10^9 với "tỷ"); loại khác: 1
    start: int = 0
    end: int = 0
    qualifier: str = ""  # approx / more / less


@dataclass
class Violation:
    section: int
    sentence: int
    kind: str
    detail: str


@dataclass
class Link:
    start: int          # vị trí con số trong câu
    end: int
    fact_id: str


@dataclass
class SentenceCheck:
    violations: list[Violation] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _kind(unit: str | None) -> tuple[str, Decimal]:
    if not unit:
        return "plain", Decimal(1)
    u = unit.lower()
    for name, mult in MONEY:
        if u == name:
            return "money", mult
    if u.startswith("điểm"):
        return "pp", Decimal(1)
    if u in ("%", "phần trăm"):
        return "pct", Decimal(1)
    return "times", Decimal(1)


def _masked(text: str) -> str:
    """Thay kỳ, năm, ngày tháng bằng khoảng trắng cùng độ dài để vị trí các số còn lại không đổi."""
    return IGNORE.sub(lambda m: " " * len(m.group(0)), text)


def numbers(text: str) -> list[Num]:
    masked = _masked(text)
    out: list[Num] = []
    for m in NUMBER.finditer(masked):
        sign, digits, unit = m.group(1), m.group(2), m.group(3)
        value = Decimal(digits.replace(".", "").replace(",", "."))
        decimals = len(digits.split(",")[1]) if "," in digits else 0
        kind, scale = _kind(unit)
        if sign in ("-", "−"):
            value = -value
        before = masked[max(0, m.start() - 14):m.start()].lower()
        q = "approx" if APPROX.search(before) else "more" if MORE.search(before) else "less" if LESS.search(before) else ""
        out.append(Num(value * scale, kind, decimals, scale, m.start(), m.end(), q))
    low = masked.lower()
    for word, k in WORD_TIMES.items():
        for m in re.finditer(word, low):
            out.append(Num(Decimal(k), "times", 0, Decimal(1), m.start(), m.end()))
    return sorted(out, key=lambda n: n.start)


def matches(n: Num, f: Num) -> bool:
    """Số `n` trong câu có khớp số `f` của bảng số không (so độ lớn; chiều tăng/giảm kiểm riêng)."""
    if n.kind != f.kind:
        return False
    v, fv = abs(n.value), abs(f.value)
    half = Decimal(5) * Decimal(10) ** -(n.decimals + 1) * n.scale
    tol = max(half * Decimal("1.01"), fv * Decimal("0.001"))
    if n.qualifier == "approx":
        tol = max(tol, fv * Decimal("0.05"))
    if n.qualifier == "more":
        return v - tol <= fv <= v * Decimal("1.25") + tol
    if n.qualifier == "less":
        return v * Decimal("0.75") - tol <= fv <= v + tol
    return abs(v - fv) <= tol


def check_sentence(text: str, uses: list[str], sheet: FactSheet, allowed: set[str], known: set[str],
                   sec: int = 0, idx: int = 0) -> SentenceCheck:
    out = SentenceCheck()

    def bad(kind: str, detail: str) -> None:
        out.violations.append(Violation(sec, idx, kind, detail))

    facts: list[Fact] = []
    for fid in uses:
        f = sheet.get(fid)
        if f is None:
            bad("unknown_fact", fid)
        else:
            facts.append(f)
    allowed_nums = [(f, n) for f in facts for n in numbers(f.text)]
    found = numbers(text)
    if found and not facts:
        bad("no_source", text.strip())
    else:
        for n in found:
            hit = next((f for f, fn in allowed_nums if matches(n, fn)), None)
            if hit is None:
                bad("unsourced_number", text[n.start:n.end].strip())
            else:
                out.links.append(Link(n.start, n.end, hit.id))
    for m in ADVICE.finditer(text):
        if m.group(0).lower() == "khuyến nghị" and _negated(text, m.start()):
            continue
        bad("advice", m.group(0))
    fact_text = " ".join(f.text for f in facts)
    for t in sorted(set(TICKER.findall(text)) & known):
        if t not in allowed and t not in fact_text:
            bad("foreign_ticker", t)
    _check_directions(text, facts, out, bad)
    return out


def _negated(text: str, start: int) -> bool:
    """Phủ định đứng ngay trước cụm (không phải/không đưa/không có) và cùng mệnh đề (không có dấu phẩy, chấm phẩy)."""
    m = NEGATED.search(text[max(0, start - 25):start])
    return bool(m) and not re.search(r"[,;.]", m.group(0))


def _check_directions(text, facts, out, bad) -> None:
    """Từ chỉ chiều và so sánh (Task 2)."""
    return None


def check_draft(draft: dict, sheet: FactSheet, allowed: set[str], known: set[str]
                ) -> tuple[list[Violation], dict[str, list[Link]], list[str]]:
    """Kiểm cả bài. Liên kết số -> dòng theo khóa "mục.câu" (dùng khi dựng trang báo cáo)."""
    violations: list[Violation] = []
    links: dict[str, list[Link]] = {}
    warnings: list[str] = []
    for s, section in enumerate(draft.get("sections", [])):
        for i, sentence in enumerate(section.get("sentences", [])):
            r = check_sentence(sentence["text"], sentence.get("uses", []), sheet, allowed, known, s, i)
            violations += r.violations
            warnings += r.warnings
            links[f"{s}.{i}"] = r.links
    return violations, links, warnings
