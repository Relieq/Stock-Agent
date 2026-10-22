"""Bộ kiểm tra số trong văn bản do mô hình viết (không gọi mô hình).

Với từng câu: mọi con số phải khớp một số trong các dòng bảng số câu đó ghi (sai số theo chữ số cuối như in và 0,1% giá
trị; "khoảng/gần" lệch tối đa 5%; "hơn/trên" thì số thật lớn hơn, "dưới" thì nhỏ hơn); từ chỉ chiều và so sánh phải khớp
số liệu; không có ngôn ngữ khuyến nghị đầu tư; không nhắc mã ngoài kế hoạch và ngoài các dòng câu ghi.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from services.analyst import catalog, trend
from services.analyst.sheet import Fact, FactSheet
from services.metrics.card import vn

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
                    r"|\b\d{1,2}\s*tháng|\bVN\d+\b|(?<!thứ\s)\b\d{1,2}/\d{1,2}(?:/\d{2,4})?(?!\d)|\bH[12]\b"
                    # số quý của xu hướng ("3 quý liên tiếp", "trong 4 quý", "quý thứ 3 liên tiếp"): kiểm riêng ở
                    # _check_trends theo chuỗi số của dòng xu hướng, không như số liệu
                    r"|\b\d{1,2}\s+quý(?!\w)|\bthứ\s+\d{1,2}\s+liên\s+(?:tiếp|tục)(?!\w)")
# Thứ hạng: "thứ 2/3", "thứ 2 trong (số) 3", "đứng/xếp thứ 2"; kiểm riêng theo thứ tự của dòng xếp hạng, không như số liệu
RANK = re.compile(r"(?i)(?<!\w)(?P<verb>(?:đứng|xếp)\s+(?:hạng\s+)?)?thứ\s+(?P<n>\d{1,3})"
                  r"(?:\s*(?:/|trên|trong(?:\s+số)?)\s*(?P<m>\d{1,3})(?!\d))?(?![\w/])")
APPROX = re.compile(r"(khoảng|gần|xấp xỉ|ước|chừng)\s*$")
MORE = re.compile(r"(hơn|trên|vượt)\s*$")
LESS = re.compile(r"(dưới|chưa đến|chưa tới|không tới)\s*$")
# Dạng động từ ("nên mua", "có thể cân nhắc bán") luôn bị bắt; "có thể" chỉ tính khi đi với "cân nhắc" hoặc "nên",
# để câu phân tích như "có thể giữ được đà tăng" không bị coi là khuyến nghị; "khuyến nghị" (danh từ) có thể được phủ định
# "giữ" chỉ là khuyên khi đi với cổ phiếu/mã ("giữ cổ phiếu TCB", "giữ TCB"), không phải "giữ được đà tăng"
_KEEP = r"giữ(?=\s+(?:cổ phiếu|mã|(?-i:[A-Z]{3})(?!\w)))"
# chủ thể "cổ đông" chỉ tính khi đứng đầu vế câu hoặc sau "các/những/nhà/quý"; "thuộc về cổ đông có thể giữ..." không phải
_HOLDER = r"(?:(?:^|(?<=[,;:.])\s*)(?:các\s+|những\s+|nhà\s+|quý\s+)?|(?<!\w)(?:các|những|nhà|quý)\s+)cổ đông"
ADVICE = re.compile(r"(?i)(nên|khuyên|có thể\s+(?:cân nhắc|nên))\s+(?:\S+\s+){0,2}?"
                    r"(mua|bán|nắm giữ|" + _KEEP + r"|tích lũy|chốt lời|cắt lỗ|đầu tư)\b"
                    # "nhà đầu tư/cổ đông/bạn có thể mua...": có chủ thể là người đầu tư thì "có thể" cũng là khuyên
                    r"|(?:(?<!\w)(?:nhà đầu tư|bạn)|" + _HOLDER + r")\s+(?:(?:vẫn|cũng|hoàn toàn)\s+)?có thể\s+"
                    r"(?:\S+\s+){0,2}?(?:mua|bán|nắm giữ|" + _KEEP + r"|tích lũy|chốt lời|cắt lỗ|đầu tư|gom)\b"
                    r"|giá mục tiêu"
                    r"|cơ hội (đầu tư|mua)|định giá (hấp dẫn|rẻ)|thời điểm (tốt để )?(mua|bán)|khuyến nghị")
NEGATED = re.compile(r"(?i)không\s+(?:\S+\s+){0,2}$")
# Tên viết tắt của tỷ lệ/đơn vị (ROE, NIM, CIR...) cũng là 3 chữ in hoa nhưng không phải mã chứng khoán
NOT_TICKERS = ("ROE", "ROA", "NIM", "CIR", "EPS", "USD", "VND")
TICKER = re.compile(r"\b(?!(?:" + "|".join(NOT_TICKERS) + r")\b)[A-Z]{3}\b")

KINDS = {
    "unsourced_number": "số không có trong các dòng câu đã ghi",
    "no_source": "câu có số hoặc từ chỉ chiều nhưng không ghi dòng số nào",
    "unknown_fact": "câu ghi mã dòng không có trong bảng số",
    "advice": "ngôn ngữ khuyến nghị đầu tư",
    "foreign_ticker": "nhắc mã ngoài kế hoạch và ngoài các dòng câu ghi",
    "direction": "từ tăng/giảm ngược với số liệu",
    "comparison": "so sánh (cao hơn/thấp hơn, cao nhất/thấp nhất) ngược với số liệu hoặc không có dòng so sánh",
    "trend": "nhận định nhiều quý (tăng/giảm liên tiếp, cao nhất/thấp nhất trong các quý, so với quý trước) ngược với "
             "số liệu hoặc không ghi dòng xu hướng",
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


def ranks(text: str) -> list[re.Match]:
    """Các cụm thứ hạng: phải có "đứng/xếp" đứng trước hoặc có tổng số ("thứ 2/3"); "quý thứ 3 liên tiếp" không phải."""
    return [m for m in RANK.finditer(text) if m.group("verb") or m.group("m")]


def _masked(text: str) -> str:
    """Thay kỳ, năm, ngày tháng, thứ hạng bằng khoảng trắng cùng độ dài để vị trí các số còn lại không đổi."""
    for m in ranks(text):
        text = text[:m.start()] + " " * (m.end() - m.start()) + text[m.end():]
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
    allowed_nums = [(f, n, loss) for f in facts for n, loss in _fact_numbers(f)]
    found = numbers(text)
    if not facts and (found or (not uses and _direction_claim(text))):
        bad("no_source", text.strip())
    elif facts:
        for n in found:
            gap = GAP_BEFORE.search(text[:n.start])
            if gap and not _gap_in_facts(n, gap.group(1), facts):
                bad("unsourced_number", text[n.start:n.end].strip() + f" (số đứng ngay sau “hơn {gap.group(1)}” đọc như mức"
                    " chênh lệch giữa hai mã; bảng số không có mức chênh này)")
                continue
            side = _profit_side(text, n)
            pool = [(f, fn) for f, fn, loss in allowed_nums if side is None or loss == (side == "loss")]
            hit = next((f for f, fn in pool if matches(n, fn)), None)
            if hit is None:
                flipped = side is not None and any(matches(n, fn) for _, fn, _ in allowed_nums)
                bad("unsourced_number", text[n.start:n.end].strip()
                    + (" (số đứng sau “lãi/lỗ” ngược dấu với bảng số)" if flipped else ""))
            else:
                out.links.append(Link(n.start, n.end, hit.id))
    for m in ADVICE.finditer(text):
        if m.group(0).lower() == "khuyến nghị" and _negated(text, m.start()):
            continue
        bad("advice", m.group(0))
    fact_text = " ".join(f.text for f in facts)
    named = with_tickers(text)          # "Vietcombank" -> "VCB": kiểm mã, so sánh, thứ hạng như khi câu viết bằng mã
    for t in sorted(set(TICKER.findall(named)) & known):
        if t not in allowed and t not in fact_text:
            bad("foreign_ticker", t)
    handled = _check_trends(named, facts, out, bad, sheet)      # vế nói diễn biến nhiều quý: kiểm theo dòng xu hướng
    _check_directions(named, facts, out, bad, sheet, skip=handled)
    _check_ranks(named, facts, bad, sheet)
    for detail in _self_contradictions(text):
        bad("direction", detail)
    # nói "lỗ" mà các dòng câu ghi không có khoản lỗ nào (số âm hoặc chữ "lỗ"); câu đã bị bắt sai chiều hoặc sai dấu
    # (số tiền sau "lỗ" đã kiểm ở trên) thì không báo thêm
    if facts and _loss_claim(text) and not any(loss for _, _, loss in allowed_nums) \
            and not any("lỗ" in PROFIT_WORD.findall(f.text.lower()) for f in facts) \
            and not any(v.kind in ("direction", "unsourced_number") for v in out.violations):
        bad("direction", f"câu nói lỗ nhưng các dòng câu ghi không có khoản lỗ nào: {text.strip()}")
    # "lỗ từ công ty liên kết" mà dòng ghi "lãi từ công ty liên kết": ngược dấu của chính khoản đó
    elif facts and not any(v.kind in ("direction", "unsourced_number") for v in out.violations) \
            and (item := _flipped_item(text, facts)):
        bad("direction", f"câu nói “{item}” nhưng dòng câu ghi là lãi: {text.strip()}")
    return out


_COMPANY = re.compile(r"(?i)(?<!\w)(" + "|".join(sorted(map(re.escape, catalog.COMPANY_NAMES), key=len, reverse=True))
                      + r")(?!\w)")


def with_tickers(text: str) -> str:
    """Thay tên gọi công ty bằng mã (ngân hàng Vietcombank -> ngân hàng VCB)."""
    return _COMPANY.sub(lambda m: catalog.COMPANY_NAMES[m.group(1).lower()], text)


# "giảm từ 107 tỷ lên 757 tỷ": từ chỉ chiều ngược với chính hai số trong câu
_FROM_TO = re.compile(r"(?i)\b(tăng|giảm|sụt)\b[^.;:]{0,60}?\btừ\s+")
_TO_WORD = re.compile(r"(?i)^\s*(?:đồng\s+)?(?:lên|xuống|còn|đến|thành)\s+")


def _self_contradictions(text: str) -> list[str]:
    out = []
    for m in _FROM_TO.finditer(text):
        rest = text[m.end():m.end() + 80]
        ns = numbers(rest)
        if len(ns) < 2 or ns[0].start != 0 or not _TO_WORD.match(rest[ns[0].end:ns[1].start]) or ns[0].kind != ns[1].kind:
            continue
        a, b = abs(ns[0].value), abs(ns[1].value)
        up = m.group(1).lower() == "tăng"
        if (up and b < a) or (not up and b > a):
            out.append(f"“{m.group(1)}” nhưng số đi từ {rest[ns[0].start:ns[0].end].strip()} "
                       f"{'xuống' if b < a else 'lên'} {rest[ns[1].start:ns[1].end].strip()}: {text.strip()}")
    return out


# "VCB cao hơn CTG 11.740 tỷ": số ngay sau "hơn <mã>" là mức chênh lệch, không phải số của mã đứng sau
GAP_BEFORE = re.compile(r"hơn\s+([A-Z]{3})\s+(?:khoảng\s+|gần\s+|xấp xỉ\s+)?$")


def _gap_in_facts(n: Num, ticker: str, facts: list[Fact]) -> bool:
    """Bảng số có đúng mức chênh này ("TCB cao hơn VCB 5,2 điểm %") trong các dòng câu ghi."""
    for f in facts:
        for m in re.finditer(rf"hơn {ticker}\s+", f.text):
            got = numbers(f.text[m.end():m.end() + 40])
            if got and got[0].start == 0 and matches(n, got[0]):
                return True
    return False


# "lãi"/"lỗ" đứng riêng (không phải "Lãi/lỗ tỷ giá", không phải "lỗi")
PROFIT_WORD = re.compile(r"(?i)(?<![/\w])(lãi|lỗ)(?![/\w])")


def _profit_side(text: str, n: Num) -> str | None:
    """Số tiền đứng ngay sau "lãi" hay "lỗ" (cách tối đa 3 từ, cùng vế): "profit", "loss" hoặc None."""
    if n.kind != "money":
        return None
    word = None
    for m in PROFIT_WORD.finditer(text, 0, n.start):
        word = m
    if word is None:
        return None
    between = text[word.end():n.start]
    if re.search(r"[,;:.](?!\d)", between) or len(between.split()) > 3:
        return None
    return "loss" if word.group(1).lower() == "lỗ" else "profit"


_LOSS_OF_TICKER = re.compile(r"(?i)\s+(?:(?:quý|q)\s*[1-4](?:\s*/\s*\d{4})?\s+|năm\s+\d{4}\s+)?của\s+(?-i:[A-Z]{3})(?!\w)")
LOSS_EXIT = re.compile(r"\b(?:cắt|thoát|hết|khỏi|xóa|bù|tránh)\s+$")     # "cắt lỗ", "thoát lỗ": không nói có lỗ


def _loss_claim(text: str) -> bool:
    """Câu khẳng định chỉ tiêu bị lỗ: chữ "lỗ" đứng riêng ngay sau mã hoặc tên chỉ tiêu, không bị phủ định, không phải
    "cắt lỗ", "thoát lỗ", "bù lỗ", không phải khoản lỗ khác ("lỗ tỷ giá", "lỗ lũy kế")."""
    low = text.lower()
    for m in PROFIT_WORD.finditer(low):
        if m.group(1) != "lỗ":
            continue
        before = low[:m.start()]
        if NEGATED_VERB.search(before) or LOSS_EXIT.search(before):
            continue
        if _LOSS_OF_TICKER.match(text, m.end()):        # "lỗ quý 2/2026 của MBB": kết quả của chính mã
            return True
        if not _LOSS_OWNER.search(text[:m.start()]) or _LOSS_OTHER.match(text, m.end()):
            continue
        return True
    return False


def _flipped_item(text: str, facts: list[Fact]) -> str | None:
    """Câu gọi "lỗ X" một khoản mà dòng câu ghi gọi "lãi X" (cùng hai từ theo sau, dòng không có "lỗ X"): trả về cụm
    "lỗ X" của câu."""
    low = text.lower()
    rows = [re.sub(r"\s+", " ", f.text.lower()) for f in facts]
    for m in PROFIT_WORD.finditer(low):
        before = low[:m.start()]
        if m.group(1) != "lỗ" or NEGATED_VERB.search(before) or LOSS_EXIT.search(before):
            continue
        words = re.findall(r"\w+", low[m.end():])[:2]
        if not words:
            continue
        tail = r"\W+".join(map(re.escape, words)) + r"(?!\w)"
        if any(re.search(r"(?<![/\w])lãi(?:\W+thuần)?\W+" + tail, r) and not re.search(r"(?<![/\w])lỗ\W+" + tail, r)
               for r in rows):
            return text[m.start():m.end()] + " " + " ".join(words)
        # "lỗ gộp" mà dòng ghi "Lợi nhuận gộp, ...: 52.338 tỷ" (số dương)
        if any(re.search(r"^lợi nhuận\W+" + re.escape(words[0]) + r"(?!\w)[^:]*:\s*\d", r) for r in rows):
            return text[m.start():m.end()] + " " + words[0]
    return None


def _fact_numbers(f: Fact) -> list[tuple[Num, bool]]:
    """Số của dòng kèm cờ "là khoản lỗ": số âm, hoặc đứng sau chữ "lỗ" gần nhất trong cùng phần ("lỗ thu hẹp từ 100 tỷ
    còn 50 tỷ", "chuyển từ lãi 20 tỷ sang lỗ 30 tỷ")."""
    out = []
    for n in numbers(f.text):
        seg_start = max((m.end() for m in re.finditer(r"[;:]|\.\s", f.text[:n.start])), default=0)
        word = None
        for m in PROFIT_WORD.finditer(f.text, seg_start, n.start):
            word = m
        out.append((n, n.value < 0 or (word is not None and word.group(1).lower() == "lỗ")))
    return out


def _direction_claim(text: str) -> bool:
    """Câu có nói chiều (tăng/giảm, cao/thấp hơn cùng kỳ, lãi/lỗ): là nhận định về số liệu, phải ghi dòng số."""
    for a, b in _clauses(text):
        low = text[a:b].lower().replace("tăng trưởng âm", "giảm")
        # danh từ không nói chiều: "so sánh tăng trưởng lợi nhuận", "đánh giá lãi lỗ"
        low = GROWTH_NOUN.sub(lambda m: " " * len(m.group(0)), low)
        low = re.sub(r"lãi\s*(?:/|,|và|hay|hoặc)?\s*lỗ(?!\w)", lambda m: " " * len(m.group(0)), low)
        if bool(UP.search(low)) != bool(DOWN.search(low)):
            return True
        if LAST_YEAR.search(low) and COMP_AS_DIR.search(low):
            return True
        if re.search(r"(?<![/\w])lỗ(?![/\w])|\b(?:có|báo) lãi\b", low):
            return True
    return False


def _check_ranks(text: str, facts: list[Fact], bad, sheet: FactSheet | None) -> None:
    """Thứ hạng "thứ N/M", "thứ N trong M", "đứng thứ N": N là vị trí của mã trong thứ tự của dòng xếp hạng câu ghi, M
    là số mã của dòng đó."""
    subject: str | None = None
    for a, b in _clauses(text):
        clause = text[a:b]
        low = clause.lower()
        tickers = [(m.start(), m.group(0)) for m in TICKER.finditer(clause)]
        for r in ranks(clause):
            n, m = int(r.group("n")), int(r.group("m")) if r.group("m") else None
            before = [t for p, t in tickers if p < r.start()]
            who = before[-1] if before else tickers[0][1] if tickers else subject
            c = _cue(low)
            rows = [f for f in facts if f.order and (who is None and f.ticker in f.order or who in f.order)
                    and (c is None or f.measure == c)]
            rows = _named(rows, low)
            if not rows:
                bad("comparison", f"không có dòng xếp hạng cho {who or 'mã được nói'}: {clause.strip()}"
                                  + (_hint(sheet, [who], c, low, rank=True) if who else ""))
                continue

            def ok(f: Fact) -> bool:
                t = who or f.ticker
                return f.order.index(t) + 1 == n and (m is None or m == len(f.order))

            if not any(ok(f) for f in rows):
                f = rows[0]
                t = who or f.ticker
                bad("comparison", f"{clause.strip()} — dòng {f.id}: {t} xếp thứ {f.order.index(t) + 1} "
                                  f"trong {len(f.order)}")
        if tickers:
            subject = tickers[0][1]


def _negated(text: str, start: int) -> bool:
    """Phủ định đứng ngay trước cụm (không phải/không đưa/không có) và cùng mệnh đề (không có dấu phẩy, chấm phẩy)."""
    m = NEGATED.search(text[max(0, start - 25):start])
    return bool(m) and not re.search(r"[,;.]", m.group(0))


UP = re.compile(r"(?i)\b(tăng(?!\s+(?:cường|vốn)\b)|cải thiện|đi lên)\b")      # "tăng cường", "tăng vốn": không phải chiều
DOWN = re.compile(r"(?i)\b(giảm(?!\s+(?:trừ|giá)\b)|sụt|đi xuống)\b")           # "giảm trừ", "giảm giá": không phải chiều
COMP_UP = re.compile(r"(nhanh hơn|cao hơn|lớn hơn|nhiều hơn|mạnh hơn|sâu hơn|vượt)")
COMP_DOWN = re.compile(r"(chậm hơn|thấp hơn|nhỏ hơn|ít hơn|yếu hơn|nhẹ hơn|kém(?!\s+nhất))")
SUP_TOP = re.compile(r"(cao nhất|lớn nhất|nhanh nhất|mạnh nhất|nhiều nhất|sâu nhất|dẫn đầu|đứng đầu)")
SUP_BOTTOM = re.compile(r"(thấp nhất|nhỏ nhất|chậm nhất|yếu nhất|ít nhất|nhẹ nhất|kém nhất|đứng cuối)")
# Dấu phẩy thập phân ("23,7%") không tách vế; từ nối nhân quả/đối lập tách vế (trừ "không còn", "chưa còn")
CLAUSE = re.compile(r",(?!\d)|;|:(?!\d)|(?<!không)(?<!chưa)\s(?:nhờ|do|vì|khiến|giúp|mặc dù|dù|trong khi|còn|nhưng|song"
                    r"|tuy nhiên|đồng thời)\s")
GROWTH_WORDS = re.compile(r"\b(?:nhanh|chậm|tăng|giảm|sụt|tốc độ|điểm phần trăm)\b|%")
NEGATED_VERB = re.compile(r"\b(?:không|chưa|ngừng)\s+(?:\S+\s+)?$")      # "không tăng", "không còn giảm", "ngừng giảm"
LOSS_BEFORE = re.compile(r"(?<![/\w])lỗ(?!\w)(?:\s+[^\s/]+)?\s*$")      # "lỗ giảm", "lỗ ròng giảm"; không phải "Lãi/lỗ", "lỗi"
# "cao hơn cùng kỳ", "thấp hơn năm trước" (không có mã thứ hai): là từ chỉ chiều, không phải so sánh hai mã
LAST_YEAR = re.compile(r"cùng kỳ|năm trước")
COMP_AS_DIR = re.compile(r"\b(?:(cao|lớn|nhiều)|(thấp|nhỏ|ít)) hơn\b")


def _clauses(text: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for m in CLAUSE.finditer(text):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(text)))
    return [(a, b) for a, b in spans if text[a:b].strip()]


