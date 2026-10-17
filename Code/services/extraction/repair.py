"""Tự định vị ô đọc sai bằng ràng buộc kế toán và đề xuất số đúng (không gọi mô hình).

Một BCTC có hàng trăm phép cộng ràng buộc lẫn nhau, nên khi một ô bị đọc sai thường có thể chỉ ra ô đó và suy ra số
đúng: thử thay từng ô thuộc các ràng buộc bị lệch bằng giá trị làm ràng buộc đó khớp, giữ phương án làm khớp nhiều
ràng buộc nhất mà không làm lệch ràng buộc nào đang đúng. Đây là ý tưởng "định vị lỗi" (error localization) của
phương pháp Fellegi–Holt mà cơ quan thống kê dùng để làm sạch số liệu điều tra (Fellegi & Holt, 1976), áp dụng cho
BCTC dạng scan.

Bằng chứng của một đề xuất:
  * số ràng buộc nó làm khớp: ô FPT quý 4/2025 mã 224 vừa làm khớp 224 = 225 + 226 vừa làm khớp 220 = 221 + 224 + 227;
  * số mới phải là số nguyên theo đơn vị in trên BCTC;
  * khác số cũ ít chữ số (kiểu đọc nhầm 1 <-> 7, 3 <-> 8).
Một ràng buộc lệch mà chỉ có một ràng buộc làm chứng thì mọi số hạng của nó đều "sửa được"; khi đó các phương án
ngang nhau được trả về cùng nhau để đọc lại riêng từng ô (pipeline._repair_by_constraints) và giữ ô nào đọc lại ra
đúng số đề xuất. Không phương án nào khớp, hoặc đọc lại vẫn ra số cũ, thì có thể chính BCTC in lệch.
"""

from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass, field
from decimal import Decimal

from services.extraction.confusion import log_likelihood
from services.extraction.numbers import normalize_code, parse_amount
from services.extraction.rules import RULESETS
from services.extraction.validate import Check, ExtractedStatement, Statement, group_rule_codes, validate

MAX_DIGITS_CHANGED = 2          # đọc nhầm điển hình: 1-2 chữ số
MAX_ROUNDS = 40                 # số ô tối đa sửa trên một tài liệu


@dataclass
class Proposal:
    statement: str
    code: str
    column_kind: str
    row: int                    # vị trí dòng trong record["raw"][statement]["rows"]
    label: str
    before: str | None          # chuỗi đang có
    after: str                  # chuỗi đề xuất, cùng kiểu viết với tài liệu
    value: Decimal              # số đề xuất (đồng)
    fixes: list[str]            # các ràng buộc được làm khớp, dạng "IS_40@ytd_prev_year"
    digits_changed: int
    alternatives: int = 0       # số phương án khác ngang bằng (cùng số ràng buộc làm khớp, chữ số khác ít tương đương)
    # Ô đi kèm khi hai ô cùng lệch một lượng nên phép cộng giữa chúng vẫn khớp (VHM quý 4/2025: "thu nhập khác" và
    # "lãi khác" cùng lệch 50.000, chỉ dòng tổng phía dưới lệch). Sửa một mình ô nào cũng làm lệch phép cộng giữa hai ô.
    partner: "Proposal | None" = None
    # Xác suất trong nhóm phương án ngang nhau theo mô hình nhầm chữ số thật (confusion.py): ô nào có kiểu nhầm hay gặp
    # hơn (6->8, 1->7) thì nhiều khả năng là ô đọc sai hơn. Phương án duy nhất: 1.
    prob: float = 1.0

    @property
    def confidence(self) -> str:
        """cao: làm khớp từ 2 ràng buộc và không có phương án ngang; vừa: 1 ràng buộc nhưng là phương án duy nhất có
        ít chữ số khác; thấp: còn phương án ngang, cần đọc lại để chọn."""
        if self.alternatives:
            return "thấp"
        return "cao" if len(self.fixes) >= 2 else "vừa"


@dataclass
class Localization:
    proposals: list[Proposal] = field(default_factory=list)      # theo thứ tự áp dụng (mỗi vòng một ô)
    ambiguous: list[list[Proposal]] = field(default_factory=list)  # nhóm phương án ngang nhau chưa chọn được
    unresolved: list[str] = field(default_factory=list)          # ràng buộc vẫn lệch, không ô nào giải thích được


def _key(c: Check) -> str:
    return f"{c.rule_id}@{c.column_kind}"


def _failures(statements: dict[str, Statement], template: str) -> dict[str, Check]:
    return {_key(c): c for c in validate(statements, template) if c.gate and not c.passed}


