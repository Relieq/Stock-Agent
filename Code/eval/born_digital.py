"""Độ đúng từng ô đo bằng đáp án có sẵn: BCTC xuất thẳng từ Excel/Word có lớp chữ gốc, đúng từng chữ số kế toán đã gõ.

    python eval/born_digital.py measure [--doc-id 6 160] [--list 20]   # so số đã đọc (từ ảnh) với lớp chữ gốc

Hệ thống luôn đọc BCTC từ ảnh trang, kể cả khi file có lớp chữ, nên với các file có chữ gốc ta có đáp án cho mọi ô mà
không cần người gán nhãn. Bảng đáp án được dựng lại từ vị trí chữ trên trang: gom chữ thành hàng theo tung độ, số tiền
xếp vào cột theo hoành độ mép phải (số canh phải), mã số là cụm 2-3 chữ số ở mép trái. Dòng đã đọc được ghép với dòng
đáp án theo mã số, không có mã thì theo tên chỉ tiêu đã bỏ dấu.

Hai mức đo: số hệ thống tự đọc ra (trả lại số trước khi người sửa tay) và số cuối cùng đang lưu.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from services.db import connect
from services.extraction.bank import clean_label, fold
from services.extraction.numbers import normalize_code, parse_amount
from services.extraction.pipeline import _load_record, open_record_pdf
from services.extraction.sources import page_texts

AMOUNT = re.compile(r"^\(?-?\d{1,3}([.,]\d{3})+\)?$|^\(?-?\d+\)?$")
DASH = {"-", "–", "—"}
CODE = re.compile(r"^\d{2,3}[a-z]?$")
NOTE = re.compile(r"(?<!\S)[ivx]*\.?\d+(\.\d+)*[a-z]?(?!\S)")
STT = re.compile(r"^([ivxl]+|[a-e]|\d+)[.)]?$")
VALUE_KINDS = {"q_cur", "q_prev_year", "ytd_cur", "ytd_prev_year", "end_period", "begin_year"}


@dataclass
class TruthRow:
    page: int
    y: float
    code: str | None
    label: str
    values: dict[int, str] = field(default_factory=dict)     # chỉ số cột giá trị -> chuỗi như in


def _visual_rows(words, tol: float = 3.0):
    rows: list[list] = []
    for w in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        yc = (w[1] + w[3]) / 2
        if rows and abs(rows[-1][0] - yc) <= tol:
            rows[-1][1].append(w)
        else:
            rows.append([yc, [w]])
    return [(yc, sorted(ws, key=lambda w: w[0])) for yc, ws in rows]


def _is_amount(text: str) -> bool:
    return bool(AMOUNT.match(text)) or text in DASH


def _value_columns(rows, ncols: int) -> list[float]:
    """Hoành độ mép phải của các cột giá trị: gom mép phải của các số có dấu phân cách hàng nghìn (số tiền), lấy
    ncols cụm bên phải nhất."""
    xs = sorted(w[2] for _, ws in rows for w in ws if AMOUNT.match(w[4]) and re.search(r"\d[.,]\d{3}", w[4]))
    clusters: list[list[float]] = []
    for x in xs:
        if clusters and x - clusters[-1][-1] <= 12:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    big = [c for c in clusters if len(c) >= 3]
    centers = [sum(c) / len(c) for c in big]
    return centers[-ncols:] if len(centers) >= ncols else centers


def truth_rows(page, page_no: int, ncols: int) -> list[TruthRow]:
    rows = _visual_rows(page.get_text("words"))
    cols = _value_columns(rows, ncols)
    if len(cols) < ncols:
        return []
    left_edge = min(cols) - 140           # số tiền dài nhất khoảng 130 điểm
    out: list[TruthRow] = []
    orphan = ""                           # chữ của các hàng không có số (tên chỉ tiêu xuống dòng)
    for yc, ws in rows:
        values, text, code = {}, [], None
        for w in ws:
            t = w[4]
            if w[0] >= left_edge and _is_amount(t):
                i = min(range(len(cols)), key=lambda k: abs(cols[k] - w[2]))
                if abs(cols[i] - w[2]) <= 25:
                    values[i] = (values[i] + " " + t) if i in values else t
                    continue
            if code is None and not text and CODE.match(t):
                code = t
                continue
            text.append(t)
        label = " ".join(text)
        if values and code is None and out and not out[-1].values:
            # tên chỉ tiêu xuống dòng, số in ở hàng cuối (ACB: "04 Chênh lệch ... / kinh doanh ... 674.347")
            out[-1].label += " " + label
            out[-1].values = values
            continue
        if not values and code is None:
            orphan = (orphan + " " + label).strip()
            if out and not out[-1].values:
                out[-1].label += " " + label
            continue
        out.append(TruthRow(page_no, yc, code, (orphan + " " + label).strip(), values))
        orphan = ""
    return out


def _core(label: str) -> str:
    """Tên chỉ tiêu đã bỏ dấu, bỏ số thuyết minh và số thứ tự đầu dòng (XII, 4, a)."""
    words = NOTE.sub(" ", fold(clean_label(label))).split()
    while words and STT.match(words[0]):
        words = words[1:]
    return " ".join(words)


def _sim(a: str, b: str) -> float:
    # bỏ số thuyết minh và số thứ tự dính vào tên ("Chứng khoán kinh doanh 8", "VI.1")
    a, b = (_core(x) for x in (a, b))
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.95
    return SequenceMatcher(None, a, b).ratio()


def compare_document(conn, doc_id: int, verbose: bool = False) -> Counter | None:
    record = _load_record(conn, doc_id)
    doc = open_record_pdf(conn, record)
    texts = page_texts(doc)
    sep = record.get("thousands_sep") or "."
    tally = Counter()
    manual = {(m["statement"], m["row"], m["column_kind"]): m.get("before") for m in record.get("manual_fixes", [])}
    for st, raw in record["raw"].items():
        kinds = [c["kind"] for c in raw.get("columns", []) if c.get("kind") in VALUE_KINDS]
        pages = sorted({int(r["page"]) for r in raw["rows"] if r.get("page")})
        if not kinds or not pages or not all(texts[p - 1].usable for p in pages if p - 1 < len(texts)):
            tally["báo cáo không có chữ gốc"] += 1
            continue
        truth = {p: truth_rows(doc[p - 1], p, len(kinds)) for p in pages}
        used: set[tuple[int, int]] = set()
        last_y: dict[int, float] = {}         # dòng ghép được gần nhất trên mỗi trang: các dòng sau phải nằm dưới nó
        for i, row in enumerate(raw["rows"]):
            vals = {k: v for k, v in row["values"].items() if v not in (None, "")}
            if not vals and not any(manual.get((st, i, k)) for k in kinds):
                continue
            cands = list(enumerate(truth.get(int(row["page"] or 0), [])))
            code = normalize_code(row.get("code"))
            best = None
            if code:
                hits = [(j, t) for j, t in cands if t.code and normalize_code(t.code) == code and (row["page"], j) not in used]
                if len(hits) == 1:
                    best = hits[0]
            if best is None:
                # Tên trùng nhau (ngân hàng: "Chứng khoán kinh doanh" ở dòng mục và dòng con) thì lấy dòng đầu tiên nằm dưới
                # dòng vừa ghép
                y0 = last_y.get(int(row["page"] or 0), -1.0)
                scored = sorted(((_sim(row.get("label") or "", t.label), j, t) for j, t in cands
                                 if (row["page"], j) not in used),
                                key=lambda x: (-round(x[0], 2), x[2].y <= y0, x[2].y))
                if scored and scored[0][0] >= 0.8:
                    best = (scored[0][1], scored[0][2])
                elif not _core(row.get("label") or ""):
                    # dòng đọc ra không có tên (thường là dòng tổng): lấy dòng đáp án có số kế tiếp
                    below = [(j, t) for j, t in cands if (row["page"], j) not in used and t.y > y0 and t.values]
                    best = min(below, key=lambda x: x[1].y) if below else None
            if best is None:
                tally["dòng không ghép được"] += 1
                if verbose:
                    print(f"  [{doc_id}] {st} dòng {i} không ghép được: {row.get('code')} {row.get('label', '')[:50]} "
                          f"{vals}")
                continue
            used.add((row["page"], best[0]))
            t = best[1]
            last_y[int(row["page"])] = t.y
            for ci, kind in enumerate(kinds):
                truth_raw = t.values.get(ci)
                tv = None if truth_raw is None or truth_raw.strip() in DASH else parse_amount(truth_raw, sep)
                for level, raw_value in (("cuối cùng", row["values"].get(kind)),
                                         ("tự động", manual.get((st, i, kind), row["values"].get(kind)))):
                    v = None if raw_value in (None, "") or str(raw_value).strip() in DASH else parse_amount(str(raw_value), sep)
                    if tv is None and v is None:
                        continue
                    result = "đúng" if tv == v else ("thiếu" if v is None else "thừa" if tv is None else "sai")
                    tally[f"{level}: {result}"] += 1
                    if verbose and result != "đúng" and level == "tự động":
                        print(f"  [{doc_id}] {st} dòng {i} {row.get('code') or ''} {row.get('label', '')[:40]} {kind}: "
                              f"đọc {raw_value} / đáp án {truth_raw}")
        # Chiều ngược lại: dòng có số trong đáp án mà hệ thống không đọc ra (bỏ sót dòng). Chỉ xét phần trang nằm giữa
        # dòng đầu và dòng cuối đã ghép được, để không tính tiêu đề trang, ngày tháng, chữ ký.
        for p, rows_p in truth.items():
            ys = [rows_p[j].y for (pp, j) in used if pp == p]
            if not ys:
                continue
            for j, t in enumerate(rows_p):
                if (p, j) in used or not (min(ys) < t.y < max(ys)):
                    continue
                n = sum(1 for v in t.values.values() if v.strip() not in DASH)
                if n:
                    tally["tự động: thiếu"] += n
                    tally["cuối cùng: thiếu"] += n
                    tally["dòng đáp án bị bỏ sót"] += 1
                    if verbose:
                        print(f"  [{doc_id}] {st} trang {p}: dòng đáp án không có dòng đọc tương ứng: {t.label[:50]} {t.values}")
    return tally


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--doc-id", type=int, nargs="+", required=True)
    m.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    total = Counter()
    with connect() as conn:
        for d in args.doc_id:
            t = compare_document(conn, d, args.verbose)
            ticker = conn.execute("SELECT ticker || ' ' || fiscal_period || '/' || fiscal_year FROM documents WHERE id = %s",
                                  (d,)).fetchone()[0]
            print(f"[{d}] {ticker}: {dict(t)}", flush=True)
            total += t
    for level in ("tự động", "cuối cùng"):
        n = sum(v for k, v in total.items() if k.startswith(level))
        ok = total[f"{level}: đúng"]
        if n:
            print(f"{level}: {ok}/{n} ô đúng ({100 * ok / n:.2f}%); sai {total[f'{level}: sai']}, "
                  f"thiếu {total[f'{level}: thiếu']}, thừa {total[f'{level}: thừa']}")
    print(f"dòng không ghép được: {total['dòng không ghép được']}; báo cáo không có chữ gốc: "
          f"{total['báo cáo không có chữ gốc']}")


if __name__ == "__main__":
    main()