def _name_keys() -> dict[str, frozenset[str]]:
    """Tên chỉ tiêu (viết thường) -> các mã chỉ tiêu có tên đó, gộp mọi loại công ty: "lnst của cổ đông công ty mẹ" và
    "lnst của cổ đông ngân hàng mẹ" đều là npat_parent."""
    out: dict[str, set[str]] = {}
    for kind in catalog.METRICS:
        for key in list(catalog.METRICS[kind]) + list(catalog.RATIOS[kind]) + list(catalog.COMPUTED.get(kind, {})):
            for n in catalog.names(kind, key):
                out.setdefault(n, set()).add(key)
    return {n: frozenset(k) for n, k in out.items()}


NAME_KEYS = _name_keys()
VOCAB = frozenset(NAME_KEYS)
# "lỗ" là kết quả của chính chỉ tiêu: ngay sau mã hoặc tên chỉ tiêu, có thể qua vài trợ từ ("TCB lỗ", "LNST lỗ",
# "TCB có lỗ", "LNST của TCB vẫn lỗ")
_LOSS_OWNER = re.compile(r"(?:(?<!\w)[A-Z]{3}\)?|(?i:" + "|".join(sorted(map(re.escape, VOCAB), key=len, reverse=True))
                         + r"))\s+(?i:(?:vẫn|còn|bị|có|đã|lại|cũng|tiếp tục|chuyển sang|quay lại|báo|ghi nhận)\s+){0,3}$")
