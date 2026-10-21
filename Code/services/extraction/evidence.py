"""Bằng chứng cho từng ô số: ô đã được kiểm bằng cách nào, có mâu thuẫn ở đâu.

Hai nguồn bằng chứng, đều không gọi mô hình:
  * cộng tổng: ô nằm trong một ràng buộc kế toán đã đạt (lhs = tổng các mã ở rhs) của chính tài liệu;
  * giữa các kỳ: cùng một con số in trên hai BCTC khác nhau, đọc độc lập từ hai bộ ảnh khác nhau, phải khớp:
      - BCĐKT: cột "đầu năm" của mọi quý trong cùng năm tài chính là cùng một ngày (01/01), phải bằng nhau;
      - KQKD: quý n = lũy kế quý n - lũy kế quý n-1, cho cả năm nay (q_cur) lẫn năm trước (q_prev_year);
      - BCTC quý 2 với BCTC bán niên, quý 4 với BCTC năm (cùng ngày kết thúc kỳ): mọi cột của BCĐKT, lũy kế của KQKD
        và LCTT phải bằng nhau. Đây là nguồn duy nhất phủ được LCTT và cột cuối kỳ của BCĐKT.
    Hai lần đọc độc lập cùng sai thành một con số giống hệt nhau là rất khó, nên khớp giữa các kỳ là bằng chứng mạnh,
    và bắt được cả ô không thuộc ràng buộc cộng tổng nào.

Nguồn thứ ba cho ô chưa có hai nguồn trên (services/extraction/second_read.py): một mô hình khác hãng chép lại cả báo
cáo; hai lần đọc trùng nhau là bằng chứng yếu hơn phép kiểm, khác nhau thì ô cần xem lại nhưng không chặn BCTC.

Ô được nhận diện theo mã số (doanh nghiệp thường, CTCK) hoặc mã chuẩn b.* (ngân hàng); dòng không có mã thì theo tên
chỉ tiêu đã bỏ dấu. Số liệu năm trước BCTC ghi "trình bày lại" thì lệch giữa các kỳ được ghi là trình bày lại, không
coi là lỗi đọc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from services.extraction.bank import clean_label, fold
from services.extraction.numbers import normalize_code, parse_amount
from services.extraction.pipeline import _check_cached
from services.extraction.rules import RULESETS
from services.extraction.validate import group_rule_codes, missing_required

EPS = re.compile(r"(lai|lo).*tren (mot )?co phieu")
RESTATED = re.compile(r"trình bày lại|điều chỉnh lại|restated", re.IGNORECASE)
PERIOD_ORDER = ("Q1", "Q2", "Q3", "Q4")


@dataclass
class Cells:
    """Số liệu một tài liệu theo ô: values[(báo cáo, khóa)][cột] = số (đồng)."""
    document_id: int
    period: str
    values: dict[tuple[str, str], dict[str, Decimal]]
    labels: dict[tuple[str, str], str]
    multiplier: dict[str, Decimal]
    restated: set[tuple[str, str]]                   # (báo cáo, cột) có tiêu đề "trình bày lại"
    item_keys: dict[str, list[str | None]] = field(default_factory=dict)   # khóa của từng dòng theo thứ tự chép
    sum_evidence: dict[tuple[str, str, str], list[str]] = field(default_factory=dict)
    sum_conflicts: dict[tuple[str, str, str], list[str]] = field(default_factory=dict)
    verified: set[tuple[str, str, str]] = field(default_factory=set)   # ô đọc lại ở ảnh nét hơn vẫn ra như cũ
    # Lãi trên cổ phiếu (đồng, không theo đơn vị của bảng): không đưa vào phép cộng hay đối chiếu kỳ (quý không bằng
    # lũy kế trừ lũy kế, số kỳ trước hay được tính lại theo số cổ phiếu mới), chỉ so với lần đọc thứ hai
    eps: dict[tuple[str, str], dict[str, Decimal]] = field(default_factory=dict)
    template: str | None = None
    # Ô hai lần đọc khác nhau mà người duyệt đã đối chiếu ảnh và xác nhận lần đọc đầu đúng: ô -> số lúc xác nhận
    image_confirmed: dict[tuple[str, str, str], Decimal] = field(default_factory=dict)
    printed: set[tuple[str, str]] = field(default_factory=set)   # (báo cáo, mã hoặc tên đã bỏ dấu) của mọi dòng đã chép
    required_missing: list[tuple[str, str, str]] = field(default_factory=list)   # validate.missing_required

    def row(self, st: str, key: str) -> dict[str, Decimal]:
        return self.values.get((st, key)) or self.eps.get((st, key), {})


def label_key(label: str) -> str:
    return "~" + fold(clean_label(label))


def cells_of(document_id: int, period: str, record: dict) -> Cells:
    extracted, statements, sep, template, checks = _check_cached(record)
    values: dict[tuple[str, str], dict[str, Decimal]] = {}
    labels: dict[tuple[str, str], str] = {}
    item_keys: dict[str, list[str | None]] = {}
    printed: set[tuple[str, str]] = set()
    eps: dict[tuple[str, str], dict[str, Decimal]] = {}
    mult = {st: s.multiplier for st, s in statements.items()}
    for ex in extracted:
        st = ex.statement
        m = mult.get(st, Decimal(1))
        seen_labels: dict[str, int] = {}
        keys = item_keys.setdefault(st, [])
        for it in ex.items:
            keys.append(None)
            code = normalize_code(it.code)
            printed.add((st, fold(clean_label(it.label))))
            printed.add((st, row_name(it.label)))
            if code:
                printed.add((st, code))
            if EPS.search(fold(clean_label(it.label))):
                # lãi trên cổ phiếu tính bằng đồng, không theo đơn vị của bảng
                base = "eps" + (code or label_key(it.label))
                seen_labels[base] = seen_labels.get(base, 0) + 1
                key = base if seen_labels[base] == 1 else f"{base}#{seen_labels[base]}"
                vals = {col: v for col, raw in it.values_raw.items() if (v := parse_amount(raw, sep)) is not None}
                if vals:
                    eps[(st, key)] = vals
                    labels[(st, key)] = it.label
                    keys[-1] = key
                continue
            if code:
                key = code
                if (st, key) in values:
                    continue
                vals = statements[st].values.get(code, {}) if st in statements else {}
            else:
                base = label_key(it.label)
                seen_labels[base] = seen_labels.get(base, 0) + 1
                key = base if seen_labels[base] == 1 else f"{base}#{seen_labels[base]}"
                vals = {col: v * m for col, raw in it.values_raw.items() if (v := parse_amount(raw, sep)) is not None}
            if vals:
                values[(st, key)] = dict(vals)
                labels[(st, key)] = it.label
                keys[-1] = key
    restated = {(st, c.get("kind")) for st, raw in record["raw"].items() for c in raw.get("columns", [])
                if RESTATED.search(c.get("header") or "")}
    cells = Cells(document_id, period, values, labels, mult, restated, item_keys, eps=eps, template=template, printed=printed,
                  required_missing=missing_required(statements, template))
    cells.verified = {(v["statement"], v["key"], v["column_kind"]) for v in record.get("cell_verifications", [])
                      if v.get("same")}
    cells.image_confirmed = {(c["statement"], c["key"], c["column"]): Decimal(c["value"])
                             for c in record.get("image_confirmed", [])}

    rules = {r.id: r for r in RULESETS[template].rules} if template else {}
    crosses = {x.id: x for x in RULESETS[template].cross_rules} if template else {}
    codes_of: dict[str, set[str]] = {}
    for st_name, code in values:
        codes_of.setdefault(st_name, set()).add(code)
    for c in checks:
        if c.rule_id in rules:
            r = rules[c.rule_id]
            touched = [(r.statement, code, c.column_kind) for code in (r.lhs, *(t for _, t in r.rhs))
                       if (r.statement, code) in values]
        elif c.rule_id in crosses:
            (ls, lc, lcol), (rs, rc, rcol) = crosses[c.rule_id].left, crosses[c.rule_id].right
            touched = [(ls, lc, lcol), (rs, rc, rcol)]
        elif (grp := group_rule_codes(c.rule_id, codes_of, template)) is not None:
            touched = [(grp[0], code, c.column_kind) for code in grp[1] if (grp[0], code) in values]
        else:
            continue
        target = cells.sum_evidence if c.passed else (cells.sum_conflicts if c.gate else None)
        if target is None:
            continue
        for cell in touched:
            target.setdefault(cell, []).append(c.rule_id)
    return cells


@dataclass
class PeriodCheck:
    kind: str                  # bs_begin / is_quarter / same_date
    statement: str
    key: str
    column: str                # cột của tài liệu sau
    later: Decimal
    expected: Decimal          # tính từ tài liệu trước (và chính tài liệu sau với KQKD)
    passed: bool
    restated: bool
    cells: list[tuple[int, str, str, str]]   # (document_id, báo cáo, khóa, cột) liên quan
    # Mọi ô liên quan đều nằm trong ràng buộc cộng tổng đã đạt của chính tài liệu chứa nó: các số thực sự được in như
    # vậy, nên lệch là do hai BCTC khác nhau thật (soát xét điều chỉnh, phân loại lại), không phải đọc sai
    consistent: bool = False
    # Mọi ô liên quan đã được đọc lại riêng ở ảnh nét hơn (verify.py) và vẫn ra như lần đầu: hai lần đọc trùng nhau
    verified: bool = False

    @property
    def suspect_misread(self) -> bool:
        """Lệch cần xem lại ảnh (có thể đọc sai), phân biệt với hai BCTC khác nhau thật.

        Lệch 1-2 chữ số luôn cần xem: thường là đọc sai, nhưng bản soát xét cũng có thể sửa đúng vài chữ số
        (FPT quý 2 so với bán niên 2026, mã 311: chênh 100.000 đồng, cả hai bản đều in đúng như đã đọc). Ngoài ra: giữa hai quý (số đầu năm, quý = lũy kế - lũy kế) mà không ghi
        trình bày lại thì nghi đọc sai, vì BCTC quý hiếm khi tự đổi số kỳ trước; còn quý 2 khác bán niên/quý 4 khác
        năm một khoản lớn là chuyện thường (soát xét, kiểm toán điều chỉnh) nên coi là khác thật.
        """
        if self.passed or self.restated or self.verified:
            return False
        if digit_slip(self.later, self.expected):
            return True
        return not self.consistent and self.kind not in ("same_date", "year_start")

    @property
    def diff(self) -> Decimal:
        return self.later - self.expected


def _same(st: str, a: Decimal, b: Decimal, tol: Decimal) -> bool:
    """KQKD: hai BCTC có thể dùng quy ước dấu chi phí khác nhau (VRE: bản quý in chi phí âm, bản bán niên in dương)."""
    return abs(a - b) <= tol or (st == "IS" and abs(abs(a) - abs(b)) <= tol)


def digit_slip(a: Decimal, b: Decimal) -> bool:
    """Dấu hiệu đọc sai chữ số, không phải điều chỉnh số liệu: hai số cùng số chữ số và khác nhau ở tối đa 2 vị trí, hoặc
    một số thừa đúng một chữ số so với số kia (STB quý 4/2025: "15,980,444" nằm dưới con dấu được đọc thành "5,980,444";
    trước đây coi là hai số khác thật nên không đọc lại)."""
    x, y = str(abs(int(a))), str(abs(int(b)))
    if len(x) == len(y):
        return sum(c != d for c, d in zip(x, y)) <= 2
    if abs(len(x) - len(y)) == 1:
        long, short = (x, y) if len(x) > len(y) else (y, x)
        return any(long[:i] + long[i + 1:] == short for i in range(len(long)))
    return False


def _mark_consistency(checks: list[PeriodCheck], *docs: Cells) -> list[PeriodCheck]:
    by_id = {d.document_id: d for d in docs}
    for pc in checks:
        pc.consistent = all((st, key, col) in by_id[doc_id].sum_evidence for doc_id, st, key, col in pc.cells)
        pc.verified = all((st, key, col) in by_id[doc_id].verified for doc_id, st, key, col in pc.cells)
    return checks


def compare_periods(earlier: Cells, later: Cells) -> list[PeriodCheck]:
    """Đối chiếu hai BCTC quý liên tiếp trong cùng năm tài chính (earlier là quý trước của later)."""
    out: list[PeriodCheck] = []

    def tol(st: str) -> Decimal:
        return max(earlier.multiplier.get(st, Decimal(1)), later.multiplier.get(st, Decimal(1))) * 3

    for (st, key), lv in later.values.items():
        ev = earlier.values.get((st, key))
        if ev is None:
            continue
        if st == "BS" and "begin_year" in lv and "begin_year" in ev:
            a, b = lv["begin_year"], ev["begin_year"]
            out.append(PeriodCheck("bs_begin", st, key, "begin_year", a, b, _same(st, a, b, tol(st)),
                                   (st, "begin_year") in later.restated or (st, "begin_year") in earlier.restated,
                                   [(later.document_id, st, key, "begin_year"), (earlier.document_id, st, key, "begin_year")]))
        if st == "IS":
            for q, ytd in (("q_cur", "ytd_cur"), ("q_prev_year", "ytd_prev_year")):
                # Lũy kế của quý trước; BCTC quý 1 có thể không in cột lũy kế (lũy kế = quý)
                e_ytd_col = ytd if ytd in ev else (q if earlier.period == "Q1" and q in ev else None)
                if q not in lv or ytd not in lv or e_ytd_col is None:
                    continue
                expected = lv[ytd] - ev[e_ytd_col]
                passed = abs(lv[q] - expected) <= tol(st) * 2 or                     abs(lv[q] - (lv[ytd] + ev[e_ytd_col])) <= tol(st) * 2 and lv[q] * lv[ytd] >= 0 > lv[ytd] * ev[e_ytd_col]
                out.append(PeriodCheck("is_quarter", st, key, q, lv[q], expected, passed,
                                       any((st, c) in s.restated for c in (q, ytd) for s in (earlier, later)),
                                       [(later.document_id, st, key, q), (later.document_id, st, key, ytd),
                                        (earlier.document_id, st, key, e_ytd_col)]))
    return _mark_consistency(out, earlier, later)


def compare_same_date(quarter: Cells, period_report: Cells) -> list[PeriodCheck]:
    """Đối chiếu BCTC quý với BCTC cùng ngày kết thúc kỳ: quý 2 với bán niên (30/06), quý 4 với năm (31/12).

    BCĐKT: cả hai cột phải bằng nhau. KQKD và LCTT: lũy kế của BCTC quý bằng số cả kỳ của BCTC bán niên/năm (bản này
    có thể chỉ có một cặp cột, mô hình có thể gán là q_* hoặc ytd_*). Lệch có thể do đọc sai hoặc do soát xét/kiểm toán
    điều chỉnh số liệu; cả hai đều cần người xem.
    """
    out: list[PeriodCheck] = []
    pairs = {"BS": (("end_period", ("end_period",)), ("begin_year", ("begin_year",))),
             "IS": (("ytd_cur", ("ytd_cur", "q_cur")), ("ytd_prev_year", ("ytd_prev_year", "q_prev_year"))),
             "CF": (("ytd_cur", ("ytd_cur", "q_cur")), ("ytd_prev_year", ("ytd_prev_year", "q_prev_year")))}
    for (st, key), qv in quarter.values.items():
        pv = period_report.values.get((st, key))
        if pv is None:
            continue
        tol = max(quarter.multiplier.get(st, Decimal(1)), period_report.multiplier.get(st, Decimal(1))) * 3
        for col, other_cols in pairs.get(st, ()):
            other = next((c for c in other_cols if c in pv), None)
            if col not in qv or other is None:
                continue
            out.append(PeriodCheck("same_date", st, key, col, qv[col], pv[other], _same(st, qv[col], pv[other], tol),
                                   (st, col) in quarter.restated or (st, other) in period_report.restated,
                                   [(quarter.document_id, st, key, col), (period_report.document_id, st, key, other)]))
    return _mark_consistency(out, quarter, period_report)


def compare_year_start(year_end: Cells, next_q1: Cells) -> list[PeriodCheck]:
    """Số cuối kỳ của BCTC quý 4 năm trước với số đầu năm của BCTC quý 1 năm sau (cùng ngày 31/12). BCTC năm đã kiểm
    toán có thể điều chỉnh số quý 4, nên chênh lớn là chuyện thường như quý 2 với bán niên."""
    out: list[PeriodCheck] = []
    for (st, key), qv in next_q1.values.items():
        if st != "BS" or "begin_year" not in qv:
            continue
        ev = year_end.values.get((st, key), {})
        if "end_period" not in ev:
            continue
        tol = max(year_end.multiplier.get(st, Decimal(1)), next_q1.multiplier.get(st, Decimal(1))) * 3
        a, b = qv["begin_year"], ev["end_period"]
        out.append(PeriodCheck("year_start", st, key, "begin_year", a, b, _same(st, a, b, tol),
                               (st, "begin_year") in next_q1.restated,
                               [(next_q1.document_id, st, key, "begin_year"), (year_end.document_id, st, key, "end_period")]))
    return _mark_consistency(out, year_end, next_q1)


# Trạng thái một ô, từ mạnh đến yếu
STATUS_LABELS = {
    "conflict": "Cần xem lại",
    "differs": "Hai BCTC in khác nhau (công ty hoặc kiểm toán đã sửa số)",
    "both": "Khớp cộng tổng và giữa các kỳ",
    "period": "Khớp giữa các kỳ",
    "sum": "Khớp cộng tổng",
    "restated": "Khác kỳ trước do trình bày lại",
    "second": "Chưa có phép kiểm; hai lần đọc độc lập trùng nhau",
    "second_differs": "Chưa có phép kiểm; hai lần đọc khác nhau, cần xem lại",
    "image_ok": "Hai lần đọc khác nhau; người duyệt đã đối chiếu ảnh, lần đọc đầu đúng",
    "none": "Chưa kiểm được",
}

# BCTC bán niên/năm chỉ in một cặp cột cả kỳ; mỗi lần chép có thể ghi vào q_* hoặc ytd_*
TWIN = {"q_cur": "ytd_cur", "ytd_cur": "q_cur", "q_prev_year": "ytd_prev_year", "ytd_prev_year": "q_prev_year"}


def second_value(cells: Cells, theirs: Cells, cell: tuple[str, str, str], doc_type: str | None) -> Decimal | None:
    """Số người đọc thứ hai chép cho ô `cell` của `cells` (None nếu không thấy)."""
    st, key, col = cell
    got = theirs.row(st, key)
    b = got.get(col)
    if b is None and doc_type in ("fs_semiannual", "fs_annual") and col in TWIN:
        b = got.get(TWIN[col])
    return b


def same_reading(a: Decimal, b: Decimal) -> bool:
    """Hai lần đọc ra cùng một số, kể cả cùng dãy chữ số nhưng hiểu đơn vị tính khác nhau (đơn vị là việc của code,
    không phải lỗi đọc chữ số; lệch đơn vị cả bảng đã có phép kiểm riêng)."""
    return a == b or (b != 0 and any(a == b * Decimal(1000) ** k or b == a * Decimal(1000) ** k for k in (1, 2, 3)))


def cell_status(cells: Cells, period_checks: list[PeriodCheck], second: Cells | None = None,
                doc_type: str | None = None) -> dict[tuple[str, str, str], dict]:
    """Trạng thái từng ô (báo cáo, khóa, cột) của tài liệu `cells`. `second`: lần đọc thứ hai của chính tài liệu này,
    chỉ dùng cho ô không có phép kiểm nào."""
    period_ok: dict[tuple, list[str]] = {}
    period_bad: dict[tuple, list[str]] = {}
    period_restated: set[tuple] = set()
    period_differs: dict[tuple, list[str]] = {}
    for pc in period_checks:
        desc = f"{pc.kind}:{pc.key}:{pc.column}"
        for doc_id, st, key, col in pc.cells:
            if doc_id != cells.document_id:
                continue
            cell = (st, key, col)
            if pc.passed:
                period_ok.setdefault(cell, []).append(desc)
            elif pc.restated:
                period_restated.add(cell)
            elif not pc.suspect_misread:
                period_differs.setdefault(cell, []).append(desc)
            else:
                period_bad.setdefault(cell, []).append(desc)

    out = {}
    for (st, key), vals in cells.values.items():
        for col in vals:
            cell = (st, key, col)
            sums, bad_sum = cells.sum_evidence.get(cell, []), cells.sum_conflicts.get(cell, [])
            per, bad_per = period_ok.get(cell, []), period_bad.get(cell, [])
            if bad_sum or bad_per:
                status = "conflict"
            elif cell in period_differs:
                status = "differs"
            elif sums and per:
                status = "both"
            elif per:
                status = "period"
            elif sums:
                status = "sum"
            elif cell in period_restated:
                status = "restated"
            else:
                status = "none"
            entry = {"status": status, "sum": sums, "period": per, "conflict": bad_sum + bad_per,
                     "differs": period_differs.get(cell, [])}
            if status == "none" and second is not None:
                b = second_value(cells, second, cell, doc_type)
                if b is not None:
                    entry["status"] = "second" if same_reading(vals[col], b) else "second_differs"
                    if entry["status"] == "second_differs" and cells.image_confirmed.get(cell) == vals[col]:
                        entry["status"] = "image_ok"
                    entry["second"] = str(b)
                    printed = b / cells.multiplier.get(st, Decimal(1))      # theo đơn vị in trên BCTC, để hiện trên web
                    entry["second_printed"] = (f"{printed:,.0f}".replace(",", ".") if printed == printed.to_integral()
                                               else str(printed))
            out[cell] = entry
    for (st, key), vals in cells.eps.items():
        for col, a in vals.items():
            cell = (st, key, col)
            entry = {"status": "none", "sum": [], "period": [], "conflict": [], "differs": []}
            # Quý 1: số quý và số lũy kế là hai cột in riêng của cùng một con số
            twin = vals.get(TWIN.get(col, "")) if cells.period == "Q1" and doc_type in (None, "fs_quarter") else None
            if twin is not None:
                if twin == a:
                    entry.update(status="sum", sum=["Q1: quý = lũy kế"])
                else:
                    entry.update(status="conflict", conflict=["Q1: quý ≠ lũy kế"])
                out[cell] = entry
                continue
            b = second_value(cells, second, cell, doc_type) if second is not None else None
            if b is not None:
                entry["status"] = "second" if a == b else "second_differs"
                if entry["status"] == "second_differs" and cells.image_confirmed.get(cell) == a:
                    entry["status"] = "image_ok"
                entry["second"], entry["second_printed"] = str(b), f"{b:,.0f}".replace(",", ".")
            out[cell] = entry
    return out


# BCTC quý và BCTC cùng ngày kết thúc kỳ: (kỳ quý, loại BCTC cả kỳ, kỳ của BCTC cả kỳ)
@dataclass
class MissingRow:
    """Dòng tài liệu này lẽ ra phải có nhưng không thấy: theo mẫu biểu, hoặc vì BCTC khác của cùng công ty in khác 0 ở
    dòng đó một con số mà tài liệu này cũng phải in (cùng ngày, hoặc lũy kế kỳ trước nằm trong lũy kế kỳ này)."""
    statement: str
    key: str
    label: str
    reason: str                         # "required" (mẫu biểu) / "peer" (BCTC khác)
    peer_id: int | None = None
    peer_period: str | None = None
    peer_column: str | None = None
    peer_value: Decimal | None = None
    by_value: bool = False              # đã tìm cả theo con số (cột phải in cùng số với BCTC đối chiếu)

    def describe(self) -> str:
        """Viết cho người duyệt."""
        name = f'{STATEMENT_NAMES.get(self.statement, self.statement)}: dòng "{self.label.strip()}"'
        if self.reason == "required":
            return f"{name} bắt buộc theo mẫu biểu nhưng không thấy trong bản đã đọc"
        amount = f"{abs(self.peer_value) / Decimal(10**9):,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return (f"{name} có ở BCTC {self.peer_period} ({COLUMN_NAMES.get(self.peer_column, self.peer_column)} {amount} "
                f"tỷ) nhưng bản này không có dòng nào cùng mã{', cùng tên hay cùng số' if self.by_value else ' hay cùng tên'}; "
                f"có thể đọc sót, hoặc công ty đổi cách trình bày")


STATEMENT_NAMES = {"BS": "Cân đối kế toán", "IS": "Kết quả kinh doanh", "CF": "Lưu chuyển tiền tệ"}
COLUMN_NAMES = {"end_period": "cuối kỳ", "begin_year": "đầu năm", "q_cur": "quý này", "q_prev_year": "cùng kỳ",
                "ytd_cur": "lũy kế", "ytd_prev_year": "lũy kế năm trước"}


# Tên dòng bắt buộc theo mẫu biểu, dùng khi tài liệu không có dòng đó để lấy tên
REQUIRED_NAMES = {"60": "Lợi nhuận sau thuế thu nhập doanh nghiệp", "61": "Lợi nhuận sau thuế của cổ đông công ty mẹ",
                  "b.npat": "Lợi nhuận sau thuế", "b.npat_parent": "Lợi nhuận sau thuế của cổ đông ngân hàng mẹ",
                  "200": "Lợi nhuận kế toán sau thuế TNDN"}

# Cột của BCTC đối chiếu phải in cùng một con số với tài liệu này, theo quan hệ giữa hai BCTC (xem neighbours): cột đầu
# năm của BCĐKT giữa các quý trong năm; số kỳ này của KQKD, LCTT năm trước là cột cùng kỳ năm trước của năm nay. Quý 2/4
# với bán niên/năm và cuối năm trước với đầu năm nay không dùng: soát xét, kiểm toán hay đổi số và cách trình bày.
PEER_SAME = {
    "earlier": {"BS": ("begin_year",)},
    "later": {"BS": ("begin_year",)},
    "prev_year_same": {"IS": ("q_cur", "ytd_cur"), "CF": ("ytd_cur", "q_cur")},
}
# Lũy kế của quý trước nằm trong lũy kế quý này: dòng KQKD, LCTT đã có số ở quý trước thì quý này cũng phải có dòng đó
# (số có thể khác nên tìm theo mã hoặc tên dòng)
PEER_CONTAINED = {"earlier": {"IS": ("ytd_cur", "q_cur", "ytd_prev_year", "q_prev_year"),
                              "CF": ("ytd_cur", "q_cur", "ytd_prev_year", "q_prev_year")}}


_DIRECTION = re.compile(r"^(?:(?:tang|giam)\s*/?\s*)+")


def row_name(label: str) -> str:
    """Tên dòng bỏ dấu, bỏ chữ chỉ chiều ở đầu: ngân hàng đổi "Tăng/(Giảm) khác về nợ hoạt động" thành "Giảm khác về
    nợ hoạt động" theo dấu của số kỳ đó (LPB quý 2 và quý 3/2026), vẫn là một dòng."""
    return _DIRECTION.sub("", fold(clean_label(label)))


