"""Chuẩn hóa số liệu trích xuất và kiểm tra ràng buộc kế toán."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from services.extraction.numbers import infer_thousands_sep, normalize_code, parse_amount, unit_multiplier
from services.extraction.rules import CORPORATE_TEMPLATES, RULESETS, TT99_ONLY_BS_CODES, RuleSet


@dataclass
class ExtractedItem:
    code: str | None
    label: str
    values_raw: dict[str, str | None]      # column_kind -> chuỗi in trên BCTC
    note: str | None = None
    page: int | None = None
    stt: str | None = None                 # số thứ tự đầu dòng ("I", "1", "a"), dùng cho mẫu không in mã số (ngân hàng)


@dataclass
class ExtractedStatement:
    statement: str                         # BS / IS / CF
    unit_raw: str | None
    items: list[ExtractedItem]


@dataclass
class Statement:
    """Báo cáo đã chuẩn hóa: values[code][column_kind] = số tiền (đồng)."""
    statement: str
    multiplier: Decimal
    values: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    # Mã in trùng trên chính BCTC (ví dụ HPG quý 2/2026 in mã 230 cho cả tài sản sinh học dài hạn lẫn BĐS đầu tư).
    # Giữ dòng đầu tiên; ràng buộc có dùng mã trùng thì kết quả cần xem lại.
    duplicate_codes: list[str] = field(default_factory=list)
    # LCTT: công ty tách một khoản thành nhiều dòng cùng mã (VNM quý 4/2025 in hai dòng 02 khấu hao và phân bổ lợi thế
    # thương mại; MCH in ba dòng 05, hai cặp 23/24). Các dòng chi tiết cùng mã được cộng lại.
    summed_codes: list[str] = field(default_factory=list)


@dataclass
class Check:
    rule_id: str
    column_kind: str
    passed: bool
    lhs: Decimal
    rhs: Decimal
    tolerance: Decimal
    gate: bool
    missing: list[str]

    @property
    def diff(self) -> Decimal:
        return self.lhs - self.rhs


# Dòng tổng của LCTT: in trùng với số khác thì không cộng mà coi là mã trùng cần xem lại
CF_TOTALS = {"08", "20", "30", "40", "50", "60", "70"}


# Mã BCĐKT là dòng tổng hoặc tổng con (vế trái của một ràng buộc) ở mẫu doanh nghiệp: in trùng thì không cộng
BS_SUBTOTALS = {r.lhs for t in CORPORATE_TEMPLATES for r in RULESETS[t].rules if r.statement == "BS"}


def _label(label: str | None) -> str:
    return re.sub(r"[^\w]+", " ", (label or "").lower()).strip()


def normalize(extracted: list[ExtractedStatement], default_unit: str | None = None) -> tuple[dict[str, Statement], str]:
    """Đổi chuỗi số về đồng. Dấu phân tách hàng nghìn suy ra chung cho cả tài liệu."""
    sep = infer_thousands_sep(v for st in extracted for it in st.items for v in it.values_raw.values())
    # Báo cáo không ghi đơn vị (ví dụ KQKD của VCB quý 2/2026) thì dùng đơn vị ghi ở báo cáo khác trong tài liệu
    doc_unit = next((m for st in extracted if (m := unit_multiplier(st.unit_raw)) is not None), None)
    out: dict[str, Statement] = {}
    for st in extracted:
        mult = unit_multiplier(st.unit_raw) or unit_multiplier(default_unit) or doc_unit or Decimal(1)
        norm = out.setdefault(st.statement, Statement(st.statement, mult))
        seen: set[str] = set(norm.values)
        first_label: dict[str, str] = {}
        for it in st.items:
            code = normalize_code(it.code)
            if code is None:
                continue
            if code in seen:
                # Dòng lặp lại ở đầu trang sau với cùng số liệu (ví dụ VNM in lại dòng 50) thì bỏ qua
                same = all(parse_amount(raw, sep) is None or parse_amount(raw, sep) * mult == norm.values.get(code, {}).get(col)
                           for col, raw in it.values_raw.items())
                if same:
                    continue
                # LCTT: nhiều dòng chi tiết cùng mã thì cộng lại. BCĐKT: dòng chi tiết (không phải dòng tổng) tách hai dòng
                # tên khác nhau cùng một mã (VJC quý 2/2026: "Vay ngắn hạn" và "Phải trả thuê tài chính ngắn hạn" đều in
                # mã 321, đúng với dòng 321 "Vay và nợ thuê tài chính" của mẫu) thì cũng cộng lại.
                bs_leaf = (st.statement == "BS" and code.isdigit() and code not in BS_SUBTOTALS
                           and _label(it.label) != first_label.get(code))
                if (st.statement == "CF" and code not in CF_TOTALS) or bs_leaf:
                    for col, raw in it.values_raw.items():
                        value = parse_amount(raw, sep)
                        if value is not None:
                            cell = norm.values.setdefault(code, {})
                            cell[col] = cell.get(col, Decimal(0)) + value * mult
                    if code not in norm.summed_codes:
                        norm.summed_codes.append(code)
                elif code not in norm.duplicate_codes:
                    norm.duplicate_codes.append(code)
                continue
            seen.add(code)
            first_label[code] = _label(it.label)
            for col, raw in it.values_raw.items():
                value = parse_amount(raw, sep)
                if value is not None:
                    norm.values.setdefault(code, {})[col] = value * mult
    return out, sep


def expenses_printed_negative(st: Statement, codes: tuple[str, ...] = ("11", "25", "26")) -> bool:
    """KQKD có in chi phí thành số âm không (ví dụ giá vốn "(37.942.073.479.846)").

    Đa số BCTC in chi phí là số dương rồi trừ theo công thức; một số công ty (ví dụ MWG) in chi phí trong ngoặc.
    Bỏ phiếu theo giá vốn (11), chi phí bán hàng (25), chi phí quản lý (26) ở mọi cột.
    """
    votes = [v for code in codes for v in st.values.get(code, {}).values() if v != 0]
    return bool(votes) and sum(v < 0 for v in votes) > len(votes) / 2


def _evaluate_rules(ruleset: RuleSet, statements: dict[str, Statement]) -> list[Check]:
    checks: list[Check] = []
    flip_is = "IS" in statements and expenses_printed_negative(statements["IS"], ruleset.expense_codes)
    for r in ruleset.rules:
        st = statements.get(r.statement)
        if st is None or r.lhs not in st.values:
            continue
        if r.when_present and r.when_present not in st.values:
            continue
        if r.when_absent and r.when_absent in st.values:
            continue
        terms = list(r.rhs)
        if r.statement == "IS" and flip_is:
            # Chi phí đã mang dấu âm khi in: cộng thẳng thay vì trừ
            terms = [(sign if c in r.abs_codes else 1, c) for sign, c in terms]
        if r.include_suffixed:
            signs = {c: sign for sign, c in r.rhs}
            for code in st.values:
                m = re.fullmatch(r"(\d+)[a-z]", code)
                if m and m.group(1) in signs and code not in signs:
                    terms.append((signs[m.group(1)], code))
        present = [c for _, c in terms if c in st.values]
        if not present:
            continue
        missing = [c for _, c in terms if c not in st.values]
        tolerance = st.multiplier * (len(terms) + 1)   # ±1 đơn vị làm tròn cho mỗi số hạng
        for col, lhs in st.values[r.lhs].items():
            rhs = Decimal(0)
            for sign, c in terms:
                v = st.values.get(c, {}).get(col, Decimal(0))
                rhs += sign * (abs(v) if c in r.abs_codes else v)
            checks.append(Check(r.id, col, abs(lhs - rhs) <= tolerance, lhs, rhs, tolerance, r.gate, missing))

    extras = dict(ruleset.group_extra)
    for name in ruleset.group_statements:
        st = statements.get(name)
        if st is None:
            continue
        for parent in sorted(st.values):
            kids = [c for c in st.values if c.startswith(parent + ".") and "." not in c[len(parent) + 1:]]
            if not kids:
                continue
            tolerance = st.multiplier * (len(kids) + 2)
            gate = any(parent == g or parent.startswith(g + ".") for g in ruleset.group_gate)
            for col, lhs in st.values[parent].items():
                rhs = sum((st.values[c].get(col, Decimal(0)) for c in kids), Decimal(0))
                options = [rhs] + [rhs + st.values[e].get(col, Decimal(0)) for e in extras.get(parent, ()) if e in st.values]
                best = min(options, key=lambda v: abs(lhs - v))
                checks.append(Check(f"{name}_grp_{parent}", col, abs(lhs - best) <= tolerance, lhs, best, tolerance,
                                    gate, []))

    for x in ruleset.cross_rules:
        (ls, lc, lcol), (rs, rc, rcol) = x.left, x.right
        lv = statements.get(ls, Statement(ls, Decimal(1))).values.get(lc, {}).get(lcol)
        rv = statements.get(rs, Statement(rs, Decimal(1))).values.get(rc, {}).get(rcol)
        if lv is None or rv is None:
            continue
        tolerance = max(statements[ls].multiplier, statements[rs].multiplier) * 2
        checks.append(Check(x.id, f"{lcol}~{rcol}", abs(lv - rv) <= tolerance, lv, rv, tolerance, x.gate, []))
    return checks


def detect_template(statements: dict[str, Statement]) -> str | None:
    """Chọn mẫu DN thường (TT200/TT99) theo nội dung, không suy từ năm.

    Có mã chỉ TT99 mới có (160, 280) thì là TT99. Nếu không, tín hiệu chính: mã nào vừa bằng tổng nguồn vốn (440) vừa bằng 100 + 200 thì là mã tổng tài sản
    (TT200: 270, TT99: 280). Nếu cả hai hoặc không mẫu nào khớp thì chọn mẫu có tỷ lệ ràng buộc bắt buộc
    đạt cao hơn. Tên chỉ tiêu chưa dùng (xem architecture.md mục 4.2: BCTC thực tế có thể ghi sai mã).
    """
    if "BS" not in statements:
        return None
    # Cấu trúc trước, mã tổng sau: BCTC có thể theo TT99 nhưng vẫn in tổng tài sản là 270 (ví dụ HPG quý 2/2026)
    if any(code in statements["BS"].values for code in TT99_ONLY_BS_CODES):
        return "TT99"
    total_ok, pass_rate = {}, {}
    for name in CORPORATE_TEMPLATES:
        rs = RULESETS[name]
        checks = [c for c in _evaluate_rules(rs, statements) if c.gate]
        code = rs.total_assets_code
        totals = [c for c in checks if c.rule_id in (f"BS_{code}", f"BS_{code}_eq_440")]
        total_ok[name] = len(totals) > 0 and all(c.passed for c in totals)
        pass_rate[name] = sum(c.passed for c in checks) / len(checks) if checks else 0.0

    matched = [n for n, ok in total_ok.items() if ok]
    if len(matched) == 1:
        return matched[0]
    pool = matched or list(CORPORATE_TEMPLATES)
    best = max(pool, key=lambda n: pass_rate[n])
    return best if pass_rate[best] > 0 else None


def validate(statements: dict[str, Statement], template: str) -> list[Check]:
    return _evaluate_rules(RULESETS[template], statements)


def group_rule_codes(rule_id: str, codes_of: dict[str, set[str]], template: str | None) -> tuple[str, list[str]] | None:
    """Ô tham gia một phép kiểm nhóm "dòng cha = tổng dòng con" (mã rule "{báo cáo}_grp_{dòng cha}"): dòng cha, các dòng
    con trực tiếp và số hạng phụ (group_extra). None nếu không phải phép kiểm nhóm."""
    statement, sep, parent = rule_id.partition("_grp_")
    if not sep or statement not in codes_of:
        return None
    codes = codes_of[statement]
    kids = [c for c in codes if c.startswith(parent + ".") and "." not in c[len(parent) + 1:]]
    extra = dict(RULESETS[template].group_extra).get(parent, ()) if template in RULESETS else ()
    return statement, [parent, *kids, *(e for e in extra if e in codes)]


def summarize(checks: list[Check]) -> dict[str, int]:
    gated = [c for c in checks if c.gate]
    return {
        "checks": len(checks),
        "gate_checks": len(gated),
        "gate_failed": sum(not c.passed for c in gated),
        "info_failed": sum(not c.passed for c in checks if not c.gate),
    }