# "lỗ tỷ giá", "lỗ lũy kế", "lỗ từ...", "lỗ của công ty con": khoản lỗ khác, không phải kết quả của chỉ tiêu
_LOSS_OTHER = re.compile(r"(?i)\s+(?:tỷ giá|lũy kế|từ|của|chênh lệch|đầu tư|thanh lý|khác)(?!\w)")
# "tăng trưởng" làm danh từ: sau "so sánh/về/mức/tốc độ/đà/sự..." hoặc ngay trước "của"/tên chỉ tiêu ("tăng trưởng lợi
# nhuận"); "LNST tăng trưởng mạnh" vẫn là động từ chỉ chiều
GROWTH_NOUN = re.compile(r"(?:(?<=so sánh )|(?<=về )|(?<=mức )|(?<=tốc độ )|(?<=đà )|(?<=sự )|(?<=xét )"
                         r"|(?<=đánh giá )|(?<=phân tích )|(?<=triển vọng ))tăng trưởng(?!\w)"
                         r"|tăng trưởng(?=\s+(?:của|" + "|".join(sorted(map(re.escape, VOCAB), key=len, reverse=True))
                         + r")(?!\w))")


def _mentioned(low: str, facts: list[Fact]) -> set[str]:
    """Tên chỉ tiêu vế câu nhắc, khớp tên dài nhất: "lợi nhuận" nằm trong "lợi nhuận trước thuế" thì không tính là nhắc
    LNST; "doanh thu" trong "doanh thu tài chính", "chi phí hoạt động" trong "chi phí hoạt động trên tổng thu nhập..."
    cũng vậy. Xét cả tên trong danh mục, để tên của chỉ tiêu câu không ghi dòng vẫn che được tên ngắn hơn."""
    vocab = VOCAB | {n for f in facts for n in f.names}
    occ = sorted(((m.start(), m.end(), n) for n in vocab if n for m in re.finditer(re.escape(n), low)),
                 key=lambda x: x[0] - x[1])
    taken, out = [], set()
    for s, e, n in occ:
        if not any(s < te and ts < e for ts, te in taken):
            taken.append((s, e))
            out.add(n)
    return out


