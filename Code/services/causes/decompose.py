"""Tách mức thay đổi LNST so với cùng kỳ thành phần đóng góp của từng dòng KQKD (Baocao/dinh-huong/agent-nguyen-nhan.md
mục 3.1). Chỉ dùng code: đi ngược các ràng buộc kế toán của mẫu BCTC (services/extraction/rules.py) từ dòng LNST xuống
các dòng thành phần, nên tổng đóng góp bằng đúng mức thay đổi LNST khi các ràng buộc đó đã đạt.

Đóng góp của một dòng = dấu của dòng trong công thức × (kỳ này − cùng kỳ). Chi phí tăng thì đóng góp âm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from services.extraction.rules import RULESETS

# Dòng dừng tách cho từng mẫu: đủ chi tiết để nói "vì sao" mà không tách tới dòng con của doanh thu hay thuế
LEAVES = {
    # Lợi nhuận gộp (20) là một dòng: doanh thu và giá vốn thường cùng tăng, tách ra thì hai số lớn ngược chiều che mất
    # điều cần nói (doanh thu tăng hay biên lợi nhuận đổi), phần đó để thuyết minh giải thích
    "TT200": {"20", "21", "22", "24", "25", "26", "31", "32", "51", "52"},
    "TT99": {"20", "21", "22", "23", "25", "26", "27", "31", "32", "51", "52"},
    "TCTD": {"b.nii", "b.nfee", "b.nfx", "b.ntrading", "b.ninv", "b.nother", "b.equity_inc", "b.opex", "b.prov",
             "b.cit"},
    "CTCK": {"20", "40", "50", "60", "61", "62", "80", "100"},
}
# Dòng LNST và LNST của cổ đông công ty mẹ; phần không kiểm soát = LNST − phần công ty mẹ
NPAT = {"TT200": ("60", "61"), "TT99": ("60", "61"), "TCTD": ("b.npat", "b.npat_parent"), "CTCK": ("200", "201")}
MINORITY = "(lợi ích cổ đông không kiểm soát)"
PAIRS = {"quarter": ("q_cur", "q_prev_year"), "ytd": ("ytd_cur", "ytd_prev_year")}


@dataclass
class Part:
    code: str
    label: str
    cur: Decimal
    prev: Decimal
    effect: Decimal              # đóng góp vào mức thay đổi LNST (đồng), có dấu
    share: Decimal = Decimal(0)  # effect / |mức thay đổi LNST|


@dataclass
class Breakdown:
    target: str                  # mã dòng LNST được tách
    cur: Decimal
    prev: Decimal
    parts: list[Part] = field(default_factory=list)
    residual: Decimal = Decimal(0)   # mức thay đổi LNST trừ tổng đóng góp (trong sai số làm tròn nếu hợp lệ)
    ok: bool = True
    note: str = ""

    @property
    def change(self) -> Decimal:
        return self.cur - self.prev


def _rule_for(template: str, code: str, values: dict) -> tuple | None:
    """Ràng buộc có vế trái là `code`, ưu tiên ràng buộc bắt buộc rồi ít số hạng thiếu nhất. Ràng buộc không bắt buộc
    (TT99 dòng 30: mã con chưa đối chiếu với phụ lục thông tư) vẫn dùng được vì tổng đóng góp được kiểm lại ở cuối."""
    best = None
    for r in RULESETS[template].rules:
        if r.statement != "IS" or r.lhs != code:
            continue
        if r.when_present and r.when_present not in values or r.when_absent and r.when_absent in values:
            continue
        if code in NPAT[template] and any(c in NPAT[template] for _, c in r.rhs):
            continue                 # 60 = 61 + 62: không tách LNST thành phần công ty mẹ và phần không kiểm soát
        missing = sum(c not in values for _, c in r.rhs)
        if missing == len(r.rhs):
            continue
        key = (not r.gate, missing)
        if best is None or key < best[0]:
            best = (key, r)
    return best[1] if best else None


def _expand(template: str, code: str, sign: int, values: dict, flip: bool, out: dict, depth: int = 0) -> bool:
    """Cộng (mã lá -> dấu) vào `out`. False nếu gặp dòng không tách được mà cũng không phải lá."""
    if code in LEAVES[template] or depth > 6:
        out[code] = out.get(code, 0) + sign
        return True
    r = _rule_for(template, code, values)
    if r is None:
        if code in values:
            out[code] = out.get(code, 0) + sign    # dòng tổng không có công thức: coi như lá
            return True
        return False
    ok = True
    for s, c in r.rhs:
        if c not in values and not any(k.startswith(c + ".") for k in values):
            continue                                 # số hạng không in trên BCTC (bằng 0)
        # Chi phí in số âm thì đã mang dấu: cộng thẳng (như phép kiểm ràng buộc)
        eff = (1 if flip and c not in r.abs_codes else s) * sign
        ok &= _expand(template, c, eff, values, flip, out, depth + 1)
    return ok


def decompose(template: str, values: dict[str, dict[str, Decimal]], labels: dict[str, str], flip: bool,
              period: str = "quarter", tolerance: Decimal = Decimal(0)) -> Breakdown | None:
    """`values`: mã -> cột -> số (đồng) của KQKD đã chuẩn hóa; `flip`: BCTC in chi phí thành số âm. Tách LNST của cổ
    đông công ty mẹ nếu có, không thì LNST. None nếu mẫu chưa hỗ trợ hoặc không có số hai kỳ."""
    if template not in LEAVES:
        return None
    cur_col, prev_col = PAIRS[period]
    npat, parent = NPAT[template]
    target = parent if parent in values else npat
    if target not in values or npat not in values:
        return None
    get = lambda c, col: values.get(c, {}).get(col)   # noqa: E731
    cur, prev = get(target, cur_col), get(target, prev_col)
    if cur is None or prev is None:
        return None
    signs: dict[str, int] = {}
    if not _expand(template, npat, 1, values, flip, signs):
        return Breakdown(target, cur, prev, ok=False, note="có dòng tổng không tách được theo ràng buộc của mẫu")
    parts = []
    for code, sign in signs.items():
        if sign == 0:
            continue
        a, b = get(code, cur_col) or Decimal(0), get(code, prev_col) or Decimal(0)
        parts.append(Part(code, labels.get(code, code), a, b, sign * (a - b)))
    if target == parent:
        # Phần công ty mẹ = LNST − phần không kiểm soát (tính từ hai dòng đã đọc, không phụ thuộc dấu in)
        mi_cur = get(npat, cur_col) - cur if get(npat, cur_col) is not None else None
        mi_prev = get(npat, prev_col) - prev if get(npat, prev_col) is not None else None
        if mi_cur is not None and mi_prev is not None:
            parts.append(Part(MINORITY, "Phần lợi nhuận của cổ đông không kiểm soát", mi_cur, mi_prev,
                              -(mi_cur - mi_prev)))
    bd = Breakdown(target, cur, prev, parts)
    bd.residual = bd.change - sum((p.effect for p in parts), Decimal(0))
    bd.ok = abs(bd.residual) <= tolerance
    if not bd.ok:
        bd.note = "tổng đóng góp các dòng khác mức thay đổi LNST"
    base = abs(bd.change)
    for p in parts:
        p.share = p.effect / base if base else Decimal(0)
    bd.parts.sort(key=lambda p: -abs(p.effect))
    return bd


TWIN = {"TT99": "TT200", "TT200": "TT99"}


def decompose_any(template: str, values, labels, flip: bool, period: str = "quarter",
                  tolerance: Decimal = Decimal(0)) -> Breakdown | None:
    """Như decompose; khi không khớp thì thử mẫu doanh nghiệp còn lại: nhiều BCTC năm 2026 vẫn in mã dòng theo TT200
    (ví dụ lãi công ty liên kết mã 24) dù hệ thống nhận là TT99, và ngược lại."""
    bd = decompose(template, values, labels, flip, period, tolerance)
    if bd is not None and not bd.ok and template in TWIN:
        other = decompose(TWIN[template], values, labels, flip, period, tolerance)
        if other is not None and other.ok:
            other.note = f"tách theo mã dòng của mẫu {TWIN[template]}"
            return other
    return bd


def top_parts(bd: Breakdown, cover: Decimal = Decimal("0.8"), limit: int = 4) -> list[Part]:
    """Các dòng đóng góp lớn nhất cùng chiều với mức thay đổi, đủ để giải thích `cover` mức thay đổi (tối đa `limit`)."""
    same = [p for p in bd.parts if p.effect * bd.change > 0]
    out, got = [], Decimal(0)
    for p in same:
        if len(out) >= limit or (bd.change and got / abs(bd.change) >= cover):
            break
        out.append(p)
        got += abs(p.effect)
    return out
