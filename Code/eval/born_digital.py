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
from services.extraction.pipeline import _check, _load_record, open_record_pdf
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


def _table_rows(page, page_no: int, ncols: int) -> list[TruthRow]:
    """Bảng có kẻ ô (PLC): dùng bộ nhận diện bảng của thư viện PDF; tên chỉ tiêu xuống dòng và số in ở dòng cuối của ô
    vẫn nằm trong cùng một hàng. Cột giá trị là ncols cột cuối."""
    out: list[TruthRow] = []
    try:
        tables = page.find_tables().tables
    except Exception:
        return out
    for t in tables:
        if t.col_count < ncols + 1 or t.row_count < 5:
            continue
        grid = [[" ".join((c or "").split()) for c in cells] for cells in t.extract()]
        keep = [j for j in range(t.col_count) if any(r[j] for r in grid)]      # bỏ cột trống hoàn toàn (PLC)
        if len(keep) < ncols + 1:
            continue
        for cells, row in zip(grid, t.rows):
            cells = [cells[j] for j in keep]
            vals = cells[-ncols:]
            if any(v and not all(_is_amount(x) for x in v.split()) for v in vals):
                continue                 # hàng tiêu đề cột
            code = next((c for c in cells[1:-ncols] if CODE.match(c)), None)
            values = {i: v for i, v in enumerate(vals) if v}
            out.append(TruthRow(page_no, (row.bbox[1] + row.bbox[3]) / 2, code, cells[0], values))
    return out


def truth_rows(page, page_no: int, ncols: int) -> list[TruthRow]:
    table = _table_rows(page, page_no, ncols)
    return table if len(table) >= 5 else line_rows(page, page_no, ncols)


def line_rows(page, page_no: int, ncols: int) -> list[TruthRow]:
    """Bảng không kẻ ô (GVR, VPB, ACB): gom chữ thành hàng theo tung độ, số xếp vào cột theo mép phải."""
    words = page.get_text("words")
    if page.rotation:
        # trang đặt xoay (TIG quý 2/2026: 270 độ): đổi tọa độ chữ sang hướng đọc
        import pymupdf
        m = page.rotation_matrix
        words = [(*(pymupdf.Rect(w[:4]) * m).normalize(), *w[4:]) for w in words]
    rows = _visual_rows(words)
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
    return compare_record(record, open_record_pdf(conn, record), doc_id, verbose)