def _named_ids(facts: list[Fact], low: str) -> tuple[set[str], bool]:
    """(mã các dòng có tên được nhắc theo khớp dài nhất, vế có nhắc tên chỉ tiêu nào không). Dòng được nhắc khi tên
    khớp thuộc đúng chỉ tiêu của dòng (tên của loại công ty khác cũng được) hoặc nằm trong tên của dòng."""
    names = _mentioned(low, facts)
    keys = {k for n in names for k in NAME_KEYS.get(n, ())}
    return {f.id for f in facts if (f.metric and f.metric in keys) or names & set(f.names)}, bool(names)


def _named(facts: list[Fact], low: str) -> list[Fact]:
    """Các dòng mà vế câu nhắc tên chỉ tiêu (khớp tên dài nhất); không nhắc tên nào thì giữ cả. Nhắc tên một chỉ tiêu
    không có trong các dòng này thì không dòng nào hợp."""
    ids, any_name = _named_ids(facts, low)
    return [f for f in facts if f.id in ids] if any_name else facts


def _cue(low: str) -> str | None:
    """Vế câu nói về quy mô (level), tốc độ thay đổi (growth) hay không rõ (None: chấp nhận dòng loại nào cũng được)."""
    if "quy mô" in low:
        return "level"
    return "growth" if GROWTH_WORDS.search(low) else None


def _hint(sheet: FactSheet | None, codes: list[str], c: str | None, low: str, rank: bool = False) -> str:
    """Gợi ý dòng bảng số câu cần ghi thêm: dòng có thứ tự chứa đủ các mã; với thứ hạng, cao nhất/thấp nhất thì ưu tiên
    dòng xếp hạng; rồi cùng loại số liệu, rồi dòng có tên chỉ tiêu xuất hiện trong vế câu. Tối đa 2 dòng; không có dòng
    nào thì không gợi ý."""
    if sheet is None:
        return ""
    cands = [f for f in sheet.facts if f.order and all(t in f.order for t in codes)]
    named, _ = _named_ids(cands, low)
    cands.sort(key=lambda f: (rank and f.kind != "rank", not (c is not None and f.measure == c), f.id not in named))
    return " — ghi thêm dòng " + ", ".join(f.id for f in cands[:2]) + " vào uses" if cands else ""


def _signed_values(f: Fact) -> list[tuple[str, Num]]:
    """Dòng so sánh hoặc xếp hạng theo tốc độ thay đổi: số có dấu đứng ngay sau từng mã ("VCB +64,7%, TCB −3,1%")."""
    if f.measure != "growth" or not f.order:
        return []
    out = []
    for t in f.order:
        m = re.search(rf"(?<!\w){t}\s+(?=[+−-]\d)", f.text)
        ns = numbers(f.text[m.end():]) if m else []
        if ns and ns[0].start == 0:
            out.append((t, ns[0]))
    return out


def _directions_by_number(clause: str, facts: list[Fact], tickers: list[str]) -> list[tuple[str, str]]:
    """(mã, chiều) của mọi dòng câu ghi có chứa một số khớp với số trong vế: dòng chỉ tiêu có chiều, và số có dấu sau
    mã trong dòng tốc độ thay đổi. Vế có mã thì chỉ giữ dòng của mã đó."""
    nums = numbers(clause)
    if not nums:
        return []
    out = []
    for f in facts:
        if f.direction and (not tickers or f.ticker in tickers):
            if any(matches(n, fn) for n in nums for fn in numbers(f.text)):
                out.append((f.id, f.direction))
        for t, v in _signed_values(f):
            if (not tickers or t in tickers) and any(matches(n, v) for n in nums):
                out.append((f.id, "up" if v.value > 0 else "down" if v.value < 0 else "flat"))
    return out


RATIO_KEYS = {k for r in catalog.RATIOS.values() for k in r} | {k for r in catalog.COMPUTED.values() for k in r}
MEDIAN = re.compile(r"trung vị")
ALL_OF = re.compile(r"(?<!\w)(?:đều|cả hai|cả ba)(?!\w)")


def _row_value(f: Fact, ticker: str) -> Num | None:
    """Số của mã trong dòng xếp hạng ("VPB +66,7%", "VCB 14.542 tỷ")."""
    m = re.search(rf"(?<!\w){ticker}\s+(?=[+−-]?\d)", f.text)
    ns = numbers(f.text[m.end():m.end() + 30]) if m else []
    return ns[0] if ns and ns[0].start == 0 else None


def _row_median(f: Fact) -> Num | None:
    m = re.search(r"trung vị nhóm\s+", f.text)
    ns = numbers(f.text[m.end():m.end() + 30]) if m else []
    return ns[0] if ns and ns[0].start == 0 else None


def _median_problem(clause: str, low: str, facts: list[Fact], who: str, higher: bool) -> str | None:
    """Vế "cao hơn/thấp hơn trung vị nhóm": chọn dòng xếp hạng có trung vị khớp số câu nêu (không nêu số thì dòng có tên
    chỉ tiêu câu nhắc), rồi so số của mã với trung vị. Không tìm được dòng thì báo thiếu dòng."""
    rows = [f for f in facts if f.order and who in f.order and _row_median(f) is not None]
    at = MEDIAN.search(low)
    said = [n for n in numbers(clause[at.end():]) if n.kind != "plain"][:1] if at else []
    if said:
        rows = [f for f in rows if matches(said[0], _row_median(f))] or rows
    rows = _named(rows, low)
    c = _cue(low[:at.start()]) if at else None      # "tăng trưởng ... cao hơn trung vị": dòng theo mức tăng
    if c:
        rows = [f for f in rows if f.measure == c] or rows
    if not rows:
        return f"không có dòng xếp hạng có trung vị nhóm cho {who}: {clause.strip()}"
    for f in rows:
        v, med = _row_value(f, who), _row_median(f)
        if v is None or v.value == med.value:
            return None
        if (v.value > med.value) == higher:
            return None
    f = rows[0]
    v, med = _row_value(f, who), _row_median(f)
    return f"{clause.strip()} — dòng {f.id}: {who} {vn(v.value / v.scale)}, trung vị nhóm {vn(med.value / med.scale)}"
_CHANGE = re.compile(r"thay đổi ([+−-]\d[\d.]*(?:,\d+)?)%")


def _two_metrics(low: str, facts: list[Fact], who: str | None) -> list[tuple[Fact, Decimal]] | None:
    """Vế câu so tốc độ của hai chỉ tiêu cùng một mã ("LNTT của TCB tăng chậm hơn tổng thu nhập hoạt động"): hai dòng
    chỉ tiêu theo thứ tự tên xuất hiện, kèm % thay đổi của mỗi dòng; không đúng dạng đó thì None."""
    rows = [f for f in facts if f.kind in ("metric", "ratio") and f.ticker and (who is None or f.ticker == who)]
    if len({f.ticker for f in rows}) != 1:
        return None
    names = _mentioned(low, rows)
    found = []
    for f in rows:
        pos = [low.find(n) for n in names & set(f.names) if n in low]
        m = _CHANGE.search(f.text)
        if pos and m:
            found.append((min(pos), f, Decimal(m.group(1).replace("−", "-").replace(".", "").replace(",", "."))))
    found.sort(key=lambda x: x[0])
    return [(f, g) for _, f, g in found[:2]] if len(found) >= 2 else None