def _cells_of(check: Check, template: str, statements: dict[str, Statement]) -> list[tuple[str, str, str]]:
    """Các ô (báo cáo, mã, cột) tham gia một ràng buộc bị lệch."""
    rs = RULESETS[template]
    rule = next((r for r in rs.rules if r.id == check.rule_id), None)
    if rule is not None:
        st = statements.get(rule.statement)
        codes = [rule.lhs, *(c for _, c in rule.rhs)]
        if rule.include_suffixed and st is not None:
            bases = {c for _, c in rule.rhs}
            codes += [c for c in st.values if (m := re.fullmatch(r"(\d+)[a-z]", c)) and m.group(1) in bases]
        return [(rule.statement, c, check.column_kind) for c in codes
                if st is not None and check.column_kind in st.values.get(c, {})]
    cross = next((x for x in rs.cross_rules if x.id == check.rule_id), None)
    if cross is None:
        grp = group_rule_codes(check.rule_id, {name: set(st.values) for name, st in statements.items()}, template)
        if grp is None:
            return []
        st = statements[grp[0]]
        return [(grp[0], c, check.column_kind) for c in grp[1] if check.column_kind in st.values.get(c, {})]
    return [(s, c, col) for s, c, col in (cross.left, cross.right) if col in statements.get(s, Statement(s, Decimal(1))).values.get(c, {})]


def _digits(raw: str | None) -> str:
    return re.sub(r"\D", "", raw or "")


def digits_changed(before: str | None, after: str) -> int:
    """Số chữ số phải đổi, thêm hoặc bớt để từ số cũ ra số mới (khoảng cách Levenshtein trên dãy chữ số): đọc nhầm
    một chữ số là 1, chép thừa một chữ số ("4.714.930" thay vì "471.930", VHM quý 4/2025) cũng là 1."""
    a, b = _digits(before), _digits(after)
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def format_like(before: str | None, units: Decimal, sep: str) -> str:
    """Viết số theo kiểu của ô cũ: dấu phân tách hàng nghìn của tài liệu, số âm trong ngoặc trừ khi ô cũ dùng dấu trừ."""
    body = f"{abs(int(units)):,}".replace(",", sep)
    if units >= 0:
        return body
    return f"-{body}" if (before or "").strip().startswith("-") else f"({body})"


def _row_index(extracted: list[ExtractedStatement], statement: str, code: str, col: str) -> tuple[int, str, str | None] | None:
    """Dòng đầu tiên mang mã này và có số ở cột này (giống cách normalize giữ dòng đầu)."""
    ex = next((e for e in extracted if e.statement == statement), None)
    if ex is None:
        return None
    for i, it in enumerate(ex.items):
        if normalize_code(it.code) == code:
            return i, it.label, it.values_raw.get(col)
    return None