def missing_rows(cells: Cells, peer: Cells, relation: str) -> list[MissingRow]:
    """Dòng của BCTC đối chiếu (đã khớp cộng tổng, số khác 0 ở cột liên quan) mà tài liệu này không có.

    Cột cùng số (PEER_SAME): thiếu khi không có dòng cùng khóa và cũng không dòng nào in đúng con số đó, vì cùng một
    công ty có thể đánh mã khác nhau giữa hai BCTC (TT200/TT99) và đổi chữ trong tên dòng. Cột lũy kế (PEER_CONTAINED):
    thiếu khi không có dòng cùng khóa và không dòng nào cùng tên."""
    out = []
    for (st, key), pv in peer.values.items():
        if (st, key) in cells.values or (st, key) in cells.printed:
            continue
        evidenced = [c for c in pv if pv[c] and (st, key, c) in peer.sum_evidence]
        col = next((c for c in PEER_SAME.get(relation, {}).get(st, ()) if c in evidenced), None)
        by_value = col is not None
        if by_value:
            tol = max(cells.multiplier.get(st, Decimal(1)), peer.multiplier.get(st, Decimal(1))) * 3
            target = abs(pv[col])
            if any(abs(abs(v) - target) <= tol for (s, _), vals in cells.values.items() if s == st for v in vals.values()):
                continue
        else:
            col = next((c for c in PEER_CONTAINED.get(relation, {}).get(st, ()) if c in evidenced), None)
            if col is None or (st, row_name(peer.labels.get((st, key), ""))) in cells.printed:
                continue
        out.append(MissingRow(st, key, peer.labels.get((st, key), key), "peer", peer.document_id, peer.period, col, pv[col],
                              by_value))
    return out


