"""Xu hướng nhiều quý: các quý của khung, thay đổi giữa hai quý, chuỗi tăng/giảm liên tiếp, quý cao nhất/thấp nhất.

Thuần, không đụng CSDL: bảng số (facts.py) dùng để viết dòng "Xu hướng ...", bộ kiểm tra số (guard.py) dùng lại đúng các
hàm này để kiểm các câu "tăng 3 quý liên tiếp", "cao nhất trong 4 quý", "giảm từ quý 1".

Chiều của thay đổi: chi phí theo độ lớn (như thẻ KQKD); lợi nhuận theo giá trị có dấu (lỗ thu hẹp là tăng).
"""

from __future__ import annotations

import re
from decimal import Decimal

DEFAULT_QUARTERS = 4      # không nói số quý: 4 quý gần nhất
MAX_QUARTERS = 8


def quarters_back(year: int, period: str, n: int) -> list[tuple[int, int]]:
    """n quý liên tiếp kết thúc ở (năm, quý), từ cũ đến mới: [(2025, 3), (2025, 4), (2026, 1), (2026, 2)]."""
    y, q = year, int(period[1])
    out = []
    for _ in range(n):
        out.append((y, q))
        y, q = (y, q - 1) if q > 1 else (y - 1, 4)
    return out[::-1]


def qlabel(y: int, q: int) -> str:
    return f"quý {q}/{y}"


def value_of(entry: dict) -> Decimal | None:
    v = entry.get("value")
    return None if v is None else Decimal(str(v))


def dir_between(a: Decimal | None, b: Decimal | None, expense: bool) -> str | None:
    """Chiều từ a sang b: up / down / flat; thiếu một số thì None."""
    if a is None or b is None:
        return None
    if expense:
        a, b = abs(a), abs(b)
    return "up" if b > a else "down" if b < a else "flat"


def pct_between(a: Decimal | None, b: Decimal | None, expense: bool, profit: bool, ratio: bool) -> Decimal | None:
    """% thay đổi từ a sang b (tỷ lệ: điểm %). Lợi nhuận âm hoặc bằng 0 ở một quý: None, như quy tắc của thẻ KQKD."""
    if a is None or b is None:
        return None
    if ratio:
        return b - a
    if a == 0 or (profit and (a <= 0 or b <= 0)):
        return None
    if expense:
        a, b = abs(a), abs(b)
    return (b - a) / abs(a) * 100


def qoq_dirs(series: list[dict], expense: bool) -> list[str | None]:
    """Chiều so với quý liền trước của từng quý (quý đầu: None)."""
    vals = [value_of(e) for e in series]
    return [None] + [dir_between(vals[i - 1], vals[i], expense) for i in range(1, len(vals))]


def streak(dirs: list[str | None], end: int, want: str) -> int:
    """Số quý liên tiếp có chiều `want` tính lùi từ quý thứ `end` (gồm cả quý đó)."""
    n = 0
    i = end
    while i >= 0 and dirs[i] == want:
        n += 1
        i -= 1
    return n


def last_streak(dirs: list[str | None]) -> tuple[str, int] | None:
    """(chiều, độ dài) của chuỗi tăng/giảm kết thúc ở quý cuối; quý cuối không có chiều hoặc đi ngang: None."""
    if not dirs or dirs[-1] not in ("up", "down"):
        return None
    return dirs[-1], streak(dirs, len(dirs) - 1, dirs[-1])


def extremes(series: list[dict], expense: bool) -> tuple[int, int] | None:
    """(chỉ số quý cao nhất, chỉ số quý thấp nhất) trong các quý có số; chi phí theo độ lớn. Dưới 2 quý có số: None."""
    have = [(i, abs(v) if expense else v) for i, e in enumerate(series) if (v := value_of(e)) is not None]
    if len(have) < 2:
        return None
    hi = max(have, key=lambda x: x[1])[0]
    lo = min(have, key=lambda x: x[1])[0]
    return hi, lo


QUARTER_REF = re.compile(r"(?i)(?<!\w)(?:quý|q)\s*(?P<q>[1-4])(?:\s*[/-]\s*(?P<y>(?:19|20)\d{2}))?(?!\d)")


def resolve(series: list[dict], q: int, y: int | None, before: int | None = None) -> int | None:
    """Chỉ số của quý (q, năm) trong chuỗi; không nói năm thì quý số q gần nhất (trước chỉ số `before` nếu có)."""
    idx = [i for i, e in enumerate(series) if e["q"] == q and (y is None or e["y"] == y)
           and (before is None or i < before)]
    return idx[-1] if idx else None
