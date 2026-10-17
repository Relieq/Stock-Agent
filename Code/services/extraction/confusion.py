"""Mô hình nhầm chữ số của người đọc (mô hình thị giác): số đúng X bị chép thành Y với xác suất bao nhiêu.

Lỗi đọc thật rất lệch: trên 81 lỗi nhầm đúng một chữ số đã sửa (đến 18/10/2026), 6->8, 1->7, 8->5, 6->5, 5->3 chiếm
gần nửa. Bước định vị lỗi (repair.localize) trước đây coi mọi kiểu nhầm như nhau (chỉ đếm số chữ số khác), nên khi
nhiều ô cùng làm khớp một ràng buộc, ô đúng chỉ đứng đầu khoảng 40%; xếp theo mô hình này thì khoảng 65% (cấy 2.000
lỗi, mô hình học từ một nửa số lỗi thật, lỗi cấy lấy từ nửa còn lại).

Bảng đếm lưu ở digit_confusion.json cạnh file này, dựng lại bằng `python eval/confusion.py` sau mỗi mùa BCTC.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

TABLE = Path(__file__).with_name("digit_confusion.json")
EPS_SUB = 0.01          # xác suất một chữ số bị đọc nhầm (chỉ để so các phương án với nhau, không cần chính xác)
EPS_INDEL = 0.001       # xác suất thừa/thiếu một chữ số
ALPHA = 0.5             # làm trơn: kiểu nhầm chưa gặp vẫn có xác suất nhỏ


def _digits(raw: str | None) -> str:
    return re.sub(r"\D", "", raw or "")


def error_pairs(record: dict) -> list[tuple[str, str]]:
    """(số đọc sai, số đúng) đã biết trong một bản ghi: sửa tay sau khi đối chiếu ảnh, đề xuất theo ràng buộc được đọc
    lại xác nhận, đọc lại được giữ, đối chiếu kỳ được áp dụng."""
    out = [(m.get("before"), m.get("after") or m.get("value")) for m in record.get("manual_fixes", [])]
    out += [(x.get("before"), x.get("after")) for x in record.get("repairs", []) if x.get("accepted")]
    out += [(x.get("before"), x.get("after")) for x in record.get("rereads", []) if x.get("kept")]
    out += [(x.get("before"), x.get("after")) for x in record.get("cell_verifications", []) if x.get("applied")]
    return [(b, a) for b, a in out if _digits(b) and _digits(a) and _digits(b) != _digits(a)]


def count_substitutions(pairs) -> dict[str, dict[str, int]]:
    """Đếm nhầm một chữ số (cùng độ dài, khác đúng một chữ số): {chữ số đúng: {đọc thành: số lần}}."""
    counts: dict[str, Counter] = defaultdict(Counter)
    for wrong, right in pairs:
        w, r = _digits(wrong), _digits(right)
        if len(w) == len(r):
            diff = [(a, b) for a, b in zip(r, w) if a != b]
            if len(diff) == 1:
                counts[diff[0][0]][diff[0][1]] += 1
    return {k: dict(v) for k, v in counts.items()}


@lru_cache(maxsize=1)
def load_table() -> dict[str, dict[str, int]]:
    try:
        return json.loads(TABLE.read_text(encoding="utf-8"))["substitutions"]
    except (OSError, ValueError, KeyError):
        return {}


def log_sub(true: str, read: str, table: dict | None = None) -> float:
    """log xác suất chữ số đúng `true` bị đọc thành `read` (true != read)."""
    row = (load_table() if table is None else table).get(true, {})
    return math.log(EPS_SUB * (row.get(read, 0) + ALPHA) / (sum(row.values()) + 9 * ALPHA))


def log_likelihood(read_raw: str | None, true_raw: str, table: dict | None = None) -> float:
    """log xác suất số đúng `true_raw` bị chép thành `read_raw` (căn hai dãy chữ số như khoảng cách sửa: nhầm, thừa,
    thiếu chữ số). Chỉ dùng để so các phương án sửa của cùng một lỗi với nhau."""
    a, b = _digits(true_raw), _digits(read_raw)
    neg_inf = float("-inf")
    prev = [j * math.log(EPS_INDEL) for j in range(len(b) + 1)]
    for i, x in enumerate(a, 1):
        cur = [i * math.log(EPS_INDEL)] + [neg_inf] * len(b)
        for j, y in enumerate(b, 1):
            cur[j] = max(prev[j - 1] + (0.0 if x == y else log_sub(x, y, table)),
                         prev[j] + math.log(EPS_INDEL), cur[j - 1] + math.log(EPS_INDEL))
        prev = cur
    return prev[-1]
