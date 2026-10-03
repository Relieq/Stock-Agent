"""Chuẩn hóa số liệu trích xuất và kiểm tra ràng buộc kế toán."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from services.extraction.numbers import infer_thousands_sep, normalize_code, parse_amount, unit_multiplier
from services.extraction.rules import RULESETS, TT99_ONLY_BS_CODES, RuleSet


@dataclass
class ExtractedItem:
    code: str | None
    label: str
    values_raw: dict[str, str | None]      # column_kind -> chuỗi in trên BCTC
    note: str | None = None
    page: int | None = None


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


def normalize(extracted: list[ExtractedStatement], default_unit: str | None = None) -> tuple[dict[str, Statement], str]:
    """Đổi chuỗi số về đồng. Dấu phân tách hàng nghìn suy ra chung cho cả tài liệu."""
    sep = infer_thousands_sep(v for st in extracted for it in st.items for v in it.values_raw.values())
    out: dict[str, Statement] = {}
    for st in extracted:
        mult = unit_multiplier(st.unit_raw) or unit_multiplier(default_unit) or Decimal(1)
        norm = out.setdefault(st.statement, Statement(st.statement, mult))
        seen: set[str] = set(norm.values)
        for it in st.items:
            code = normalize_code(it.code)
            if code is None:
                continue
            if code in seen:
                # Dòng lặp lại ở đầu trang sau với cùng số liệu (ví dụ VNM in lại dòng 50) thì bỏ qua
                same = all(parse_amount(raw, sep) is None or parse_amount(raw, sep) * mult == norm.values[code].get(col)
                           for col, raw in it.values_raw.items())
                if not same and code not in norm.duplicate_codes:
                    norm.duplicate_codes.append(code)
                continue
            seen.add(code)
            for col, raw in it.values_raw.items():
                value = parse_amount(raw, sep)
                if value is not None:
                    norm.values.setdefault(code, {})[col] = value * mult
    return out, sep


def expenses_printed_negative(st: Statement) -> bool:
    """KQKD có in chi phí thành số âm không (ví dụ giá vốn "(37.942.073.479.846)").

    Đa số BCTC in chi phí là số dương rồi trừ theo công thức; một số công ty (ví dụ MWG) in chi phí trong ngoặc.
    Bỏ phiếu theo giá vốn (11), chi phí bán hàng (25), chi phí quản lý (26) ở mọi cột.
    """
    votes = [v for code in ("11", "25", "26") for v in st.values.get(code, {}).values() if v != 0]
    return bool(votes) and sum(v < 0 for v in votes) > len(votes) / 2


def _evaluate_rules(ruleset: RuleSet, statements: dict[str, Statement]) -> list[Check]:
    checks: list[Check] = []
    flip_is = "IS" in statements and expenses_printed_negative(statements["IS"])
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
            terms = [(1, c) for _, c in terms]
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
            rhs = sum((sign * st.values.get(c, {}).get(col, Decimal(0)) for sign, c in terms), Decimal(0))
            checks.append(Check(r.id, col, abs(lhs - rhs) <= tolerance, lhs, rhs, tolerance, r.gate, missing))

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
    for name, rs in RULESETS.items():
        checks = [c for c in _evaluate_rules(rs, statements) if c.gate]
        code = rs.total_assets_code
        totals = [c for c in checks if c.rule_id in (f"BS_{code}", f"BS_{code}_eq_440")]
        total_ok[name] = len(totals) > 0 and all(c.passed for c in totals)
        pass_rate[name] = sum(c.passed for c in checks) / len(checks) if checks else 0.0

    matched = [n for n, ok in total_ok.items() if ok]
    if len(matched) == 1:
        return matched[0]
    pool = matched or list(RULESETS)
    best = max(pool, key=lambda n: pass_rate[n])
    return best if pass_rate[best] > 0 else None


def validate(statements: dict[str, Statement], template: str) -> list[Check]:
    return _evaluate_rules(RULESETS[template], statements)


def summarize(checks: list[Check]) -> dict[str, int]:
    gated = [c for c in checks if c.gate]
    return {
        "checks": len(checks),
        "gate_checks": len(gated),
        "gate_failed": sum(not c.passed for c in gated),
        "info_failed": sum(not c.passed for c in checks if not c.gate),
    }