def _paired_directions(clause: str, low: str, facts: list[Fact], tickers: list[str]) -> list[str]:
    """Vế có cả "tăng" lẫn "giảm" ("giảm 13,7% (tăng 310 tỷ)", "MSN giảm 53,5% và LNST tăng 202,8%"): mỗi từ chỉ chiều
    ghép với con số đứng ngay sau nó (không có từ chỉ chiều khác xen giữa), rồi so với chiều của dòng có số đó."""
    words = sorted([*UP.finditer(low), *DOWN.finditer(low)], key=lambda m: m.start())
    nums = numbers(clause)
    out = []
    for j, w in enumerate(words):
        stop = words[j + 1].start() if j + 1 < len(words) else len(low)
        n = next((x for x in nums if w.end() <= x.start < stop and x.start - w.end() <= 30), None)
        if n is None or NEGATED_VERB.search(low[:w.start()]):
            continue
        up = w.re is UP
        if LOSS_BEFORE.search(low[:w.start()]):
            up = not up
        near = [t for t in TICKER.findall(clause[:w.start()])][-1:] or tickers
        dirs = {d for _, d in _directions_by_number(clause[n.start:n.end], facts, near)}
        if len(dirs) == 1 and dirs != {"flat"} and (dirs == {"up"}) != up:
            out.append(f"“{w.group(0)} {clause[n.start:n.end].strip()}” ngược chiều với bảng số: {clause.strip()}")
    return out


_AUX = {"đã", "vẫn", "cũng", "lại", "đều", "chỉ", "có", "bị", "tiếp", "tục", "mạnh", "nhẹ", "là", "thì", "đang"}


def _against_cited_words(low: str, facts: list[Fact]) -> list[str]:
    """Từ chỉ chiều ngược với chính nguyên nhân hay cờ câu dẫn: câu nói "chi phí bán hàng giảm" mà dòng nguyên nhân ghi
    "Chi phí bán hàng tăng"; câu nói "lợi nhuận giảm nhờ thu nhập khác" mà cờ ghi "Lợi nhuận tăng nhờ thu nhập khác"."""
    texts = [f.text.lower() for f in facts if f.kind in ("reason", "flag")]
    if not texts:
        return []
    out = []
    for w in [*UP.finditer(low), *DOWN.finditer(low)]:
        if NEGATED_VERB.search(low[:w.start()]):
            continue
        words = re.findall(r"\w+", low[:w.start()])
        while words and words[-1] in _AUX:
            words.pop()
        if len(words) >= 2 and words[-2] == "của":        # "chi phí bán hàng của SAB giảm"
            del words[-2:]
        if len(words) < 2:
            continue
        item = r"\s+".join(map(re.escape, words[-2:]))
        same, other = (r"tăng", r"giảm") if w.re is UP else (r"giảm", r"tăng")
        if any(re.search(rf"(?<!\w){item}\s+{other}(?!\w)", t) and not re.search(rf"(?<!\w){item}\s+{same}(?!\w)", t)
               for t in texts):
            out.append(f"dòng nguyên nhân/cờ câu dẫn ghi “{' '.join(words[-2:])} {other}”")
    return out


