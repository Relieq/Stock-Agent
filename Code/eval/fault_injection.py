"""Cấy lỗi giả vào các ô đang được xác nhận của BCTC đã kiểm chứng rồi đo hệ thống có bắt được không, không gọi mô hình.

    python eval/fault_injection.py [--n 2000] [--seed 20261018] [--no-cross]

Tỷ lệ "được phép kiểm xác nhận" (eval/cell_funnel.py) chỉ cho biết bao nhiêu ô nằm trong phép kiểm. Phép thử này trả lời
câu khác: một lỗi đọc kiểu X xảy ra ở ô đó thì phép kiểm bắt được với xác suất bao nhiêu. Kiểu lỗi cấy:
  * nhầm một chữ số, theo tần suất nhầm thật (confusion.py) học từ một nửa số lỗi đã sửa, lỗi cấy lấy từ nửa còn lại;
  * mất dấu âm (số trong ngoặc chép thành số dương);
  * thiếu một chữ số;
  * đổi chỗ hai dòng (mọi cột) cùng là số hạng của một phép cộng bắt buộc: tổng không đổi nên phép cộng không thấy.
Với mỗi lỗi: (1) phép kiểm bắt buộc trong chính BCTC có lệch thêm không; (2) nếu không, công thức không bắt buộc (tham
khảo) có lệch không; (3) nếu không, đối chiếu với BCTC kỳ khác (evidence.py) có đánh dấu ô không; (4) với lỗi một chữ số, bước định vị lỗi (repair.localize) chỉ ra đúng ô và đúng số
không, và khi ô đúng nằm trong nhóm phương án ngang nhau thì xếp theo mô hình nhầm có đưa nó lên đầu không.
"""

from __future__ import annotations

import argparse
import copy
import random
import re
import sys
from collections import Counter, defaultdict

from eval.cell_funnel import classify
from services.db import connect
from services.extraction.confusion import count_substitutions, error_pairs
from services.extraction.evidence import document_evidence
from services.extraction.numbers import normalize_code
from services.extraction.pipeline import _check, _load_record
from services.extraction.repair import localize, rank_group
from services.extraction.rules import RULESETS

KINDS = ("nhầm một chữ số", "mất dấu âm", "thiếu một chữ số", "đổi chỗ hai dòng cùng một phép cộng")
FLAGGED = ("conflict", "differs", "restated")


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


class Corpus:
    def __init__(self, conn, listed_before: str | None = None):
        self.conn = conn
        self.records: dict[int, dict] = {}
        self.cells: dict[int, list[tuple[str, int, str]]] = {}
        self.base_fail: dict[int, set] = {}
        self.base_soft: dict[int, set] = {}
        pairs = []
        scope = "AND (%s::date IS NULL OR source_listed_at < %s::date)"
        for (d,) in conn.execute("SELECT id FROM documents WHERE owner_user_id IS NULL "
                                 f"AND status IN ('verified', 'approved', 'needs_review') {scope}",
                                 (listed_before, listed_before)):
            pairs += error_pairs(self.load(d))
        for (d,) in conn.execute(f"SELECT id FROM documents WHERE owner_user_id IS NULL AND status = 'verified' {scope} "
                                 "ORDER BY id", (listed_before, listed_before)):
            rec = self.load(d)
            ok = [(st, row, col) for cat, st, row, col, _, _ in classify(conn, d) if cat == 1]
            ok = [x for x in ok if len(_digits(rec["raw"][x[0]]["rows"][x[1]]["values"][x[2]])) >= 4]
            if ok:
                self.cells[d] = ok
                self.base_fail[d] = gate_failures(copy.deepcopy(rec))
                self.base_soft[d] = gate_failures(copy.deepcopy(rec), soft=True)
        self.pairs = pairs

    def load(self, d: int) -> dict | None:
        if d not in self.records:
            try:
                self.records[d] = _load_record(self.conn, d)
            except RuntimeError:
                self.records[d] = None
        return self.records[d]


