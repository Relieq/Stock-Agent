"""Chuẩn hóa số in trên BCTC Việt Nam.

Mô hình đọc ảnh chỉ chép lại nguyên văn từng ô; mọi việc diễn giải số làm ở đây, bằng code:
  * dấu phân tách hàng nghìn suy ra theo từng tài liệu (khoảng 1/4 BCTC dùng "1,234,567", còn lại "1.234.567");
  * số âm viết trong ngoặc "(1.234)" hoặc có dấu trừ;
  * ô trống, "-", "–" là không có số;
  * đơn vị tính (đồng, nghìn đồng, triệu đồng) đổi về đồng.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

_EMPTY = {"", "-", "–", "—", "_", "x", "n/a"}
_MULTI_GROUP = {
    ".": re.compile(r"^\(?-?\d{1,3}(\.\d{3}){2,}\)?$"),
    ",": re.compile(r"^\(?-?\d{1,3}(,\d{3}){2,}\)?$"),
}


def _clean(raw: str) -> str:
    s = unicodedata.normalize("NFKC", raw).strip()
    s = s.replace("−", "-")            # dấu trừ toán học
    return re.sub(r"\s+", "", s)            # "1 234 567" -> "1234567"


def infer_thousands_sep(raw_values: Iterable[str | None]) -> str:
    """Suy dấu phân tách hàng nghìn của cả tài liệu từ các số có từ 2 nhóm phân tách trở lên.

    Số chỉ có một nhóm ("1.234") không phân biệt được với số thập phân nên không dùng để bỏ phiếu.
    Không có bằng chứng thì mặc định "." (khoảng 3/4 BCTC).
    """
    votes: Counter[str] = Counter()
    for raw in raw_values:
        if not raw:
            continue
        s = _clean(raw)
        for sep, pattern in _MULTI_GROUP.items():
            if pattern.match(s):
                votes[sep] += 1
    if not votes:
        return "."
    return votes.most_common(1)[0][0]


def parse_amount(raw: str | None, thousands_sep: str) -> Decimal | None:
    """'(1.234.567)' -> Decimal('-1234567'). Trả None nếu ô trống hoặc không phải số."""
    if raw is None:
        return None
    s = _clean(raw)
    if s.casefold() in _EMPTY:
        return None

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    if s.startswith("-"):
        negative, s = not negative, s[1:]

    decimal_mark = "," if thousands_sep == "." else "."
    s = s.replace(thousands_sep, "")
    s = s.replace(decimal_mark, ".")
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        return None
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    return -value if negative else value


_UNIT_MULTIPLIERS = [
    (re.compile(r"tri[eệ]u"), Decimal(1_000_000)),
    (re.compile(r"ngh[iì]n|ng[aà]n"), Decimal(1_000)),
    (re.compile(r"t[yỷ]\b"), Decimal(1_000_000_000)),
    (re.compile(r"million"), Decimal(1_000_000)),
    (re.compile(r"thousand"), Decimal(1_000)),
]


def unit_multiplier(unit_raw: str | None) -> Decimal | None:
    """'Đơn vị tính: triệu đồng' -> 1_000_000. Trả None nếu không nhận ra đơn vị."""
    if not unit_raw:
        return None
    t = unicodedata.normalize("NFC", unit_raw).casefold()
    for pattern, mult in _UNIT_MULTIPLIERS:
        if pattern.search(t):
            return mult
    if re.search(r"đồng|dong|vnd|vnđ", t):
        return Decimal(1)
    return None


def normalize_code(raw: str | None) -> str | None:
    """Chuẩn hóa mã số chỉ tiêu: '1' -> '01', ' 411a ' -> '411a', '421 b' -> '421b'."""
    if raw is None:
        return None
    s = re.sub(r"\s+", "", unicodedata.normalize("NFKC", raw)).lower()
    if not s:
        return None
    if re.fullmatch(r"\d", s):
        s = "0" + s
    return s