def _check_directions(text: str, facts: list[Fact], out: SentenceCheck, bad, sheet: FactSheet | None = None,
                      skip: set[int] = frozenset()) -> None:
    """Từ tăng/giảm khớp chiều của dòng được ghi; so sánh hai mã và cao nhất/thấp nhất khớp thứ tự trong bảng số.
    Xét từng vế câu; loại số liệu (quy mô hay tốc độ thay đổi) cũng đọc theo từng vế. `skip`: vị trí đầu các vế đã kiểm
    theo dòng xu hướng (_check_trends)."""
    subject: str | None = None          # mã làm chủ ngữ ở vế trước ("TCB tăng 23,7%, cao hơn VCB")
    prev_low, prev_tickers = "", []
    spans = _clauses(text)
    for i, (a, b) in enumerate(spans):
        clause = text[a:b]
        nxt = list(dict.fromkeys(TICKER.findall(text[spans[i + 1][0]:spans[i + 1][1]]))) if i + 1 < len(spans) else []
        low = clause.lower().replace("tăng trưởng âm", "giảm")
        tickers = list(dict.fromkeys(TICKER.findall(clause)))
        p_low, p_tickers = prev_low, prev_tickers
        prev_low, prev_tickers = low, tickers
        if a in skip:
            if tickers:
                subject = tickers[0]
            continue
        up_m, down_m = UP.search(low), DOWN.search(low)
        declining = bool(down_m) and not up_m

        def cue(carried: bool) -> str | None:
            """Vế không tự nói rõ thì lấy ý từ vế trước khi vế trước là câu dẫn không có mã hoặc chủ ngữ được mang sang."""
            own = _cue(low)
            if own is None and p_low and (carried or not p_tickers):
                own = _cue(p_low)
            return own

        comp_up, comp_down = COMP_UP.search(low), COMP_DOWN.search(low)
        if (comp_up or comp_down) and MEDIAN.search(low):
            # "cao hơn trung vị nhóm +23,7%": số của mã so với trung vị ghi trong dòng xếp hạng
            who = tickers[0] if tickers else subject
            if who:
                problem = _median_problem(clause, low, facts, who, bool(comp_up and not comp_down))
                if problem:
                    bad("comparison", problem)
                subject = who
                continue
        if comp_up or comp_down:
            comp = comp_up or comp_down
            pair, carried = None, False
            if len(tickers) >= 2:
                pair = tickers[:2]
            elif len(tickers) == 1 and subject and subject != tickers[0]:
                at = re.search(rf"(?<!\w){tickers[0].lower()}(?!\w)", low)
                # mã đứng sau từ so sánh là vế sau ("..., nhanh hơn VCB"); đứng trước là chủ ngữ ("..., còn TCB nhanh hơn")
                pair = [subject, tickers[0]] if at and at.start() > comp.start() else [tickers[0], subject]
                carried = True
            elif len(tickers) == 1 and [t for t in nxt if t != tickers[0]]:
                # "VCB thấp hơn với 17.420 tỷ, trong khi TCB là 9.670 tỷ": vế sau của so sánh nằm ở vế câu kế tiếp
                pair = [tickers[0], next(t for t in nxt if t != tickers[0])]
            if not pair:
                two = _two_metrics(low, facts, tickers[0] if tickers else subject)
                if two and (cue(not tickers) == "growth" or GROWTH_WORDS.search(low)):
                    (fa, ga), (fb, gb) = two
                    first = bool(comp_up)
                    if declining:
                        first = not first
                    if (ga > gb) != first and ga != gb:
                        bad("comparison", f"{clause.strip()} — {fa.id}: {vn(ga)}%, {fb.id}: {vn(gb)}%")
                    continue
            if pair:
                a_t, b_t = pair
                rows = [f for f in facts if f.order and a_t in f.order and b_t in f.order]
                # mỗi từ so sánh trong vế xét riêng, loại số liệu đọc từ đoạn ngay trước nó ("quy mô lớn hơn và tăng
                # trưởng chậm hơn MCH"); vế chỉ có một từ so sánh thì đọc cả vế như trước
                comps = sorted([*COMP_UP.finditer(low), *COMP_DOWN.finditer(low)], key=lambda m: m.start())
                start = 0
                for j, cm in enumerate(comps):
                    local = _cue(low[start:cm.end()]) if len(comps) > 1 else None
                    start = cm.end()
                    if len(comps) > 1:      # "thấp hơn VHM và cao hơn VRE": mỗi từ so sánh với mã đứng ngay sau nó
                        stop = comps[j + 1].start() if j + 1 < len(comps) else len(low)
                        after = [t for t in TICKER.findall(clause[cm.end():stop])]
                        lead = [t for t in TICKER.findall(clause[:comps[0].start()])] or ([subject] if subject else [])
                        if after and lead and after[0] != lead[0]:
                            a_t, b_t = lead[0], after[0]
                            rows = [f for f in facts if f.order and a_t in f.order and b_t in f.order]
                    c = local or cue(carried)
                    first = cm.re is COMP_UP            # vế đầu đứng trước vế sau trong thứ tự (lớn -> nhỏ)?
                    if declining and c == "growth":
                        first = not first           # "giảm nhanh hơn" = tăng trưởng thấp hơn
                    if c is None:   # không rõ loại số liệu: theo dòng quy mô; không có thì xét dòng tăng trưởng
                        named_rows = _named(rows, low)
                        cands = [f for f in named_rows if f.measure == "level"] or \
                                [f for f in named_rows if f.measure == "growth"]
                    else:
                        cands = _named([f for f in rows if f.measure == c], low)
                        if not cands and c == "growth":     # tỷ lệ (CIR, biên lợi nhuận) có mức tính bằng %
                            cands = [f for f in _named(rows, low) if f.measure == "level" and f.metric in RATIO_KEYS]
                    if not cands:
                        bad("comparison", f"không có dòng so sánh {a_t} với {b_t}: {clause.strip()}"
                                          + _hint(sheet, [a_t, b_t], c, low))
                        break
                    if not any((f.order.index(a_t) < f.order.index(b_t)) == first for f in cands):
                        bad("comparison", clause.strip())
                        break
                subject = a_t if len(tickers) >= 2 or a_t == tickers[0] else subject
                continue
            as_dir = COMP_AS_DIR.search(low) if LAST_YEAR.search(low) else None
            if as_dir and (up_m or down_m):
                # "6,9%, thấp hơn mức 4,4% cùng kỳ và tăng 2,5 điểm %": phần so với cùng kỳ kiểm riêng theo chiều của dòng
                dirs = {d for _, d in _directions_by_number(clause, facts, tickers)}
                if not dirs:
                    named, _ = _named_ids(facts, low)
                    dirs = {f.direction for f in facts if f.direction and f.id in named
                            and (not tickers or f.ticker in tickers)}
                if len(dirs) == 1 and dirs != {"flat"} and (as_dir.group(1) is not None) != (dirs == {"up"}):
                    bad("comparison", f"{clause.strip()} — bảng số ghi chiều {'tăng' if dirs == {'up'} else 'giảm'}")
            elif as_dir:        # "thấp hơn cùng kỳ": kiểm như từ chỉ chiều ở dưới
                up_m, down_m = (as_dir, None) if as_dir.group(1) else (None, as_dir)
            else:
                out.warnings.append(f"không rõ hai vế so sánh: {clause.strip()}")
        top, bottom = SUP_TOP.search(low), SUP_BOTTOM.search(low)
        if top or bottom:
            if "một trong những" in text.lower():       # không phải xếp hạng tuyệt đối
                continue
            who = tickers[0] if tickers else subject
            if who:
                sup = top or bottom
                # loại số liệu đọc tới hết vế nhỏ chứa từ xếp hạng ("đứng đầu nhóm và tăng 20,6%": "đứng đầu" là quy mô)
                seg = low[:sup.end()] + low[sup.end():].split(" và ")[0]
                c = _cue(seg)
                if c is None and p_low and (not tickers or not p_tickers):
                    c = _cue(p_low)
                first = bool(top)
                if declining and c == "growth":
                    if top and "đầu" not in top.group(0):      # "giảm mạnh nhất" = tăng trưởng thấp nhất
                        first = False
                    else:                                      # "giảm ít nhất", "dẫn đầu mức giảm": chưa rõ nghĩa
                        out.warnings.append(f"không rõ cực: {clause.strip()}")
                        first = None                           # bỏ qua phần xếp hạng, vẫn kiểm từ chỉ chiều ở dưới
                cands = _named([f for f in facts if f.order and who in f.order and (c is None or f.measure == c)], low)
                if not cands and c == "growth":         # tỷ lệ có mức tính bằng %: "biên lợi nhuận ròng cao nhất ở 70,0%"
                    cands = _named([f for f in facts if f.order and who in f.order and f.measure == "level"
                                    and f.metric in RATIO_KEYS], low)
                if first is None:
                    pass
                elif not cands:
                    bad("comparison", f"không có dòng xếp hạng cho {who}: {clause.strip()}"
                                      + _hint(sheet, [who], c, low, rank=True))
                elif not any((f.order[0] if first else f.order[-1]) == who for f in cands):
                    bad("comparison", clause.strip())
            if tickers:         # "VRE có quy mô nhỏ nhất..., nhưng biên lợi nhuận ròng lại cao nhất": chủ ngữ mang sang
                subject = tickers[0]
            if not (UP.search(low) or DOWN.search(low)):
                continue
            # vế vừa xếp hạng vừa nói chiều ("đứng đầu nhóm và giảm 20,6%"): kiểm tiếp từ chỉ chiều ở dưới
        if tickers:
            subject = tickers[0]
        for problem in _against_cited_words(low, facts):
            bad("direction", f"{clause.strip()} — {problem}")
        if up_m and down_m:
            problems = _paired_directions(clause, low, facts, tickers)
            for problem in problems:
                bad("direction", problem)
            if not problems:
                out.warnings.append(f"vế vừa có tăng vừa có giảm: {clause.strip()}")
            continue
        if not up_m and not down_m:
            continue
        word = up_m or down_m
        before = low[:word.start()]
        if NEGATED_VERB.search(before):
            out.warnings.append(f"chiều bị phủ định: {clause.strip()}")
            continue
        up, down = bool(up_m), bool(down_m)
        if LOSS_BEFORE.search(before):  # "lỗ giảm" là cải thiện, "lỗ tăng" là xấu đi
            up, down = down, up
        # mọi dòng câu ghi có số khớp với số trong vế (không chỉ dòng con số được gắn liên kết)
        by_num = _directions_by_number(clause, facts, tickers)
        dirs = {d for _, d in by_num}
        named, any_name = _named_ids(facts, low)
        if len(dirs) > 1:       # số khớp nhiều dòng trái chiều: thu hẹp theo tên chỉ tiêu vế câu nhắc
            dirs = {d for fid, d in by_num if fid in named} or dirs
        if not by_num:          # không có số khớp: theo tên chỉ tiêu
            cands = [f for f in facts if f.direction and f.id in named and (not tickers or f.ticker in tickers)]
            if not cands:
                # chỉ một dòng có chiều: dùng khi vế nhắc đúng mã của dòng đó mà không nhắc tên chỉ tiêu khác (hoặc
                # không mã nào và nhắc tên chỉ tiêu của dòng)
                with_dir = [f for f in facts if f.direction]
                if len(with_dir) == 1:
                    f = with_dir[0]
                    if (f.ticker and f.ticker in tickers and (not any_name or f.id in named)) \
                            or (not tickers and f.id in named):
                        cands = with_dir
                elif with_dir and not any_name and ALL_OF.search(low):
                    cands = with_dir        # "đều thấp hơn cùng kỳ": mọi dòng có chiều câu ghi
                elif with_dir and not any_name and tickers:
                    own = [f for f in with_dir if f.ticker in tickers]
                    if own and len({f.direction for f in own}) == 1:
                        cands = own         # "lãi quý 2 của MBB giảm": mọi dòng có chiều của mã đều cùng chiều
            dirs = {f.direction for f in cands}
        if not dirs:
            # "VCB có mức giảm LNTT thấp nhất", "BID và CTG đều giảm lợi nhuận": dấu của mã trong dòng tốc độ thay đổi
            who = tickers or ([subject] if subject else [])
            rows = _named([f for f in facts if f.order and f.measure == "growth"], low)
            signs = {("up" if v.value > 0 else "down" if v.value < 0 else "flat")
                     for f in rows for t in who if t in f.order and (v := _row_value(f, t)) is not None}
            if len(signs) == 1:
                dirs = signs
        if not dirs and sheet is not None:
            # các dòng câu ghi không cho biết chiều: dò cả bảng số theo mã và tên chỉ tiêu; đúng một dòng thì kiểm theo nó
            who = tickers or ([subject] if subject else [])
            ids, _ = _named_ids(sheet.facts, low)
            found = [f for f in sheet.facts if f.direction and f.ticker in who and f.id in ids]
            if len(found) == 1:
                f = found[0]
                if (up and f.direction == "down") or (down and f.direction == "up"):
                    bad("direction", f"{clause.strip()} — bảng số ghi chiều ngược ở dòng {f.id}; ghi dòng {f.id} "
                                     f"vào uses")
                continue
        if len(dirs) > 1:       # "doanh thu tăng 17,1% và LNST tăng 13,7%": ghép từng từ chỉ chiều với số của nó
            problems = _paired_directions(clause, low, facts, tickers)
            for problem in problems:
                bad("direction", problem)
            if not problems:
                out.warnings.append(f"không rõ chiều: {clause.strip()}")
            continue
        if len(dirs) != 1:
            out.warnings.append(f"không rõ chiều: {clause.strip()}")
            continue
        d = dirs.pop()
        if (up and d == "down") or (down and d == "up"):
            bad("direction", clause.strip())