def gate_failures(record: dict, soft: bool = False) -> set:
    """Ràng buộc bắt buộc đang lệch (soft=True: ràng buộc không bắt buộc, chỉ để tham khảo)."""
    *_, checks = _check(record)
    return {(c.rule_id, c.column_kind) for c in checks if c.gate != soft and not c.passed}


def cross_flagged(corpus: Corpus, d: int, broken: dict, cells: list[tuple[str, int, str]]) -> bool:
    """Đối chiếu kỳ khác đánh dấu ít nhất một ô bị cấy lỗi (lệch, nghi đọc sai hoặc khác số)."""
    ev = document_evidence(corpus.conn, d, load=lambda x: broken if x == d else corpus.load(x))
    if ev is None:
        return False
    for st, row, col in cells:
        keys = ev.cells.item_keys.get(st, [])
        key = keys[row] if row < len(keys) else None
        if key and ev.status.get((st, key, col), {}).get("status") in FLAGGED:
            return True
    return False


def inject_digit(raw: str, gen: dict[str, list[str]], rng: random.Random) -> str | None:
    first = next(i for i, ch in enumerate(raw) if ch.isdigit())
    pos = [i for i, ch in enumerate(raw) if ch.isdigit() and gen.get(ch)]
    if not pos:
        return None
    i = rng.choice(pos)
    wrong = rng.choice(gen[raw[i]])
    if i == first and wrong == "0":
        return None
    return raw[:i] + wrong + raw[i + 1:]


def inject_cell(kind: str, raw: str, gen, rng) -> str | None:
    if kind == "nhầm một chữ số":
        return inject_digit(raw, gen, rng)
    if kind == "mất dấu âm":
        return raw.replace("(", "").replace(")", "").replace("-", "") if raw.strip().startswith(("(", "-")) else None
    pos = [i for i, ch in enumerate(raw) if ch.isdigit()][1:]
    if not pos:
        return None
    i = rng.choice(pos)
    return raw[:i] + raw[i + 1:]