def _compare_statement(st, raw, truth, kinds, manual, sep, truth_sep, doc_id) -> tuple[Counter, list[str]]:
    tally, msgs = Counter(), []
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
            same = [(j, t) for j, t in cands if t.code and normalize_code(t.code) == code]
            hits = [(j, t) for j, t in same if (row["page"], j) not in used]
            if len(hits) == 1:
                best = hits[0]
            elif not hits and len(same) == 1:
                tally["dòng đọc lặp"] += 1      # mô hình chép một dòng hai lần; cùng mã cùng số nên code gộp lại
                continue
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
            if True:
                msgs.append(f"  [{doc_id}] {st} dòng {i} không ghép được: {row.get('code')} {row.get('label', '')[:50]} "
                      f"{vals}")
            continue
        used.add((row["page"], best[0]))
        t = best[1]
        last_y[int(row["page"])] = t.y
        for ci, kind in enumerate(kinds):
            truth_raw = t.values.get(ci)
            tv = None if truth_raw is None or truth_raw.strip() in DASH else parse_amount(truth_raw, truth_sep)
            tv = None if tv == 0 else tv            # "0" và "-" (ô trống) cùng nghĩa trên BCTC
            for level, raw_value in (("cuối cùng", row["values"].get(kind)),
                                     ("tự động", manual.get((st, i, kind), row["values"].get(kind)))):
                v = None if raw_value in (None, "") or str(raw_value).strip() in DASH else parse_amount(str(raw_value), sep)
                v = None if v == 0 else v
                if tv is None and v is None:
                    continue
                result = "đúng" if tv == v else ("thiếu" if v is None else "thừa" if tv is None else "sai")
                tally[f"{level}: {result}"] += 1
                if result != "đúng" and level == "tự động":
                    msgs.append(f"  [{doc_id}] {st} dòng {i} {row.get('code') or ''} {row.get('label', '')[:40]} {kind}: "
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
            n = sum(1 for v in t.values.values() if v.strip() not in DASH and parse_amount(v, truth_sep) not in (None, 0))
            if n:
                tally["tự động: thiếu"] += n
                tally["cuối cùng: thiếu"] += n
                tally["dòng đáp án bị bỏ sót"] += 1
                if True:
                    msgs.append(f"  [{doc_id}] {st} trang {p}: dòng đáp án không có dòng đọc tương ứng: {t.label[:50]} {t.values}")
    return tally, msgs


def compare_record(record: dict, doc, doc_id, verbose: bool = False, truth_sep: str | None = None) -> Counter:
    """So các ô của bản ghi trích xuất `record` với lớp chữ gốc của `doc` (file có chữ gốc cùng số trang)."""
    texts = page_texts(doc)
    sep = record.get("thousands_sep") or "."
    truth_sep = truth_sep or sep
    tally = Counter()
    manual = {(m["statement"], m["row"], m["column_kind"]): m.get("before") for m in record.get("manual_fixes", [])}
    for st, raw in record["raw"].items():
        kinds = [c["kind"] for c in raw.get("columns", []) if c.get("kind") in VALUE_KINDS]
        pages = sorted({int(r["page"]) for r in raw["rows"] if r.get("page")})
        if not kinds or not pages or not all(texts[p - 1].usable for p in pages if p - 1 < len(texts)):
            tally["báo cáo không có chữ gốc"] += 1
            continue
        # Hai cách dựng đáp án: bảng có kẻ ô (bộ nhận diện bảng) và gom chữ theo hàng. Giữ cách ghép được nhiều dòng
        # hơn; chỉ xét việc ghép dòng, không xét số khớp hay không, để cách chọn không thiên về kết quả tốt
        options = []
        for name, fn in (("hàng", line_rows), ("bảng", _table_rows)):
            truth = {pg: fn(doc[pg - 1], pg, len(kinds)) for pg in pages}
            t, msgs = _compare_statement(st, raw, truth, kinds, manual, sep, truth_sep, doc_id)
            options.append((t["dòng không ghép được"] + t["dòng đáp án bị bỏ sót"], name != "hàng", t, msgs))
        _, _, t, msgs = min(options, key=lambda x: (x[0], x[1]))
        tally.update(t)
        if verbose:
            for msg in msgs:
                print(msg)
    return tally


def flagged(record: dict, conn=None, doc_id: int | None = None) -> list[str]:
    """Lý do hệ thống (theo bộ kiểm tra hiện tại) không để BCTC đọc ở bản này đi thẳng ra ngoài: ràng buộc bắt buộc lệch
    (vào hàng đọc lại/duyệt), hoặc có dấu hiệu thiếu dòng (cần xem lại). BCTC trong kho thì đối chiếu cả BCTC kỳ khác."""
    from services.extraction.evidence import cells_of, document_evidence
    _, _, _, _, checks = _check(record)
    out = [f"lệch {c.rule_id}" for c in checks if c.gate and not c.passed]
    if conn is not None and doc_id is not None:
        cache: dict[int, dict | None] = {}

        def load(x):
            if x == doc_id:
                return record
            if x not in cache:
                try:
                    cache[x] = _load_record(conn, x)
                except RuntimeError:
                    cache[x] = None
            return cache[x]
        ev = document_evidence(conn, doc_id, load=load)
        missing = ev.missing if ev else []
    else:
        missing = [code for _, code, _ in cells_of(0, "", record).required_missing]
    return out + [f"thiếu dòng {getattr(m, 'key', m)}" for m in missing]


def _tally_flag(t: Counter, reasons: list[str]) -> None:
    """Ô sai (sai/thiếu/thừa ở mức tự động) nằm trong BCTC bị báo hay lọt qua."""
    wrong = sum(v for k, v in t.items() if k.startswith("tự động") and k != "tự động: đúng")
    t["BCTC bị báo"] += bool(reasons)
    t["ô sai trong BCTC bị báo" if reasons else "ô sai lọt qua"] += wrong


@dataclass
class Level:
    name: str
    dpi: int
    blur: float
    angle: float
    noise: float
    jpeg: int


# Mức chất lượng ảnh mô phỏng bản scan: "xấu" gần với file 72 dpi của GVR bán niên 2026
LEVELS = {"tot": Level("scan tốt", 200, 0.0, 0.3, 0.0, 80),
          "vua": Level("scan trung bình", 120, 0.5, 0.7, 6.0, 55),
          "xau": Level("scan xấu", 72, 0.7, 1.2, 10.0, 35)}


def degrade(src, level: Level):
    """PDF chỉ gồm ảnh (như bản scan) dựng lại từ `src` ở mức chất lượng `level`."""
    import io
    import random

    import pymupdf
    from PIL import Image, ImageFilter

    rng = random.Random(20261020)
    out = pymupdf.open()
    for page in src:
        pix = page.get_pixmap(dpi=level.dpi, colorspace=pymupdf.csGRAY)
        img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
        if level.blur:
            img = img.filter(ImageFilter.GaussianBlur(level.blur))
        if level.angle:
            img = img.rotate(rng.uniform(-level.angle, level.angle), resample=Image.BICUBIC, fillcolor=255)
        if level.noise:
            noise = Image.effect_noise(img.size, level.noise)
            img = Image.blend(img, noise, 0.08)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=level.jpeg)
        new = out.new_page(width=page.rect.width, height=page.rect.height)
        new.insert_image(new.rect, stream=buf.getvalue())
    return out