SAME_DATE = {("Q2", "fs_semiannual", "H1"), ("Q4", "fs_annual", "FY")}


def neighbours(conn, document_id: int) -> list[tuple[int, str, str]]:
    """Các BCTC đã đọc dùng để đối chiếu, cùng mã, cùng phạm vi, cùng năm: [(id, kỳ, quan hệ)].

    Quan hệ: "earlier"/"later" = quý liền trước/liền sau; "report" = BCTC cả kỳ cùng ngày kết thúc với quý này
    (bán niên cho quý 2, năm cho quý 4); "quarter" = BCTC quý cùng ngày kết thúc với BCTC cả kỳ này;
    "prev_year_end"/"next_year_start" = quý 4 năm trước / quý 1 năm sau (cuối năm trước là đầu năm nay);
    "prev_year_same" = BCTC cùng kỳ năm trước (chỉ dùng để tìm dòng thiếu, xem missing_rows).
    Kỳ của BCTC khác năm được ghi kèm năm, ví dụ "Q4/2025".
    """
    row = conn.execute("SELECT ticker, scope, fiscal_year, fiscal_period, doc_type FROM documents WHERE id = %s",
                       (document_id,)).fetchone()
    if row is None:
        return []
    ticker, scope, year, period, doc_type = row
    wanted: list[tuple[str, str, str, int]] = []          # (loại BCTC, kỳ, quan hệ, năm)
    if doc_type == "fs_quarter" and period in PERIOD_ORDER:
        i = PERIOD_ORDER.index(period)
        wanted += [("fs_quarter", p, "earlier" if p_i < i else "later", year)
                   for p_i, p in enumerate(PERIOD_ORDER) if abs(p_i - i) == 1]
        wanted += [(t, rp, "report", year) for q, t, rp in SAME_DATE if q == period]
        if period == "Q1":
            wanted.append(("fs_quarter", "Q4", "prev_year_end", year - 1))
        if period == "Q4":
            wanted.append(("fs_quarter", "Q1", "next_year_start", year + 1))
    wanted += [("fs_quarter", q, "quarter", year) for q, t, rp in SAME_DATE if t == doc_type and rp == period]
    wanted.append((doc_type, period, "prev_year_same", year - 1))
    out = []
    for t, p, relation, y in wanted:
        hit = conn.execute(
            """SELECT id FROM documents
               WHERE ticker = %s AND scope = %s AND fiscal_year = %s AND doc_type = %s AND fiscal_period = %s
                 AND content_kind = 'full' AND processed_at IS NOT NULL AND NOT is_amended AND owner_user_id IS NULL
                 AND duplicate_of IS NULL
               ORDER BY source_listed_at DESC LIMIT 1""",
            (ticker, scope, y, t, p)).fetchone()
        if hit:
            out.append((hit[0], p if y == year else f"{p}/{y}", relation))
    return out