def swap_rows(record: dict, rng: random.Random) -> tuple[str, int, int] | None:
    *_, template, _ = _check(copy.deepcopy(record))
    rules = [r for r in RULESETS[template].rules if r.gate and len(r.rhs) >= 2 and r.statement in record["raw"]] \
        if template else []
    if not rules:
        return None
    r = rng.choice(rules)
    rows = record["raw"][r.statement]["rows"]
    idx = {}
    for i, row in enumerate(rows):
        code = normalize_code(row.get("code"))
        if code and code not in idx:
            idx[code] = i
    terms = [c for _, c in r.rhs if c in idx and any(_digits(v) for v in rows[idx[c]]["values"].values())]
    if len(terms) < 2:
        return None
    a, b = rng.sample(terms, 2)
    ia, ib = idx[a], idx[b]
    if rows[ia]["values"] == rows[ib]["values"]:
        return None
    rows[ia]["values"], rows[ib]["values"] = rows[ib]["values"], rows[ia]["values"]
    return r.statement, ia, ib


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=2000, help="số lỗi nhầm chữ số (các kiểu khác: n/4)")
    ap.add_argument("--seed", type=int, default=20261018)
    ap.add_argument("--no-cross", action="store_true", help="bỏ bước đối chiếu kỳ khác (nhanh hơn)")
    ap.add_argument("--listed-before", help="chỉ tính BCTC Vietstock đăng trước ngày này (YYYY-MM-DD), để số liệu báo cáo giữ đúng phạm vi đã ghi")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    with connect() as conn:
        corpus = Corpus(conn, args.listed_before)
        pairs = list(corpus.pairs)
        rng.shuffle(pairs)
        fit_table = count_substitutions(pairs[::2])
        gen: dict[str, list[str]] = defaultdict(list)
        for true, row in count_substitutions(pairs[1::2]).items():
            for read, n in row.items():
                gen[true] += [read] * n
        docs = sorted(corpus.cells)
        res: dict[str, Counter] = {k: Counter() for k in KINDS}
        loc, rank = Counter(), Counter()
        for kind in KINDS:
            target = args.n if kind == "nhầm một chữ số" else max(1, args.n // 4)
            done = 0
            while done < target:
                d = rng.choice(docs)
                broken = copy.deepcopy(corpus.load(d))
                if kind.startswith("đổi chỗ"):
                    swapped = swap_rows(broken, rng)
                    if swapped is None:
                        continue
                    st, ia, ib = swapped
                    cells = [(st, i, col) for i in (ia, ib) for col in broken["raw"][st]["rows"][i]["values"]]
                else:
                    st, row, col = rng.choice(corpus.cells[d])
                    raw = broken["raw"][st]["rows"][row]["values"][col]
                    new = inject_cell(kind, raw, gen, rng)
                    if new is None:
                        continue
                    broken["raw"][st]["rows"][row]["values"][col] = new
                    cells = [(st, row, col)]
                done += 1
                extracted, statements, sep, template, checks = _check(broken)
                new_fail = {(c.rule_id, c.column_kind) for c in checks if c.gate and not c.passed} - corpus.base_fail[d]
                soft = {(c.rule_id, c.column_kind) for c in checks if not c.gate and not c.passed} - corpus.base_soft[d]
                if new_fail:
                    res[kind]["trong BCTC"] += 1
                elif soft:
                    res[kind]["công thức không bắt buộc"] += 1
                elif not args.no_cross and cross_flagged(corpus, d, broken, cells):
                    res[kind]["đối chiếu kỳ khác"] += 1
                else:
                    res[kind]["lọt"] += 1
                if kind != "nhầm một chữ số" or not new_fail:
                    continue
                out = localize(extracted, statements, sep, template)
                hit = lambda p: (p.statement, p.row, p.column_kind) == cells[0] and _digits(p.after) == _digits(raw)
                group = next((g for g in out.ambiguous if any(hit(p) for p in g)), None)
                if any(hit(p) for p in out.proposals):
                    loc["chỉ đúng một ô, đúng số"] += 1
                elif group:
                    loc["ô đúng nằm trong nhóm ngang điểm"] += 1
                    rank["nhóm"] += 1
                    rank["cỡ"] += len(group)
                    rank["theo mô hình nhầm"] += hit(rank_group(list(group), fit_table)[0])
                    m = min(p.digits_changed for p in group)
                    first = [p for p in group if p.digits_changed == m]
                    rank["theo số chữ số khác"] += sum(hit(p) for p in first) / len(first)
                elif out.proposals:
                    loc["đề xuất sai ô hoặc sai số"] += 1
                else:
                    loc["không có đề xuất"] += 1
    print(f"Cấy lỗi vào ô đang được xác nhận của {len(docs)} BCTC đã kiểm chứng; mô hình nhầm học từ "
          f"{len(pairs[::2])} lỗi đã sửa, lỗi cấy lấy từ {len(pairs[1::2])} lỗi khác")
    for kind in KINDS:
        t = res[kind]
        n = sum(t.values())
        caught = n - t["lọt"]
        print(f"  {kind}: {n} lỗi; ràng buộc bắt buộc trong BCTC bắt {t['trong BCTC']} "
              f"({100 * t['trong BCTC'] / n:.0f}%), thêm công thức không bắt buộc {t['công thức không bắt buộc']}, "
              f"đối chiếu kỳ khác {t['đối chiếu kỳ khác']} -> tổng {100 * caught / n:.0f}%; lọt {t['lọt']}")
    n = sum(loc.values())
    print(f"Định vị {n} lỗi nhầm một chữ số đã bị phép kiểm trong BCTC bắt:")
    for k, v in loc.most_common():
        print(f"  {k}: {v} ({100 * v / n:.1f}%)")
    if rank["nhóm"]:
        print(f"  nhóm ngang điểm cỡ trung bình {rank['cỡ'] / rank['nhóm']:.1f}; ô đúng đứng đầu: theo mô hình nhầm "
              f"{100 * rank['theo mô hình nhầm'] / rank['nhóm']:.0f}%, theo số chữ số khác "
              f"{100 * rank['theo số chữ số khác'] / rank['nhóm']:.0f}%")


if __name__ == "__main__":
    main()