def localize(extracted: list[ExtractedStatement], statements: dict[str, Statement], sep: str,
             template: str | None) -> Localization:
    """Lần lượt chọn ô mà thay số thì làm khớp nhiều ràng buộc bắt buộc nhất, không làm lệch ràng buộc nào khác.

    Phương án độ tin cao/vừa thì áp dụng rồi tìm tiếp (nhiều ô sai độc lập, như VHM quý 4/2025). Nhóm phương án ngang
    nhau thì trả về để đọc lại, tạm gác các ràng buộc của nhóm đó và tìm tiếp ở các ràng buộc khác."""
    out = Localization()
    if template is None:
        return out
    statements = copy.deepcopy(statements)
    summed = {(name, c) for name, st in statements.items() for c in st.summed_codes}
    parked: set[str] = set()

    def failures() -> dict[str, Check]:
        return {k: c for k, c in _failures(statements, template).items() if k not in parked}

    def proposal(st_name, code, col, new, fixed) -> Proposal | None:
        loc = _row_index(extracted, st_name, code, col)
        if loc is None:
            return None
        row, label, before = loc
        after_raw = format_like(before, new / statements[st_name].multiplier, sep)
        return Proposal(st_name, code, col, row, label, before, after_raw, new, fixed, digits_changed(before, after_raw))

    for _ in range(MAX_ROUNDS):
        before_fix = failures()
        if not before_fix:
            break
        candidates: list[Proposal] = []
        seen: set[tuple] = set()
        for check in before_fix.values():
            diff = check.lhs - check.rhs
            for st_name, code, col in _cells_of(check, template, statements):
                if (st_name, code) in summed:
                    continue        # ô là tổng của nhiều dòng in cùng mã: không biết dòng nào sai
                st = statements[st_name]
                cur = st.values[code][col]
                for new in (cur - diff, cur + diff):
                    if new == cur or (st_name, code, col, new) in seen:
                        continue
                    seen.add((st_name, code, col, new))
                    units = new / st.multiplier
                    if units != units.to_integral_value():
                        continue    # số in trên BCTC là số nguyên theo đơn vị tính
                    st.values[code][col] = new
                    after_fix = failures()
                    if set(after_fix) < set(before_fix):
                        p = proposal(st_name, code, col, new, sorted(set(before_fix) - set(after_fix)))
                        if p:
                            candidates.append(p)
                    else:
                        candidates += _pair_moves(statements, template, failures, before_fix, after_fix,
                                                  (st_name, code, col), new - cur, summed, proposal,
                                                  proposal(st_name, code, col, new, []))
                    st.values[code][col] = cur
        plausible = [p for p in candidates if len(p.fixes) >= 2 or p.digits_changed <= MAX_DIGITS_CHANGED]
        plausible = [p for p in plausible if p.partner is None
                     or (p.digits_changed <= MAX_DIGITS_CHANGED and p.partner.digits_changed <= MAX_DIGITS_CHANGED)]
        if not plausible:
            break
        plausible.sort(key=lambda p: (-len(p.fixes), p.digits_changed))
        best = plausible[0]
        # Phương án ngang: cùng làm khớp đúng tập ràng buộc đó (phương án của ràng buộc khác không cạnh tranh)
        ties = [p for p in plausible[1:] if p.fixes == best.fixes
                and p.digits_changed <= max(best.digits_changed, MAX_DIGITS_CHANGED)]
        if ties:
            group = rank_group([best, *ties])
            for p in group:
                p.alternatives = len(ties)
            out.ambiguous.append(group)
            parked |= {k for p in group for k in p.fixes}
            continue
        out.proposals.append(best)
        statements[best.statement].values[best.code][best.column_kind] = best.value
        if best.partner:
            out.proposals.append(best.partner)
            statements[best.partner.statement].values[best.partner.code][best.partner.column_kind] = best.partner.value
    out.unresolved = sorted(k for k in _failures(statements, template) if k not in parked)
    return out


def _pair_moves(statements, template, failures, before_fix, after_fix, first, delta, summed, proposal, first_p) -> list:
    """Ô thứ nhất đổi một lượng `delta` làm lệch thêm ràng buộc khác: thử đổi thêm một ô thuộc ràng buộc vừa lệch cùng
    lượng đó (cả hai chiều). Giữ khi tổng cộng làm khớp thêm mà không làm lệch ràng buộc nào khác."""
    if first_p is None:
        return []
    out = []
    for key in set(after_fix) - set(before_fix):
        check = after_fix[key]
        for st_name, code, col in _cells_of(check, template, statements):
            if (st_name, code, col) == first or (st_name, code) in summed:
                continue
            st = statements[st_name]
            cur = st.values[code][col]
            for new in (cur + delta, cur - delta):
                st.values[code][col] = new
                both = failures()
                st.values[code][col] = cur
                if set(both) < set(before_fix):
                    fixed = sorted(set(before_fix) - set(both))
                    p2 = proposal(st_name, code, col, new, fixed)
                    if p2:
                        p1 = Proposal(**{**first_p.__dict__, "fixes": fixed})
                        p1.partner = p2
                        out.append(p1)
    return out


def loglik(p: Proposal, table: dict | None = None) -> float:
    """log xác suất ô (và ô đi kèm) bị đọc thành số đang thấy nếu số đúng là số đề xuất."""
    return sum(log_likelihood(q.before, q.after, table) for q in (p, p.partner) if q is not None)


def rank_group(group: list[Proposal], table: dict | None = None) -> list[Proposal]:
    """Xếp nhóm phương án ngang nhau theo xác suất nhầm (cao trước) và gán xác suất chuẩn hóa trong nhóm."""
    scored = sorted(((loglik(p, table), i, p) for i, p in enumerate(group)), key=lambda x: (-x[0], x[1]))
    top = scored[0][0]
    weights = [math.exp(ll - top) for ll, _, _ in scored]
    for w, (_, _, p) in zip(weights, scored):
        p.prob = w / sum(weights)
    return [p for _, _, p in scored]


def proposal_dict(p: Proposal) -> dict:
    return {"statement": p.statement, "code": p.code, "column_kind": p.column_kind, "row": p.row, "label": p.label,
            "before": p.before, "after": p.after, "fixes": p.fixes, "digits_changed": p.digits_changed,
            "alternatives": p.alternatives, "confidence": p.confidence, "prob": round(p.prob, 4),
            "partner": proposal_dict(p.partner) if p.partner else None}