@dataclass
class DocumentEvidence:
    cells: Cells
    period_checks: list[PeriodCheck]
    status: dict[tuple[str, str, str], dict]
    peers: list[tuple[int, str, str]]
    missing: list[MissingRow] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out = {k: 0 for k in STATUS_LABELS}
        for s in self.status.values():
            out[s["status"]] += 1
        return out


def document_evidence(conn, document_id: int, load=None, cells_fn=None) -> DocumentEvidence | None:
    """Bằng chứng cho mọi ô của một tài liệu. `load(document_id)` trả về bản ghi trích xuất (mặc định đọc file JSON);
    `cells_fn(document_id, kỳ, bản ghi)` thay cho cells_of khi cần cache."""
    cells_fn = cells_fn or cells_of
    from services.extraction.pipeline import _load_record

    def _load(doc_id: int) -> dict | None:
        if load:
            return load(doc_id)
        try:
            return _load_record(conn, doc_id)
        except RuntimeError:
            return None

    period = conn.execute("SELECT fiscal_period, doc_type FROM documents WHERE id = %s", (document_id,)).fetchone()
    record = _load(document_id)
    if period is None or record is None:
        return None
    cells = cells_fn(document_id, period[0], record)
    second = second_cells(document_id, period[0], record, cells_fn)
    checks: list[PeriodCheck] = []
    missing = [MissingRow(st, code, REQUIRED_NAMES.get(code, code), "required")
               for st, code, _ in cells.required_missing]
    peers = neighbours(conn, document_id)
    for peer_id, peer_period, relation in peers:
        peer_record = _load(peer_id)
        if peer_record is None:
            continue
        peer = cells_fn(peer_id, peer_period, peer_record)
        seen = {(m.statement, m.key) for m in missing}
        missing += [m for m in missing_rows(cells, peer, relation) if (m.statement, m.key) not in seen]
        checks += {"earlier": lambda: compare_periods(peer, cells), "later": lambda: compare_periods(cells, peer),
                   "report": lambda: compare_same_date(cells, peer), "quarter": lambda: compare_same_date(peer, cells),
                   "prev_year_end": lambda: compare_year_start(peer, cells),
                   "next_year_start": lambda: compare_year_start(cells, peer),
                   "prev_year_same": lambda: [],     # chỉ dùng để tìm dòng thiếu
                   }[relation]()
    return DocumentEvidence(cells, checks, cell_status(cells, checks, second, period[1]), peers, missing)


def second_cells(document_id: int, period: str, record: dict, cells_fn=None) -> Cells | None:
    """Ô theo lần đọc thứ hai đã lưu trong bản ghi (record["second_read"]["raw"]), cùng cách nhận diện ô như lần đầu."""
    second = record.get("second_read")
    if not second or not second.get("raw"):
        return None
    other = {k: v for k, v in record.items() if k not in ("second_read", "raw", "cell_verifications")}
    other["raw"] = second["raw"]
    return (cells_fn or cells_of)(document_id, period, other)