def read_pdf(client, src, base: dict, chosen: dict | None, level_key: str, out_name: str) -> dict:
    """Đọc `src` (level_key "goc": nguyên file; mức khác: bản làm mờ) bằng quy trình thật: chép bảng, kiểm tra, leo
    thang (không ghi CSDL). `chosen`: kết quả định vị trang có sẵn; None thì định vị trên nguyên file."""
    import json

    from services.extraction import prompts
    from services.extraction.pipeline import (LOCATE_MAX_PAGES, _check, _escalate, _extract_detail, _extract_image,
                                              _locate, _rotation, _statement_pages, fix_row_pages)
    from services.ingestion.registry import raw_data_dir

    usd0 = client.usage.usd
    if chosen is None:
        pages = _locate(client, src, LOCATE_MAX_PAGES)
        chosen = {"pages": pages, "statement_pages": _statement_pages(pages),
                  "rotations": {p["page"]: p.get("rotation", 0) for p in pages}}
    doc = src if level_key == "goc" else degrade(src, LEVELS[level_key])
    record = dict(base, model=client.cfg.model, provider=client.cfg.provider, level=level_key, raw={},
                  candidates=[dict(chosen, name="eval")], chosen="eval")
    for st, pages in chosen["statement_pages"].items():
        pages = [int(p) for p in pages]
        images = [(f"Trang {p}", _extract_image(doc, p, _rotation(record, p))) for p in pages]
        record["raw"][st] = fix_row_pages(client.json_from_images(prompts.extract_prompt(st), images,
                                                                  prompts.extract_schema(st), f"statement_{st}",
                                                                  detail=_extract_detail(doc, pages)), pages)
    _escalate(record, client, doc, None)
    _, _, sep, template, checks = _check(record)
    record["thousands_sep"] = sep
    record["gate_failed"] = sum(c.gate and not c.passed for c in checks)
    record["usd"] = client.usage.usd - usd0
    out = raw_data_dir() / "born_digital" / "runs" / f"{out_name}_{level_key}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, default=str), encoding="utf-8")
    return record


def run_degraded(conn, client, doc_id: int, level_key: str) -> dict:
    """BCTC đã có trong kho: dùng lại kết quả định vị trang của lần đọc thật để chỉ đo phần đọc số."""
    original = _load_record(conn, doc_id)
    chosen = next(c for c in original["candidates"] if c["name"] == original["chosen"])
    base = {"document_id": doc_id, "ticker": original["ticker"], "doc_type": original.get("doc_type"),
            "company_template": original["company_template"]}
    return read_pdf(client, open_record_pdf(conn, original), base, chosen, level_key, str(doc_id))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--doc-id", type=int, nargs="+", required=True)
    m.add_argument("--verbose", action="store_true")
    r = sub.add_parser("degraded", help="đọc lại từ ảnh làm mờ (gọi mô hình) rồi chấm; đã có kết quả thì chỉ chấm")
    r.add_argument("--doc-id", type=int, nargs="+", required=True)
    r.add_argument("--level", nargs="+", default=list(LEVELS), choices=list(LEVELS))
    r.add_argument("--verbose", action="store_true")
    f = sub.add_parser("files", help="BCTC có chữ gốc chưa có trong kho (Data/raw/born_digital/set.json): đọc ở "
                                     "bản gốc và các mức làm mờ, chấm bằng lớp chữ gốc")
    f.add_argument("--level", nargs="+", default=["goc", *LEVELS], choices=["goc", *LEVELS])
    f.add_argument("--only", nargs="+", help="chỉ các tên, ví dụ PLC_Q2_2025")
    f.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if args.cmd == "files":
        files_main(args)
        return
    if args.cmd == "degraded":
        degraded_main(args)
        return
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