# ---- xu hướng nhiều quý -----------------------------------------------------------------------------------------
# Câu nói diễn biến qua nhiều quý chỉ kiểm được bằng dòng xu hướng (Fact.series): chuỗi tăng/giảm liên tiếp, cao nhất/
# thấp nhất trong N quý hoặc kể từ một quý, so với quý trước hay với một quý đã nêu, và số % / tiền của thay đổi giữa các
# quý. Phép tính dùng chung với bảng số (services/analyst/trend.py).

_QN = r"(\d{1,2}|hai|ba|bốn|tư|năm|sáu|bảy|tám)"
QN_WORDS = {"hai": 2, "ba": 3, "bốn": 4, "tư": 4, "năm": 5, "sáu": 6, "bảy": 7, "tám": 8}
_Q = r"(?:quý|q)\s*([1-4])(?:\s*[/-]\s*((?:19|20)\d{2}))?(?!\d)"
# "tăng 3 quý liên tiếp", "3 quý tăng liên tiếp", "quý thứ 3 liên tiếp", "liên tiếp 3 quý"
STREAK = re.compile(r"(?i)(?<!\w)(?:" + _QN + r"\s+quý\s+(?:\S+\s+){0,2}?liên\s+(?:tiếp|tục)"
                    r"|quý\s+thứ\s+" + _QN + r"\s+liên\s+(?:tiếp|tục)"
                    r"|liên\s+(?:tiếp|tục)\s+(?:trong\s+)?" + _QN + r"\s+quý)(?!\w)")
BARE_STREAK = re.compile(r"(?i)(?<!\w)liên\s+(?:tiếp|tục)(?!\w)")       # "tăng liên tiếp": ít nhất 2 quý
WINDOW_N = re.compile(r"(?i)(?<!\w)(?:trong|của|suốt|qua)\s+" + _QN + r"\s+quý(?!\w)"
                      r"|(?<!\w)" + _QN + r"\s+quý\s+(?:gần|vừa|qua|trở lại)")
SINCE = re.compile(r"(?i)(?<!\w)kể\s+từ\s+" + _Q)
ALL_Q = re.compile(r"(?i)(?<!\w)(?:các quý|cả giai đoạn|giai đoạn này|trong giai đoạn|qua từng quý|từng quý|xu hướng)"
                   r"(?!\w)")
REF_PREV = re.compile(r"(?i)(?<!\w)(?:so với|hơn|bằng|từ)\s+(?:mức\s+(?:của\s+)?)?quý\s+(?:liền\s+)?(?:trước|liền kề)"
                      r"(?:\s+đó)?(?!\w)")
REF_Q = re.compile(r"(?i)(?<!\w)(?:so với|hơn|từ)\s+(?:mức\s+(?:của\s+)?)?" + _Q)


# giữa từ cực và quý của nó chỉ có từ nối: "cao nhất ở quý 4/2025", "thấp nhất là vào quý 1"; "cao nhất và ở quý 1" thì
# quý sau là của vế khác
_SUP_TO_QUARTER = re.compile(r"^\s*(?:(?:là|ở|vào|tại|rơi vào|thuộc về|trong)\s+){0,2}$")


def _qn(s: str) -> int:
    return int(s) if s.isdigit() else QN_WORDS[s.lower()]


def _group_n(m: re.Match) -> int:
    return _qn(next(g for g in m.groups() if g))


def _changes(f: Fact) -> list[tuple[Num, str]]:
    """Mọi thay đổi in trong dòng xu hướng, kèm chiều: so với quý liền trước (% hoặc điểm %, và mức tiền), quý cuối so
    với quý đầu, so với cùng kỳ của từng quý."""
    s = f.series
    expense, ratio = f.metric in catalog.EXPENSES, f.metric in RATIO_KEYS
    profit = f.metric in catalog.PROFIT
    vals = [trend.value_of(e) for e in s]
    have = [i for i, v in enumerate(vals) if v is not None]
    pairs = [(i - 1, i) for i in range(1, len(s))] + ([(have[0], have[-1])] if len(have) >= 3 else [])
    out = []
    for i, j in pairs:
        a, b = vals[i], vals[j]
        d = trend.dir_between(a, b, expense)
        if d is None:
            continue
        pct = trend.pct_between(a, b, expense, profit, ratio)
        if pct is not None:
            out.append((Num(abs(pct), "pp" if ratio else "pct", 0, Decimal(1)), d))
        if not ratio:
            delta = abs(b) - abs(a) if expense else b - a
            out.append((Num(abs(delta), "money", 0, Decimal(1)), d))
    for e in s:
        if e.get("yoy") is not None and e.get("yoy_dir"):
            out.append((Num(abs(Decimal(e["yoy"])), "pp" if ratio else "pct", 0, Decimal(1)), e["yoy_dir"]))
    return out


def _subject_index(f: Fact, quarter: tuple[int, int | None] | None) -> int | None:
    if quarter is not None:
        return trend.resolve(f.series, *quarter)
    have = [i for i, e in enumerate(f.series) if e["value"] is not None]
    return have[-1] if have else None


def _word(want: str) -> str:
    return "tăng" if want == "up" else "giảm"


def _trend_problem(f: Fact, claim: dict) -> str | None:
    """Lý do nhận định không khớp dòng xu hướng `f`; khớp thì None."""
    s = f.series
    expense = f.metric in catalog.EXPENSES
    idx = _subject_index(f, claim.get("quarter"))
    if idx is None:
        q = claim.get("quarter")
        return f"dòng {f.id} không có số của quý {q[0]}" + (f"/{q[1]}" if q and q[1] else "")
    at = s[idx]["label"]
    vals = [trend.value_of(e) for e in s]
    kind, want = claim["kind"], claim.get("want")
    if kind == "streak":
        yoy = claim["yoy"]
        dirs = [e.get("yoy_dir") for e in s] if yoy else trend.qoq_dirs(s, expense)
        k = trend.streak(dirs, idx, want)
        if k < claim["n"]:
            base = "so với cùng kỳ" if yoy else "so với quý liền trước"
            return (f"dòng {f.id}: {at} không {_word(want)} {base}" if k == 0 else
                    f"dòng {f.id}: tính đến {at}, {base} chỉ {_word(want)} {k} quý liên tiếp")
        return None
    if kind == "ref":
        ri = idx - 1 if claim.get("ref") is None else trend.resolve(s, *claim["ref"], before=idx)
        if ri is None or ri < 0 or vals[ri] is None or vals[idx] is None:
            return f"dòng {f.id} không có số của quý được so"
        d = trend.dir_between(vals[ri], vals[idx], expense)
        if d != want:
            return f"dòng {f.id}: {at} so với {s[ri]['label']} là " + ("không đổi" if d == "flat" else _word(d))
        return None
    if kind == "extreme":
        # khoảng xét: "kể từ quý X" -> từ quý X đến quý được nói; "trong N quý" -> N quý cuối của dòng (khung của báo
        # cáo); không nói -> cả dòng
        end = len(s) - 1
        if claim.get("since") is not None:
            start, end = trend.resolve(s, *claim["since"], before=idx + 1), idx
            if start is None:
                return f"dòng {f.id} không có quý bắt đầu được nêu"
        elif claim.get("n"):
            start = end - claim["n"] + 1
            if start < 0 or any(vals[i] is None for i in range(start, end + 1)):
                return f"dòng {f.id} chỉ có {sum(v is not None for v in vals)} quý có số"
            if idx < start:
                return f"{at} nằm ngoài {claim['n']} quý cuối của dòng {f.id}"
        else:
            start = 0
        if claim["measure"] == "level":
            items = [(i, abs(vals[i]) if expense else vals[i]) for i in range(start, end + 1) if vals[i] is not None]
        else:
            ratio, profit = f.metric in RATIO_KEYS, f.metric in catalog.PROFIT
            items = [(i, g) for i in range(max(start, 1), end + 1)
                     if (g := trend.pct_between(vals[i - 1], vals[i], expense, profit, ratio)) is not None]
        target = next((v for i, v in items if i == idx), None)
        if target is None or len(items) < 2:
            return f"dòng {f.id}: không so được {at} với các quý khác"
        best = max(v for _, v in items) if claim["top"] else min(v for _, v in items)
        if target != best:
            i_best = next(i for i, v in items if v == best)
            return (f"dòng {f.id}: {'cao' if claim['top'] else 'thấp'} nhất trong khoảng này là {s[i_best]['label']}, "
                    f"không phải {at}")
        return None
    if kind == "span":          # "xu hướng tăng", "đi lên qua các quý": quý cuối so với quý đầu có số
        first = next((i for i in range(idx + 1) if vals[i] is not None), None)
        if first is None or first == idx:
            return f"dòng {f.id}: không đủ quý có số"
        d = trend.dir_between(vals[first], vals[idx], expense)
        if d != want:
            return f"dòng {f.id}: {at} so với {s[first]['label']} là " + ("không đổi" if d == "flat" else _word(d))
        return None
    return None