def agrees(proposal: Proposal | dict, reread_raw: str | None, sep: str, multiplier: Decimal) -> bool:
    """Lần đọc lại riêng ô ra đúng số đề xuất: cùng dãy chữ số và cùng dấu. Không so theo giá trị vì lần đọc lại có
    thể viết dấu phân tách kiểu khác ("724,006" trong tài liệu dùng dấu chấm, VHM quý 4/2025)."""
    after = proposal.after if isinstance(proposal, Proposal) else proposal["after"]
    before = proposal.before if isinstance(proposal, Proposal) else proposal["before"]
    if not reread_raw or not _digits(reread_raw):
        return False
    if _digits(reread_raw).lstrip("0") != _digits(after).lstrip("0"):
        return False
    # Dấu: khớp đề xuất, hoặc lần đọc lại bỏ mất dấu ngoặc trong khi đề xuất giữ nguyên dấu của ô cũ
    return _negative(reread_raw) == _negative(after) or (not _negative(reread_raw) and _negative(after) == _negative(before))


def _negative(raw: str | None) -> bool:
    return (raw or "").strip().startswith(("(", "-"))


EQUALITY_KINDS = ("bs_begin", "same_date", "year_start")


def cross_proposals(evidence, extracted: list[ExtractedStatement], statements: dict[str, Statement], sep: str,
                    template: str | None, taken: set[tuple[str, int, str]] = frozenset()) -> list[list[Proposal]]:
    """Đề xuất từ đối chiếu với BCTC khác của cùng công ty (evidence.document_evidence): số đầu năm bằng số đầu năm
    của quý trước, quý = lũy kế − lũy kế quý trước, quý 2 bằng bán niên, đầu năm bằng cuối năm trước.

    Chỉ dùng các chỗ lệch bị nghi đọc sai (PeriodCheck.suspect_misread), vì chênh giữa hai bản có thể là công ty hoặc
    kiểm toán sửa số thật. Số mới phải khác số cũ tối đa MAX_DIGITS_CHANGED chữ số và không làm lệch thêm ràng buộc
    nào của chính BCTC. Mỗi chỗ lệch cho một nhóm (ô của tài liệu này có thể sửa được); đọc lại sẽ chọn."""
    if evidence is None or template is None:
        return []
    me = evidence.cells.document_id
    base = set(_failures(statements, template))
    groups: list[list[Proposal]] = []
    for pc in evidence.period_checks:
        if not pc.suspect_misread:
            continue
        options = []                                    # (ô của tài liệu này, số mới)
        later_cell = pc.cells[0]
        if later_cell[0] == me:
            options.append((later_cell, pc.expected))
            if pc.kind == "is_quarter":                 # hoặc ô lũy kế của chính tài liệu sau sai
                ytd = pc.cells[1]
                cur = evidence.cells.values.get((ytd[1], ytd[2]), {}).get(ytd[3])
                if cur is not None:
                    options.append((ytd, cur + pc.later - pc.expected))
        if pc.kind in EQUALITY_KINDS and pc.cells[1][0] == me:
            options.append((pc.cells[1], pc.later))
        group = []
        for (_, st_name, key, col), new in options:
            keys = evidence.cells.item_keys.get(st_name, [])
            if key not in keys:
                continue
            row = keys.index(key)
            if (st_name, row, col) in taken:
                continue
            ex = next((e for e in extracted if e.statement == st_name), None)
            st = statements.get(st_name)
            if ex is None or st is None or row >= len(ex.items):
                continue
            code = normalize_code(ex.items[row].code)
            if code is None or code not in st.values or col not in st.values[code]:
                continue
            units = new / st.multiplier
            if units != units.to_integral_value():
                continue
            before = ex.items[row].values_raw.get(col)
            after_raw = format_like(before, units, sep)
            n = digits_changed(before, after_raw)
            if n > MAX_DIGITS_CHANGED:
                continue
            cur = st.values[code][col]
            st.values[code][col] = new
            after = set(_failures(statements, template))
            st.values[code][col] = cur
            if not after <= base:
                continue
            fixes = [f"X:{pc.kind}@{pc.column}", *sorted(base - after)]
            group.append(Proposal(st_name, code, col, row, ex.items[row].label, before, after_raw, new, fixes, n))
        if group:
            group = rank_group(group)
            for p in group:
                p.alternatives = len(group) - 1
            groups.append(group)
    return groups