def degraded_main(args) -> None:
    import json

    from services.ingestion.registry import raw_data_dir
    from services.llm import VisionClient

    client = None
    totals: dict[str, Counter] = {}
    with connect() as conn:
        for d in args.doc_id:
            original = _load_record(conn, d)
            src = open_record_pdf(conn, original)
            for lv in args.level:
                path = raw_data_dir() / "born_digital" / "runs" / f"{d}_{lv}.json"
                if path.exists():
                    rec = json.loads(path.read_text(encoding="utf-8"))
                else:
                    client = client or VisionClient()
                    rec = run_degraded(conn, client, d, lv)
                t = compare_record(rec, src, d, args.verbose, truth_sep=original.get("thousands_sep"))
                reasons = flagged(rec, conn, d)
                _tally_flag(t, reasons)
                n = sum(v for k, v in t.items() if k.startswith("tự động"))
                ok = t["tự động: đúng"]
                print(f"[{d}] {original['ticker']} {LEVELS[lv].name}: {ok}/{n} ô đúng"
                      + (f" ({100 * ok / n:.2f}%)" if n else "") + f"; hệ thống báo: {', '.join(reasons) or 'không'}; "
                      f"{rec.get('usd', 0):.3f} USD; {dict(t)}", flush=True)
                totals.setdefault(lv, Counter()).update(t)
    for lv, t in totals.items():
        n = sum(v for k, v in t.items() if k.startswith("tự động"))
        ok = t["tự động: đúng"]
        if n:
            print(f"{LEVELS[lv].name}: {ok}/{n} ô đúng ({100 * ok / n:.2f}%); {t['BCTC bị báo']} BCTC bị báo, "
                  f"chứa {t['ô sai trong BCTC bị báo']} ô sai; {t['ô sai lọt qua']} ô sai lọt qua")
    if client:
        print(f"Tổng chi phí lần chạy này: {client.usage.usd:.3f} USD")


def _infer_sep(doc) -> str:
    """Dấu phân cách hàng nghìn của lớp chữ gốc."""
    text = " ".join(page.get_text() for page in doc)
    dots, commas = len(re.findall(r"\d\.\d{3}(?!\d)", text)), len(re.findall(r"\d,\d{3}(?!\d)", text))
    return "." if dots >= commas else ","


def files_main(args) -> None:
    import json

    from services.extraction.sources import candidates, open_pdf
    from services.ingestion.registry import raw_data_dir
    from services.llm import VisionClient

    root = raw_data_dir() / "born_digital"
    entries = json.loads((root / "set.json").read_text(encoding="utf-8"))
    template_of = {"bank": "bank", "corporate": "corporate", "securities": "securities"}
    client = None
    totals: dict[str, Counter] = {}
    for e in entries:
        name = f"{e['ticker']}_{e['period']}_{e['year']}"
        if (args.only and name not in args.only) or (not args.only and e.get("excluded")):
            continue
        src = open_pdf(candidates(root / "pdf" / e["file"])[0])
        sep = _infer_sep(src)
        base = {"document_id": name, "ticker": e["ticker"], "doc_type": e["doc_type"],
                "company_template": template_of[e["template"]]}
        chosen = None
        for lv in ["goc", *[x for x in args.level if x != "goc"]]:
            if lv not in args.level and lv != "goc":
                continue
            path = root / "runs" / f"{name}_{lv}.json"
            if path.exists():
                rec = json.loads(path.read_text(encoding="utf-8"))
            else:
                client = client or VisionClient()
                rec = read_pdf(client, src, base, chosen, lv, name)
            chosen = {k: v for k, v in rec["candidates"][0].items() if k != "name"}
            if lv not in args.level:
                continue
            t = compare_record(rec, src, name, args.verbose, truth_sep=sep)
            reasons = flagged(rec)
            _tally_flag(t, reasons)
            n = sum(v for k, v in t.items() if k.startswith("tự động"))
            ok = t["tự động: đúng"]
            label = "bản gốc" if lv == "goc" else LEVELS[lv].name
            print(f"[{name}] {label}: {ok}/{n} ô đúng" + (f" ({100 * ok / n:.2f}%)" if n else "")
                  + f"; hệ thống báo: {', '.join(reasons) or 'không'}; {rec.get('usd', 0):.3f} USD; {dict(t)}",
                  flush=True)
            totals.setdefault(lv, Counter()).update(t)
    for lv, t in totals.items():
        n = sum(v for k, v in t.items() if k.startswith("tự động"))
        if n:
            print(f"{'bản gốc' if lv == 'goc' else LEVELS[lv].name}: {t['tự động: đúng']}/{n} ô đúng "
                  f"({100 * t['tự động: đúng'] / n:.2f}%); {t['BCTC bị báo']} BCTC bị báo, chứa "
                  f"{t['ô sai trong BCTC bị báo']} ô sai; {t['ô sai lọt qua']} ô sai lọt qua")
    if client:
        print(f"Tổng chi phí lần chạy này: {client.usage.usd:.3f} USD")


if __name__ == "__main__":
    main()