def _check_trends(text: str, facts: list[Fact], out: SentenceCheck, bad, sheet: FactSheet | None) -> set[int]:
    """Kiểm các vế câu nói diễn biến nhiều quý theo dòng xu hướng câu ghi. Trả về vị trí đầu các vế đã kiểm ở đây (bộ
    kiểm tra chiều chung bỏ qua các vế này, vì dòng chỉ tiêu chỉ có chiều so với cùng kỳ)."""
    handled: set[int] = set()
    rows_all = [f for f in facts if f.series]
    subject: str | None = None
    quarter: tuple[int, int | None] | None = None
    for a, b in _clauses(text):
        clause = text[a:b]
        low = clause.lower().replace("tăng trưởng âm", "giảm")
        tickers = list(dict.fromkeys(TICKER.findall(clause)))
        streak_m = STREAK.search(clause)
        bare = BARE_STREAK.search(clause) if not streak_m else None
        win, since, allq = WINDOW_N.search(clause), SINCE.search(clause), ALL_Q.search(clause)
        ref_prev, ref_q = REF_PREV.search(clause), REF_Q.search(clause)
        top, bottom = SUP_TOP.search(low), SUP_BOTTOM.search(low)
        taken = [m.span() for m in (since, ref_q) if m]
        refs = [m for m in trend.QUARTER_REF.finditer(clause) if not any(s <= m.start() < e for s, e in taken)]
        if refs:
            quarter = (int(refs[-1]["q"]), int(refs[-1]["y"]) if refs[-1]["y"] else None)
        if ref_q and quarter and ref_q.group(2) and quarter[1] and int(ref_q.group(1)) == quarter[0] \
                and int(ref_q.group(2)) == quarter[1] - 1:
            ref_q = None            # "so với quý 2/2025" khi nói quý 2/2026: so với cùng kỳ, kiểm như từ chỉ chiều thường
        who = tickers or ([subject] if subject else [])
        if tickers:
            subject = tickers[0]
        # chiều câu nói: tăng/giảm, hoặc cao hơn/thấp hơn khi so với một quý
        up_m, down_m = UP.search(low), DOWN.search(low)
        if (ref_prev or ref_q) and not (up_m or down_m):
            up_m, down_m = COMP_UP.search(low), COMP_DOWN.search(low)
        word = up_m or down_m
        want = None
        if word and not (up_m and down_m):
            want = "up" if up_m else "down"
            if LOSS_BEFORE.search(low[:word.start()]):
                want = "down" if want == "up" else "up"
            if NEGATED_VERB.search(low[:word.start()]):
                want = None
                out.warnings.append(f"chiều bị phủ định: {clause.strip()}")
        sup = top or bottom
        # cao nhất/thấp nhất nói về các quý (không phải giữa các mã): có khung ("trong 4 quý", "kể từ quý 1"), hoặc có
        # nêu quý mà câu không ghi dòng so sánh/xếp hạng giữa các mã
        quarter_sup = bool(sup) and bool(win or since or allq or ref_q or (
            rows_all and (refs or quarter) and not any(f.order for f in facts)))
        claims: list[dict] = []
        if streak_m or bare:
            if want:
                claims.append({"kind": "streak", "want": want, "n": _group_n(streak_m) if streak_m else 2,
                               "yoy": "cùng kỳ" in text[:b].lower()})
            else:
                out.warnings.append(f"không rõ chiều của chuỗi liên tiếp: {clause.strip()}")
        if quarter_sup:
            start = since or ref_q
            raw = clause.lower()
            # mỗi từ cực một quý: quý đứng ngay sau ("cao nhất ở quý 4/2025"), không thì quý đứng trước gần nhất
            sups = sorted([*SUP_TOP.finditer(raw), *SUP_BOTTOM.finditer(raw)], key=lambda m: m.start())
            for sm in sups:
                is_top = sm.re is SUP_TOP
                growth_word = bool(up_m or down_m) and "đầu" not in sm.group(0)
                if growth_word and down_m and not is_top:
                    out.warnings.append(f"không rõ cực: {clause.strip()}")
                    continue
                after = next((r for r in refs if r.start() >= sm.end()
                              and _SUP_TO_QUARTER.match(raw[sm.end():r.start()])), None)
                before = [r for r in refs if r.end() <= sm.start()]
                r = after or (before[-1] if before else None)
                claims.append({"kind": "extreme", "top": is_top != bool(growth_word and down_m),
                               "measure": "growth" if growth_word else "level",
                               "n": _group_n(win) if win and not start else None,
                               "since": (int(start.group(1)), int(start.group(2)) if start.group(2) else None)
                               if start else None,
                               "quarter": (int(r["q"]), int(r["y"]) if r["y"] else None) if r else quarter})
        elif (ref_prev or ref_q) and want:
            claims.append({"kind": "ref", "want": want,
                           "ref": None if ref_prev else (int(ref_q.group(1)),
                                                         int(ref_q.group(2)) if ref_q.group(2) else None)})
        elif allq and want and not claims:
            claims.append({"kind": "span", "want": want})
        strong = bool(streak_m or bare or ref_prev or ref_q or quarter_sup or (allq and want))
        rows = [f for f in rows_all if not who or f.ticker in who]
        ids, any_name = _named_ids(rows, low)
        if not any_name:
            ids, any_name = _named_ids(rows, text[:b].lower())
        if any_name:
            rows = [f for f in rows if f.id in ids]
        # số trong vế khớp một thay đổi của dòng xu hướng: chiều của từ đứng trước số phải khớp chiều của thay đổi đó
        # (số cũng có trong dòng khác câu ghi, như mức tăng so với cùng kỳ của dòng chỉ tiêu, thì để bộ kiểm tra chung)
        num_dirs = set()
        others = [fn for f in facts if not f.series for fn, _ in _fact_numbers(f)]
        if rows and want:
            for n in numbers(clause):
                if not any(matches(n, fn) for fn in others):
                    num_dirs |= {d for f in rows for fn, d in _changes(f) if matches(n, fn)}
        if not strong and not num_dirs:
            continue
        handled.add(a)
        if not rows:
            hint = ""
            if sheet is not None:
                cands = [f.id for f in sheet.facts if f.series and (not who or f.ticker in who)]
                hint = " — ghi thêm dòng " + ", ".join(cands[:2]) + " vào uses" if cands else ""
            bad("trend", f"câu nói diễn biến nhiều quý nhưng không ghi dòng xu hướng tương ứng: {clause.strip()}"
                         + hint)
            continue
        if num_dirs and not claims and len(num_dirs) == 1 and num_dirs != {"flat"} and want not in num_dirs:
            bad("trend", f"“{word.group(0)}” ngược chiều với thay đổi giữa các quý trong bảng số: {clause.strip()}")
            continue
        need_all = bool(ALL_OF.search(low))
        for claim in claims:
            problems = [_trend_problem(f, {"quarter": quarter} | claim) for f in rows]
            ok = all(p is None for p in problems) if need_all else any(p is None for p in problems)
            if not ok:
                bad("trend", f"{clause.strip()} — " + next(p for p in problems if p))
                break
    return handled


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
