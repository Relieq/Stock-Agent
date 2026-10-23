"""So sánh các phương pháp đọc số BCTC trên cùng bộ đáp án chữ gốc (11 BCTC, eval/born_digital.py).

Mọi phương pháp nhận đúng cùng trang ba báo cáo (trang Soi đã định vị ở bản gốc), cùng ảnh trang ở cùng bốn mức (ảnh
gốc và ba bản làm mờ của born_digital.degrade, vẽ bằng đúng hàm vẽ ảnh của hệ thống), cùng góc xoay. Đầu ra của mỗi
phương pháp được đổi sang dạng bản ghi của Soi rồi chấm bằng cùng bộ chấm (born_digital.compare_record) và cùng bộ phép
kiểm (born_digital.flagged): ô sai nằm trong BCTC bị báo hay lọt qua.

Phương pháp:
  M1  lớp chữ PDF (chữ gốc, chính là nguồn của đáp án: chỉ để tham khảo, không phải đối thủ công bằng)
  M2  Tesseract 5 tiếng Việt, hộp chữ -> dựng bảng bằng luật (hàng theo tung độ, cột số theo cụm mép phải, mã số theo
      vị trí cột)
  M3  Docling (mô hình bố cục + cấu trúc bảng, OCR bằng Tesseract tiếng Việt, chạy CPU) -> bảng -> dòng
  M4  chữ OCR của M2 + mô hình văn bản (Haiku 5.5, không ảnh) chép thành JSON theo đúng schema của Soi
  M5a Soi lần đọc đầu (dựng lại từ kết quả đã lưu bằng cách hoàn nguyên các bước tự sửa đã ghi)
  M5b Soi đầy đủ (kết quả đã lưu)

Các bước (chạy từ Code/):
  # image soi-app (cần CSDL cho 6 BCTC trong kho):
  docker compose -f infra/docker-compose.yml run --rm -T app python eval/methods.py prepare
  docker compose -f infra/docker-compose.yml run --rm -T app python eval/methods.py run --method M1 --level goc
  docker compose -f infra/docker-compose.yml run --rm -T app python eval/methods.py run --method M4 --level goc --only PLC_Q2_2025 --max-usd 0.10
  docker compose -f infra/docker-compose.yml run --rm -T app python eval/methods.py score
  # image riêng soi-methods (eval/methods/Dockerfile), không cần CSDL:
  docker run --rm -v "$PWD:/app/Code" -v "$PWD/../Data/raw:/app/Data/raw" soi-methods python eval/methods.py run --method M2
  docker run --rm -v "$PWD:/app/Code" -v "$PWD/../Data/raw:/app/Data/raw" soi-methods python eval/methods.py run --method M3

Kết quả mỗi lượt lưu ở Data/raw/methods/<phương pháp>/<mức>/<tên>.json (đầu ra thô của công cụ: <tên>.raw.json), chạy
lại thì chỉ chấm lại, không tốn gì.

Ánh xạ cột (giống nhau cho M1, M2, M3): các cột số của một trang được đếm theo cụm mép phải; n cột đầu tiên theo thứ tự
trái sang phải ứng với n loại cột đầu tiên của báo cáo: BCĐKT end_period, begin_year; KQKD q_cur, q_prev_year, ytd_cur,
ytd_prev_year; LCTT ytd_cur, ytd_prev_year. Cột của đáp án luôn dựng theo loại cột của Soi ở bản gốc (đã đúng 100%) để
mọi phương pháp chấm trên cùng một đáp án; phương pháp đếm sai số cột thì số rơi vào cột khác và bị tính sai.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

LEVEL_KEYS = ["goc", "tot", "vua", "xau"]
LEVEL_NAMES = {"goc": "bản gốc", "tot": "scan tốt 200 dpi", "vua": "scan vừa 120 dpi", "xau": "scan xấu 72 dpi"}
METHODS = ["M1", "M2", "M3", "M4", "M5a", "M5b", "M5a_cungAnh", "M5b_cungAnh"]
# M5a/M5b: kết quả Soi đã lưu của born_digital (bản 120/72 dpi có nhiễu khác bộ ảnh chung, xem prepare);
# M5a_cungAnh/M5b_cungAnh: Soi đọc lại đúng file làm mờ đã lưu ở Data/raw/methods/degraded (run --method M5)
DB_DOCS = [6, 160, 162, 5829, 6070, 13892]        # 6 BCTC trong kho có chữ gốc (born_digital measure/degraded)
COLUMN_KINDS = {
    "BS": ["end_period", "begin_year"],
    "IS": ["q_cur", "q_prev_year", "ytd_cur", "ytd_prev_year"],
    "CF": ["ytd_cur", "ytd_prev_year"],
}

AMOUNT = re.compile(r"^\(?-?\d{1,3}([.,]\d{3})+\)?$|^\(?-?\d+\)?$")      # như born_digital.AMOUNT
GROUPED = re.compile(r"\d[.,]\d{3}")                                     # số có dấu phân cách hàng nghìn
DASH = {"-", "–", "—"}
CODE = re.compile(r"^\d{2,3}[a-z]?$")
STT_TOKEN = re.compile(r"^([IVXL]+|[A-Ea-e]|\d{1,2})[.)]$|^[IVXL]+$|^[A-E]$")
NOTE_TOKEN = re.compile(r"^([IVX]+\.?)?\d{1,2}(\.\d{1,2})*[a-z]?$")       # thuyết minh: 5, 4.2, V.1, V20, VI.14


def raw_dir() -> Path:
    """Data/raw (giống services.ingestion.registry.raw_data_dir, không phải nhập code của Soi trong image riêng)."""
    code_dir = Path(__file__).resolve().parent.parent
    return (code_dir / os.environ.get("RAW_DATA_DIR", "../Data/raw")).resolve()


def out_dir() -> Path:
    return raw_dir() / "methods"


# ---------------------------------------------------------------------------------------------------------------
# Hàm thuần: ánh xạ cột, dựng dòng từ hộp chữ, dựng dòng từ lưới bảng (có kiểm thử trong tests/test_methods.py)

def map_kinds(statement: str, n: int) -> list[str]:
    """n cột số đếm được (trái sang phải) -> loại cột của Soi theo thứ tự; thừa cột thì chỉ giữ số loại của báo cáo."""
    return COLUMN_KINDS[statement][:max(0, n)]


def is_amount(text: str) -> bool:
    return bool(AMOUNT.match(text)) or text in DASH


def visual_rows(words, tol: float = 3.0):
    """Gom chữ thành hàng theo tung độ tâm (như born_digital._visual_rows). words: (x0, y0, x1, y1, chữ, ...)."""
    rows: list[list] = []
    for w in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        yc = (w[1] + w[3]) / 2
        if rows and abs(rows[-1][0] - yc) <= tol:
            rows[-1][1].append(w)
        else:
            rows.append([yc, [w]])
    return [(yc, sorted(ws, key=lambda w: w[0])) for yc, ws in rows]


def _clusters(xs: list[float], gap: float) -> list[list[float]]:
    out: list[list[float]] = []
    for x in sorted(xs):
        if out and x - out[-1][-1] <= gap:
            out[-1].append(x)
        else:
            out.append([x])
    return out


def value_columns(rows, max_cols: int, min_size: int = 3) -> list[float]:
    """Hoành độ mép phải các cột số: cụm mép phải của các số có dấu phân cách hàng nghìn, cụm có từ `min_size` số trở
    lên; giữ `max_cols` cụm bên phải nhất (cùng luật với cột của đáp án, nhưng số cột do dữ liệu quyết định)."""
    xs = [w[2] for _, ws in rows for w in ws if AMOUNT.match(w[4]) and GROUPED.search(w[4])]
    centers = [sum(c) / len(c) for c in _clusters(xs, 12) if len(c) >= min_size]
    return centers[-max_cols:]


def code_column(rows, right_limit: float, min_size: int = 4) -> float | None:
    """Tâm hoành độ của cột Mã số: cụm lớn nhất các chữ dạng 2-3 chữ số nằm bên trái vùng số tiền."""
    xs = [(w[0] + w[2]) / 2 for _, ws in rows for w in ws if CODE.match(w[4]) and w[2] < right_limit]
    big = [c for c in _clusters(xs, 10) if len(c) >= min_size]
    if not big:
        return None
    best = max(big, key=len)
    return sum(best) / len(best)


def _starts_lower(text: str) -> bool:
    t = text.lstrip("(\"'“-–")
    return bool(t) and t[0].isalpha() and t[0].islower()


def split_label(tokens: list[str]) -> tuple[str | None, str, str | None]:
    """Chữ không phải số tiền và mã số của một hàng -> (stt, tên chỉ tiêu, thuyết minh)."""
    toks = list(tokens)
    stt = None
    if toks and STT_TOKEN.match(toks[0]) and len(toks) > 1:
        stt = toks.pop(0).rstrip(".)")
    note = None
    if toks and NOTE_TOKEN.match(toks[-1]) and (len(toks) > 1 or not CODE.match(toks[-1])):
        note = toks.pop()
    return stt, " ".join(toks), note


def _has_text(label: str) -> bool:
    """Tên có ít nhất một chữ dài từ 2 chữ cái (không phải mảnh vụn OCR như "1U)", "li")."""
    return any(sum(c.isalpha() for c in w) >= 2 for w in label.split()) and len(label.replace(" ", "")) >= 4


BORDER = "|¦[]_!"      # nét kẻ bảng mà OCR đọc thành chữ


def clean_value(text: str) -> str:
    """Chữ trong ô số -> chuỗi số: bỏ nét kẻ bảng đọc thành chữ ("|", "[", "_"), bỏ gạch ngang đứng riêng khi ô còn số
    khác ("— 6.267.821.574"); ô chỉ có gạch ngang giữ nguyên (nghĩa là trống)."""
    toks = [t.strip(BORDER) for t in text.replace("|", " ").replace("¦", " ").split()]
    toks = [t for t in toks if t]
    nums = [t for t in toks if t not in DASH]
    return " ".join(nums if nums else toks)


def assemble(fragments: list[tuple], page: int, statement: str) -> list[dict]:
    """Các hàng ngang (stt, mã số, tên, thuyết minh, {loại cột: chuỗi số}) theo thứ tự từ trên xuống -> dòng dạng Soi.

    Một dòng chỉ tiêu có thể bị tách thành nhiều hàng ngang (tên xuống dòng; tên, mã số và số in lệch tung độ trong ô
    bảng). Luật gộp, giống nhau cho mọi phương pháp:
    - hàng không có tên thật (chỉ mã số, thuyết minh, số) gộp vào dòng đang chờ ở trên (dòng có tên mà chưa có số);
      không có dòng chờ thì gộp số vào dòng ngay trên nếu dòng đó chưa có số ở các cột này;
    - hàng có tên bắt đầu bằng chữ thường, không số thứ tự: phần tiếp của tên dòng đang chờ, hoặc của dòng ngay trên
      nếu không có dòng chờ;
    - hàng có tên mà chưa có số thành dòng chờ; dòng chờ được ghi ra khi có số hoặc khi gặp dòng mới."""
    out: list[dict] = []
    pending: dict | None = None

    def flush():
        nonlocal pending
        if pending is not None:
            out.append(pending)
            pending = None

    for stt, code, label, note, values in fragments:
        text = _has_text(label)
        if not text and stt is None and not values and code is None and not note:
            continue
        if not text and stt is None:
            target = pending
            if target is None and out and not (set(values) & {k for k, v in out[-1]["values"].items() if v}) \
                    and (code is None or out[-1]["code"] in (None, code)):
                target = out[-1]
            if target is not None:
                target["code"] = target["code"] or code
                target["note"] = target["note"] or note
                target["values"].update(values)
                if target is pending and values:
                    flush()
                continue
        if text and stt is None and _starts_lower(label) and (pending is not None or (out and code is None)):
            target = pending if pending is not None else out[-1]
            if target is pending or not values or not any(target["values"].values()):
                target["label"] = (target["label"] + " " + label).strip()
                target["code"] = target["code"] or code
                target["note"] = target["note"] or note
                target["values"].update(values)
                if target is pending and values:
                    flush()
                continue
        flush()
        row = {"stt": stt, "code": code, "label": label, "note": note, "page": page, "values": dict(values)}
        if values:
            out.append(row)
        else:
            pending = row
    flush()
    for r in out:
        r["values"] = {k: (clean_value(v) or None) if v else None
                       for k in COLUMN_KINDS[statement] for v in [r["values"].get(k)]}
    return out


def clean_words(words) -> list[tuple]:
    """Bỏ nét kẻ bảng OCR đọc nhầm thành chữ ("3.624.565|", "|V.04|"): tách chữ tại "|", bỏ ký tự kẻ ở hai đầu; hộp
    chữ của từng mảnh chia theo tỉ lệ số ký tự."""
    out = []
    for w in words:
        text = w[4]
        if not any(c in text for c in BORDER):
            out.append(tuple(w))
            continue
        n = max(1, len(text))
        pos = 0
        for part in re.split(r"([|¦])", text):
            start, pos = pos, pos + len(part)
            piece = part.strip(BORDER)
            if not piece:
                continue
            x0 = w[0] + (w[2] - w[0]) * (start + part.index(piece)) / n
            x1 = x0 + (w[2] - w[0]) * len(piece) / n
            out.append((x0, w[1], x1, w[3], piece, *w[5:]))
    return out


def rows_from_words(words, page: int, statement: str, val_tol: float = 25.0, code_tol: float = 20.0) -> list[dict]:
    """Dựng các dòng dạng Soi từ hộp chữ của một trang (tọa độ theo điểm của trang PDF, đã xoay đúng chiều).

    Luật: gom hàng ngang theo tung độ; số tiền xếp vào cột theo mép phải (cột số đếm theo cụm, ánh xạ map_kinds); mã
    số là chữ dạng 2-3 chữ số nằm ở cột Mã số (tâm cụm, sai lệch <= code_tol); còn lại là tên chỉ tiêu (bỏ số thứ tự
    đầu dòng và thuyết minh cuối tên); các hàng ngang ghép thành dòng chỉ tiêu bằng assemble."""
    rows = visual_rows(clean_words(words))
    cols = value_columns(rows, len(COLUMN_KINDS[statement]))
    if not cols:
        return []
    kinds = map_kinds(statement, len(cols))
    left_edge = min(cols) - 140           # số tiền dài nhất khoảng 130 điểm (như đáp án)
    code_x = code_column(rows, left_edge + 5)
    fragments = []
    for _, ws in rows:
        values: dict[str, str] = {}
        text: list[str] = []
        code = None
        for w in ws:
            t = w[4]
            if w[0] >= left_edge and is_amount(t):
                i = min(range(len(cols)), key=lambda k: abs(cols[k] - w[2]))
                if abs(cols[i] - w[2]) <= val_tol:
                    values[kinds[i]] = (values[kinds[i]] + " " + t) if kinds[i] in values else t
                    continue
            if code is None and code_x is not None and CODE.match(t) and abs((w[0] + w[2]) / 2 - code_x) <= code_tol:
                code = t
                continue
            text.append(t)
        stt, label, note = split_label(text)
        fragments.append((stt, code, label, note, values))
    return assemble(fragments, page, statement)


def unit_text(words) -> str | None:
    """Dòng ghi đơn vị tính ("Đơn vị tính: VND") trong các hộp chữ của trang."""
    for _, ws in visual_rows(words):
        line = " ".join(w[4] for w in ws)
        if "đơn vị" in unicodedata.normalize("NFC", line).casefold():
            return line
    return None


def tesseract_words(tsv: str, scale: float) -> list[tuple]:
    """TSV của Tesseract -> hộp chữ (x0, y0, x1, y1, chữ, độ tin cậy) theo điểm của trang (scale = điểm / điểm ảnh)."""
    out = []
    lines = tsv.splitlines()
    if not lines:
        return out
    head = lines[0].split("\t")
    idx = {k: i for i, k in enumerate(head)}
    for line in lines[1:]:
        f = line.split("\t")
        if len(f) < len(head) or f[idx["level"]] != "5":
            continue
        text = unicodedata.normalize("NFC", f[idx["text"]].strip())
        if not text:
            continue
        x, y, w, h = (int(f[idx[k]]) for k in ("left", "top", "width", "height"))
        out.append((x * scale, y * scale, (x + w) * scale, (y + h) * scale, text, float(f[idx["conf"]])))
    return out


def rows_from_grid(grid: list[list[str]], page: int, statement: str) -> list[dict]:
    """Lưới một bảng (danh sách hàng, mỗi hàng là chữ của từng ô theo cột) -> các dòng dạng Soi.

    Cột số: cột có ít nhất 3 số có dấu phân cách hàng nghìn và phần lớn ô có chữ là số tiền; giữ các cột bên phải nhất,
    ánh xạ map_kinds theo thứ tự. Cột Mã số: cột bên trái cột số mà phần lớn ô có chữ là cụm 2-3 chữ số. Các cột còn lại
    bên trái cột số ghép thành tên chỉ tiêu; các hàng ghép thành dòng chỉ tiêu bằng assemble (như rows_from_words)."""
    if not grid:
        return []
    ncol = max(len(r) for r in grid)
    def clean_cell(c: str) -> str:            # nét kẻ bảng đọc thành chữ: bỏ trong từng chữ
        return " ".join(t for t in (x.strip(BORDER) for x in (c or "").replace("|", " ").replace("¦", " ").split()) if t)

    grid = [[clean_cell(c) for c in r] + [""] * (ncol - len(r)) for r in grid]

    def share(j, test) -> tuple[float, int]:
        cells = [r[j] for r in grid if r[j]]
        return (sum(bool(test(c)) for c in cells) / len(cells)) if cells else 0.0, len(cells)

    def amount_cell(c: str) -> bool:
        return all(is_amount(x) for x in c.split())

    numeric = [j for j in range(ncol)
               if sum(1 for r in grid if r[j] and amount_cell(r[j]) and GROUPED.search(r[j])) >= 3
               and share(j, amount_cell)[0] >= 0.6]
    if not numeric:
        return []
    numeric = numeric[-len(COLUMN_KINDS[statement]):]
    kinds = map_kinds(statement, len(numeric))
    code_col = next((j for j in range(numeric[0]) if share(j, CODE.match)[0] >= 0.6 and share(j, CODE.match)[1] >= 4),
                    None)
    label_cols = [j for j in range(numeric[0]) if j != code_col]
    fragments = []
    for r in grid:
        values = {kind: r[j] for j, kind in zip(numeric, kinds) if r[j]}   # chữ lạ trong cột số giữ nguyên: bộ chấm tính sai
        code_text = clean_value(r[code_col]) if code_col is not None else ""
        code = code_text if CODE.match(code_text) else None
        tokens = [t.strip(BORDER) for j in label_cols for t in r[j].replace("|", " ").split()]
        stt, label, note = split_label([t for t in tokens if t])
        if code_text and code is None:
            note = note or code_text
        fragments.append((stt, code, label, note, values))
    return assemble(fragments, page, statement)


def layout_text(words, page_width: float, chars: int = 160) -> str:
    """Hộp chữ của một trang -> văn bản giữ vị trí cột bằng khoảng trắng (mỗi hàng ngang một dòng), làm đầu vào cho
    mô hình văn bản ở M4."""
    lines = []
    for _, ws in visual_rows(words):
        line = ""
        for w in ws:
            col = int(round(w[0] / page_width * chars))
            if len(line) < col:
                line += " " * (col - len(line))
            elif line:
                line += " "
            line += w[4]
        lines.append(line.rstrip())
    return "\n".join(lines)


def revert_first_pass(record: dict) -> tuple[dict, list[str]]:
    """Bản ghi Soi đã lưu -> bản ghi lần đọc đầu: hoàn nguyên các ô do bước định vị bằng ràng buộc sửa (repairs đã
    nhận), các ô đọc lại được giữ (rereads), bỏ các dòng của trang chép thêm (extensions đã giữ). Báo cáo đã được chép
    lại cả bảng (reextracts đã giữ) thì không còn bản đầu: giữ nguyên và trả tên báo cáo trong danh sách thứ hai."""
    import copy
    rec = copy.deepcopy(record)
    lost = sorted({e["statement"] for e in rec.get("reextracts", []) if e.get("kept")})
    for e in reversed(rec.get("rereads") or []):
        if e.get("kept") and e["statement"] not in lost:
            row = next((r for r in rec["raw"][e["statement"]]["rows"]
                        if (r.get("code") or "").strip().lower() == str(e["code"]).lower()), None)
            if row is not None:
                row["values"][e["column_kind"]] = e["before"]
    for e in reversed(rec.get("repairs") or []):
        if e.get("accepted") and e["statement"] not in lost:
            rec["raw"][e["statement"]]["rows"][e["row"]]["values"][e["column_kind"]] = e["before"]
    for e in rec.get("extensions") or []:
        if e.get("kept") and e["statement"] not in lost:
            raw = rec["raw"][e["statement"]]
            raw["rows"] = [r for r in raw["rows"] if int(r.get("page") or 0) != int(e["page"])]
    return rec, lost


# ---------------------------------------------------------------------------------------------------------------
# Chuẩn bị: danh sách BCTC, trang, góc xoay, ảnh dùng chung (image soi-app)

def _entries_files():
    sys.path.insert(0, str(Path(__file__).parent))
    from born_digital import _infer_sep
    from services.extraction.sources import candidates, open_pdf
    root = raw_dir() / "born_digital"
    for e in json.loads((root / "set.json").read_text(encoding="utf-8")):
        if e.get("excluded"):
            continue
        name = f"{e['ticker']}_{e['period']}_{e['year']}"
        src = open_pdf(candidates(root / "pdf" / e["file"])[0])
        key = json.loads((root / "runs" / f"{name}_goc.json").read_text(encoding="utf-8"))
        yield name, src, key, _infer_sep(src), False


def _entries_db(conn):
    from services.extraction.pipeline import _load_record, open_record_pdf
    for d in DB_DOCS:
        key = _load_record(conn, d)
        yield str(d), open_record_pdf(conn, key), key, key.get("thousands_sep"), True


def load_sources(conn):
    """(tên, PDF gốc, bản ghi Soi ở bản gốc, dấu phân cách của lớp chữ gốc, có trong kho)."""
    yield from _entries_db(conn)
    yield from _entries_files()


def prepare_main(args) -> None:
    sys.path.insert(0, str(Path(__file__).parent))
    from born_digital import LEVELS, VALUE_KINDS, degrade
    from services.db import connect
    from services.extraction.pipeline import _extract_image, _rotation
    import pymupdf

    root = out_dir()
    with connect() as conn:
        for name, src, key, truth_sep, in_db in load_sources(conn):
            if args.only and name not in args.only:
                continue
            chosen = next(c for c in key["candidates"] if c["name"] == key["chosen"])
            st_pages = {st: [int(p) for p in ps] for st, ps in chosen["statement_pages"].items() if st in key["raw"]}
            pages = sorted({p for ps in st_pages.values() for p in ps})
            meta = {"name": name, "ticker": key["ticker"], "doc_type": key.get("doc_type"),
                    "company_template": key["company_template"], "in_db": in_db, "truth_sep": truth_sep,
                    "statement_pages": st_pages, "rotations": {str(p): _rotation(key, p) for p in pages},
                    "key_kinds": {st: [c["kind"] for c in raw.get("columns", []) if c.get("kind") in VALUE_KINDS]
                                  for st, raw in key["raw"].items()},
                    "key_model": key.get("model"),
                    "page_size": {str(p): [src[p - 1].rect.width, src[p - 1].rect.height] for p in pages},
                    "images": {}}
            old = root / "inputs" / f"{name}.json"
            if args.level and old.exists():
                meta["images"] = json.loads(old.read_text(encoding="utf-8"))["images"]
            for lv in args.level or LEVEL_KEYS:
                doc = src
                if lv != "goc":
                    # Bản làm mờ lưu lại thành PDF rồi vẽ ảnh từ chính file đã lưu: phần nhiễu của degrade không lặp lại
                    # được giữa các lần chạy, nên mọi phương pháp (kể cả Soi đọc lại, chạy lệnh run --method M5) phải
                    # dùng đúng file này
                    pdf = root / "degraded" / lv / f"{name}.pdf"
                    pdf.parent.mkdir(parents=True, exist_ok=True)
                    pdf.write_bytes(degrade(src, LEVELS[lv]).tobytes())
                    doc = pymupdf.open(pdf)
                meta["images"][lv] = {}
                for p in pages:
                    png = _extract_image(doc, p, _rotation(key, p))
                    path = root / "images" / lv / f"{name}_p{p}.png"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(png)
                    from PIL import Image
                    import io
                    w, h = Image.open(io.BytesIO(png)).size
                    meta["images"][lv][str(p)] = {"file": str(path.relative_to(root)).replace("\\", "/"), "width": w,
                                                  "height": h, "sha256": hashlib.sha256(png).hexdigest()}
            (root / "inputs").mkdir(parents=True, exist_ok=True)
            (root / "inputs" / f"{name}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                                         encoding="utf-8")
            print(f"[{name}] {len(pages)} trang x {len(LEVEL_KEYS)} mức; trang {st_pages}", flush=True)


def load_inputs(only=None) -> list[dict]:
    files = sorted((out_dir() / "inputs").glob("*.json"))
    metas = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    return [m for m in metas if not only or m["name"] in only]


def _image_path(meta: dict, lv: str, page: int) -> Path:
    return out_dir() / meta["images"][lv][str(page)]["file"]


def _scale(meta: dict, lv: str, page: int) -> float:
    """Điểm trang / điểm ảnh (trang không xoay; ảnh xoay 90/270 thì cạnh đổi chỗ)."""
    w_pt, h_pt = meta["page_size"][str(page)]
    rot = int(meta["rotations"].get(str(page), 0))
    if rot in (90, 270):
        w_pt, h_pt = h_pt, w_pt
    return w_pt / meta["images"][lv][str(page)]["width"]


def _record(meta: dict, method: str, lv: str, raw: dict, seconds: float, usd: float = 0.0, **extra) -> dict:
    """Bản ghi dạng Soi. Cột ghi theo loại cột của đáp án (meta key_kinds) để mọi phương pháp chấm trên cùng đáp án."""
    for st, r in raw.items():
        r["columns_method"] = r.get("columns")
        r["columns"] = [{"header": k, "kind": k} for k in meta["key_kinds"].get(st, [])]
    return {"document_id": int(meta["name"]) if meta["in_db"] else meta["name"], "ticker": meta["ticker"],
            "doc_type": meta["doc_type"], "company_template": meta["company_template"], "method": method, "level": lv,
            "raw": raw, "chosen": "eval",
            "candidates": [{"name": "eval", "statement_pages": meta["statement_pages"],
                            "rotations": meta["rotations"]}],
            "seconds": round(seconds, 2), "usd": usd, **extra}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------------------------------------------
# Các phương pháp

# Chế độ chia trang của Tesseract: chốt trên BCTC phát triển PLC_Q2_2025 ở bản gốc (so --psm 3, 4, 6), không chỉnh sau
# đó. Biến môi trường METHODS_PSM và METHODS_VARIANT (hậu tố thư mục kết quả) chỉ dùng cho lượt thử trên BCTC đó.
TESSERACT_PSM = os.environ.get("METHODS_PSM", "3")


def method_dir(m: str) -> Path:
    return out_dir() / (m + os.environ.get("METHODS_VARIANT", ""))


def run_tesseract(meta: dict, lv: str) -> dict:
    """M2 (image soi-methods): Tesseract trên từng ảnh trang, lưu hộp chữ (theo điểm của trang)."""
    pages, t0 = {}, time.monotonic()
    for p_str in meta["images"][lv]:
        p = int(p_str)
        img = _image_path(meta, lv, p)
        scale = _scale(meta, lv, p)
        dpi = round(72 / scale)
        tsv = subprocess.run(["tesseract", str(img), "stdout", "-l", "vie", "--psm", TESSERACT_PSM, "--dpi", str(dpi),
                              "tsv"], capture_output=True, text=True, encoding="utf-8", check=True).stdout
        pages[p_str] = {"words": tesseract_words(tsv, scale), "width_pt": meta["images"][lv][p_str]["width"] * scale}
    version = subprocess.run(["tesseract", "--version"], capture_output=True, text=True).stdout.splitlines()[0]
    return {"engine": version, "psm": TESSERACT_PSM, "seconds": time.monotonic() - t0, "pages": pages}


_DOCLING = None


def _docling_converter():
    global _DOCLING
    if _DOCLING is None:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (PdfPipelineOptions, TableFormerMode, TesseractCliOcrOptions)
        from docling.document_converter import DocumentConverter, ImageFormatOption
        opts = PdfPipelineOptions(do_ocr=True, do_table_structure=True,
                                  ocr_options=TesseractCliOcrOptions(lang=["vie"], force_full_page_ocr=True),
                                  artifacts_path=os.environ.get("DOCLING_ARTIFACTS_PATH"))
        opts.table_structure_options.mode = TableFormerMode.ACCURATE
        _DOCLING = DocumentConverter(format_options={InputFormat.IMAGE: ImageFormatOption(pipeline_options=opts)})
    return _DOCLING


def run_docling(meta: dict, lv: str) -> dict:
    """M3 (image soi-methods): Docling trên từng ảnh trang, lưu lưới chữ của mọi bảng tìm được và văn bản trang."""
    conv = _docling_converter()
    pages, t0 = {}, time.monotonic()
    for p_str in meta["images"][lv]:
        res = conv.convert(str(_image_path(meta, lv, int(p_str))))
        tables = []
        for t in res.document.tables:
            grid = [[""] * t.data.num_cols for _ in range(t.data.num_rows)]
            for c in t.data.table_cells:
                if c.start_row_offset_idx < t.data.num_rows and c.start_col_offset_idx < t.data.num_cols:
                    grid[c.start_row_offset_idx][c.start_col_offset_idx] = unicodedata.normalize("NFC", c.text or "")
            tables.append(grid)
        texts = [unicodedata.normalize("NFC", x.text) for x in res.document.texts if getattr(x, "text", None)]
        pages[p_str] = {"tables": tables, "texts": texts}
    from importlib.metadata import version
    return {"engine": f"docling {version('docling')}", "seconds": time.monotonic() - t0, "pages": pages}


def convert_words(meta: dict, lv: str, raw_out: dict, method: str) -> dict:
    """Hộp chữ (M1, M2) -> bản ghi dạng Soi."""
    raw = {}
    for st, pages in meta["statement_pages"].items():
        rows, unit = [], None
        for p in pages:
            words = raw_out["pages"][str(p)]["words"]
            rows += rows_from_words(words, p, st)
            unit = unit or unit_text(words)
        raw[st] = {"unit_text": unit, "columns": None, "rows": rows}
    n_pages = max(1, len(raw_out["pages"]))
    return _record(meta, method, lv, raw, raw_out["seconds"], seconds_per_page=raw_out["seconds"] / n_pages)


def convert_docling(meta: dict, lv: str, raw_out: dict) -> dict:
    raw = {}
    for st, pages in meta["statement_pages"].items():
        rows, unit = [], None
        for p in pages:
            page = raw_out["pages"][str(p)]
            for grid in page["tables"]:
                rows += rows_from_grid(grid, p, st)
            unit = unit or next((t for t in page["texts"] if "đơn vị" in t.casefold()), None)
        raw[st] = {"unit_text": unit, "columns": None, "rows": rows}
    return _record(meta, "M3", lv, raw, raw_out["seconds"])


def run_text_layer(meta: dict, src) -> dict:
    """M1: hộp chữ của lớp chữ PDF (chỉ có ở bản gốc)."""
    import pymupdf
    pages, t0 = {}, time.monotonic()
    for p_str in meta["images"]["goc"]:
        page = src[int(p_str) - 1]
        words = page.get_text("words")
        if page.rotation:
            m = page.rotation_matrix
            words = [(*(pymupdf.Rect(w[:4]) * m).normalize(), *w[4:]) for w in words]
        pages[p_str] = {"words": [(w[0], w[1], w[2], w[3], unicodedata.normalize("NFC", w[4])) for w in words],
                        "width_pt": page.rect.width}
    return {"engine": f"pymupdf {pymupdf.__version__}", "seconds": time.monotonic() - t0, "pages": pages}


def text_prompt(statement: str) -> str:
    """Lời nhắc chép bảng của Soi (prompts.extract_prompt) đổi đầu vào từ ảnh sang văn bản OCR; phần còn lại giữ
    nguyên chữ. Thay đổi: câu mở đầu (ảnh -> văn bản OCR giữ vị trí cột) và "số trang N của ảnh" -> "của trang"."""
    from services.extraction import prompts
    p = prompts.extract_prompt(statement)
    head_old = (f"Các ảnh sau là {prompts._STATEMENT_NAME[statement]} trong một BCTC Việt Nam (bản scan). "
                "Mỗi ảnh có nhãn \"Trang N\".")
    head_new = (f"Văn bản sau là kết quả nhận dạng chữ (OCR) của {prompts._STATEMENT_NAME[statement]} trong một BCTC "
                "Việt Nam (bản scan). Mỗi trang bắt đầu bằng nhãn \"Trang N\"; mỗi dòng văn bản là một hàng ngang trên "
                "trang, khoảng trắng giữ gần đúng vị trí cột. Chữ OCR có thể sai.")
    assert head_old in p, "lời nhắc chép bảng của Soi đã đổi: sửa text_prompt"
    p = p.replace(head_old, head_new).replace("- page: số trang N của ảnh chứa dòng đó.",
                                              "- page: số trang N chứa dòng đó.")
    return p


def run_text_llm(meta: dict, client, ocr: dict, max_usd: float) -> dict:
    """M4: chữ OCR của M2 (cùng mức ảnh) + mô hình văn bản, cùng schema và lời nhắc của Soi (đã đổi đầu vào)."""
    from services.extraction import prompts
    from services.extraction.pipeline import fix_row_pages
    usd0, t0 = client.usage.usd, time.monotonic()
    raw = {}
    for st, pages in meta["statement_pages"].items():
        if client.usage.usd >= max_usd:
            raise RuntimeError(f"Dừng: đã tiêu {client.usage.usd:.4f} USD, chạm trần {max_usd} USD")
        text = "\n\n".join(f"Trang {p}\n" + layout_text(ocr["pages"][str(p)]["words"], ocr["pages"][str(p)]["width_pt"])
                           for p in pages)
        out = client.json_from_images(text_prompt(st) + "\n\n" + text, [], prompts.extract_schema(st),
                                      f"statement_{st}", step=f"statement_text_{st}")
        raw[st] = fix_row_pages(out, pages)
    return _record(meta, "M4", "?", raw, time.monotonic() - t0, client.usage.usd - usd0,
                   model=client.cfg.model, provider=client.cfg.provider)


def _born_digital_usd(name: str, lv: str) -> float:
    """Chi phí lần đọc của born_digital cho cùng BCTC, cùng mức (để ước chi phí trước khi chạy)."""
    path = raw_dir() / "born_digital" / "runs" / f"{name}_{lv}.json"
    return json.loads(path.read_text(encoding="utf-8")).get("usd", 0.13) if path.exists() else 0.13


def run_soi(meta: dict, lv: str, client) -> dict:
    """M5 trên đúng file làm mờ đã lưu: quy trình đọc của born_digital.read_pdf (chép bảng từng báo cáo bằng ảnh của
    hệ thống, rồi leo thang: định vị ô bằng ràng buộc, đọc lại, chép lại), cùng trang và góc xoay, không ghi CSDL.
    Ảnh lần chép đầu được so mã băm với bộ ảnh chung trước khi gọi mô hình."""
    import pymupdf

    from services.extraction import prompts
    from services.extraction.pipeline import (_check, _escalate, _extract_detail, _extract_image, _rotation,
                                              fix_row_pages)
    doc = pymupdf.open(out_dir() / "degraded" / lv / f"{meta['name']}.pdf")
    usd0, t0 = client.usage.usd, time.monotonic()
    chosen = {"pages": [], "statement_pages": {st: list(ps) for st, ps in meta["statement_pages"].items()},
              "rotations": dict(meta["rotations"])}
    record = {"document_id": int(meta["name"]) if meta["in_db"] else meta["name"], "ticker": meta["ticker"],
              "doc_type": meta["doc_type"], "company_template": meta["company_template"], "model": client.cfg.model,
              "provider": client.cfg.provider, "level": lv, "method": "M5", "raw": {},
              "candidates": [dict(chosen, name="eval")], "chosen": "eval"}
    for st, pages in chosen["statement_pages"].items():
        images = []
        for p in pages:
            png = _extract_image(doc, p, _rotation(record, p))
            if hashlib.sha256(png).hexdigest() != meta["images"][lv][str(p)]["sha256"]:
                raise RuntimeError(f"{meta['name']} {lv} trang {p}: ảnh khác bộ ảnh chung")
            images.append((f"Trang {p}", png))
        record["raw"][st] = fix_row_pages(client.json_from_images(prompts.extract_prompt(st), images,
                                                                  prompts.extract_schema(st), f"statement_{st}",
                                                                  detail=_extract_detail(doc, pages)), pages)
    _escalate(record, client, doc, None)
    _, _, sep, _, checks = _check(record)
    record["thousands_sep"] = sep
    record["gate_failed"] = sum(c.gate and not c.passed for c in checks)
    record["usd"] = client.usage.usd - usd0
    record["seconds"] = round(time.monotonic() - t0, 2)
    return record


def run_main(args) -> None:
    metas = load_inputs(args.only)
    m = args.method
    levels = args.level or (["goc"] if m == "M1" else LEVEL_KEYS)
    client = None
    spent: list[float] = []
    src_of = {}
    if m in ("M1",):
        from services.db import connect
        with connect() as conn:
            src_of = {name: src for name, src, *_ in load_sources(conn) if not args.only or name in args.only}
    for lv in levels:
        for meta in metas:
            name = meta["name"]
            path = method_dir(m) / lv / f"{name}.json"
            raw_path = method_dir(m) / lv / f"{name}.raw.json"
            if path.exists() and not args.force:
                continue
            if m == "M1":
                if lv != "goc":
                    continue          # bản làm mờ chỉ có ảnh, không có lớp chữ
                raw_out = run_text_layer(meta, src_of[name])
                _save(raw_path, raw_out)
                rec = convert_words(meta, lv, raw_out, "M1")
            elif m == "M2":
                raw_out = json.loads(raw_path.read_text(encoding="utf-8")) if raw_path.exists() else run_tesseract(meta, lv)
                _save(raw_path, raw_out)
                rec = convert_words(meta, lv, raw_out, "M2")
            elif m == "M3":
                raw_out = json.loads(raw_path.read_text(encoding="utf-8")) if raw_path.exists() else run_docling(meta, lv)
                _save(raw_path, raw_out)
                rec = convert_docling(meta, lv, raw_out)
            elif m == "M4":
                ocr_path = method_dir("M2") / lv / f"{name}.raw.json"
                if not ocr_path.exists():
                    print(f"[{name}] {lv}: chưa có chữ OCR của M2, bỏ qua", flush=True)
                    continue
                if client is None:
                    from services.llm import VisionClient, config
                    client = VisionClient(config())          # chỉ nhà chính (Haiku 5.5), không chuyển nhà dự phòng
                est = max(spent or [0.015])                  # lượt đắt nhất đã gặp
                if client.usage.usd + est > args.max_usd:
                    print(f"[{name}] {lv}: dừng, đã tiêu {client.usage.usd:.4f} USD, lượt kế ước {est:.4f} USD "
                          f"sẽ vượt trần {args.max_usd} USD", flush=True)
                    break
                rec = run_text_llm(meta, client, json.loads(ocr_path.read_text(encoding="utf-8")), args.max_usd)
                rec["level"] = lv
            elif m == "M5":
                if lv not in ("vua", "xau"):
                    continue          # bản gốc và 200 dpi không có nhiễu: kết quả born_digital đã đọc đúng ảnh này
                if client is None:
                    from services.llm import VisionClient
                    client = VisionClient()                   # cấu hình hiện tại của hệ thống, như born_digital
                est = 1.25 * _born_digital_usd(name, lv)
                if client.usage.usd + est > args.max_usd:
                    print(f"[{name}] {lv}: bỏ qua, đã tiêu {client.usage.usd:.4f} USD, lượt này ước {est:.3f} USD "
                          f"sẽ vượt trần {args.max_usd} USD", flush=True)
                    continue
                rec = run_soi(meta, lv, client)
            else:
                raise SystemExit(f"run không áp dụng cho {m} (M5a/M5b chấm từ kết quả đã lưu)")
            _save(path, rec)
            if m in ("M4", "M5"):
                spent.append(rec["usd"])
            n = sum(len(r["rows"]) for r in rec["raw"].values())
            print(f"[{name}] {m} {LEVEL_NAMES[lv]}: {n} dòng, {rec['seconds']:.1f} s"
                  + (f", {rec['usd']:.4f} USD" if rec.get("usd") else ""), flush=True)
    if client is not None:
        print(f"Tổng chi phí lần chạy: {client.usage.usd:.4f} USD ({client.usage.input_tokens} token vào, "
              f"{client.usage.output_tokens} token ra, mô hình {client.cfg.model})")


def reconvert_main(args) -> None:
    """Dựng lại bản ghi M1/M2/M3 từ đầu ra thô đã lưu (sau khi sửa bộ chuyển; không chạy lại công cụ)."""
    for meta in load_inputs(args.only):
        for m in ("M1", "M2", "M3"):
            for lv in LEVEL_KEYS:
                raw_path = method_dir(m) / lv / f"{meta['name']}.raw.json"
                if not raw_path.exists():
                    continue
                raw_out = json.loads(raw_path.read_text(encoding="utf-8"))
                rec = convert_docling(meta, lv, raw_out) if m == "M3" else convert_words(meta, lv, raw_out, m)
                _save(method_dir(m) / lv / f"{meta['name']}.json", rec)


# ---------------------------------------------------------------------------------------------------------------
# Chấm (image soi-app)

def soi_record(meta: dict, lv: str, conn) -> dict | None:
    """Bản ghi Soi đã lưu ở mức `lv` (như born_digital: BCTC trong kho ở bản gốc là bản ghi trong kho)."""
    from services.extraction.pipeline import _load_record
    if meta["in_db"] and lv == "goc":
        return _load_record(conn, int(meta["name"]))
    path = raw_dir() / "born_digital" / "runs" / f"{meta['name']}_{lv}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def failed_cells(record: dict) -> set[tuple[str, str | None]]:
    """(báo cáo, cột) có ràng buộc bắt buộc lệch; ràng buộc chéo tính cho cả ba báo cáo."""
    from services.extraction.pipeline import _check, statements_of_rule
    _, _, _, _, checks = _check(record)
    out = set()
    for c in checks:
        if c.gate and not c.passed:
            st = statements_of_rule(c.rule_id)
            for s in (["BS", "IS", "CF"] if st == "X" else [st]):
                out.add((s, c.column_kind))
    return out


def would_verify(record: dict) -> bool:
    """Điều kiện "đã kiểm chứng" của Soi (pipeline._finalize): có mẫu biểu, mọi ràng buộc bắt buộc đạt, có ràng buộc bắt
    buộc trên cả BCĐKT và KQKD, kiểm được tổng tài sản = tổng nguồn vốn. BCTC không đạt thì vào hàng chờ người xem dù
    không ràng buộc nào lệch (ví dụ mất mã số nên không ràng buộc nào chạy được)."""
    from services.extraction.pipeline import BALANCE_RULE, _check, statements_of_rule
    _, _, _, template, checks = _check(record)
    gate = [c for c in checks if c.gate]
    covered = {statements_of_rule(c.rule_id) for c in gate}
    return bool(template and gate and all(c.passed for c in gate) and {"BS", "IS"} <= covered
                and any(BALANCE_RULE.search(c.rule_id) for c in gate))


def score_one(record: dict, meta: dict, src, conn) -> tuple[Counter, list[str], list]:
    """Chấm một bản ghi: bộ đếm của born_digital (đúng/sai/thiếu/thừa, BCTC bị báo, ô sai trong BCTC bị báo / lọt qua)
    cộng phép đếm mức ô: ô sai nằm trong cột của một báo cáo có ràng buộc bắt buộc lệch."""
    sys.path.insert(0, str(Path(__file__).parent))
    from born_digital import _tally_flag, compare_record, flagged
    cells: list = []
    t = compare_record(record, src, meta["name"], False, truth_sep=meta["truth_sep"], wrong=cells)
    reasons = flagged(record, conn, int(meta["name"])) if meta["in_db"] else flagged(record)
    _tally_flag(t, reasons)
    wrong_n = sum(v for k, v in t.items() if k.startswith("tự động") and k != "tự động: đúng")
    released = would_verify(record) and not reasons
    t["BCTC tự đi ra ngoài"] += released
    t["ô sai trong BCTC tự đi ra ngoài" if released else "ô sai trong BCTC chờ người xem"] += wrong_n
    bad = failed_cells(record)
    for st, _, kind, result, *_ in cells:
        if result != "đúng":
            t["ô sai trong cột có phép kiểm lệch" if (st, kind) in bad else "ô sai không phép kiểm nào lệch"] += 1
    return t, reasons, cells


def key_cells(cells: list) -> Counter:
    """Các ô của đáp án (có số in) theo (báo cáo, trang, cột, chữ số của số in). Không dùng tên dòng: đáp án dựng theo
    hai cách (gom hàng / bảng kẻ ô) cho tên hơi khác nhau, bộ chấm chọn cách theo từng đầu ra."""
    return Counter((st, p, kind, re.sub(r"\D", "", raw)) for st, _, kind, result, p, _, raw in cells
                   if raw is not None and result in ("đúng", "sai", "thiếu"))


def correct_cells(cells: list) -> Counter:
    return Counter((st, p, kind, re.sub(r"\D", "", raw)) for st, _, kind, result, p, _, raw in cells
                   if result == "đúng" and raw is not None)


def score_main(args) -> None:
    """Chấm mọi lượt đã có. Ngoài số của bộ chấm (ô đúng / mọi ô có số ở đáp án hoặc ở đầu ra, trong vùng trang mà
    phương pháp ghép được dòng), đếm thêm số ô đúng trên một bộ ô đáp án cố định cho mọi phương pháp: các ô có số của
    đáp án trong vùng mà Soi ghép được ở bản gốc (3.106 ô); vùng chấm của bộ chấm đổi theo phương pháp nên hai tổng
    khác nhau."""
    from services.db import connect
    methods = args.method or METHODS
    metas = {m["name"]: m for m in load_inputs(args.only)}
    results: dict = {}
    examples: dict = {}
    with connect() as conn:
        for name, src, key, _, _ in load_sources(conn):
            if name not in metas:
                continue
            meta = metas[name]
            _, _, soi_cells = score_one(soi_record(meta, "goc", conn), meta, src, conn)
            fixed = key_cells(soi_cells)
            for m in methods:
                for lv in LEVEL_KEYS:
                    lost = []
                    if m in ("M5a", "M5b", "M5a_cungAnh", "M5b_cungAnh"):
                        if m.endswith("_cungAnh"):
                            path = method_dir("M5") / lv / f"{name}.json"
                            rec = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
                        else:
                            rec = soi_record(meta, lv, conn)
                        if rec is None:
                            continue
                        if m.startswith("M5a"):
                            rec, lost = revert_first_pass(rec)
                    else:
                        path = method_dir(m) / lv / f"{name}.json"
                        if not path.exists():
                            continue
                        rec = json.loads(path.read_text(encoding="utf-8"))
                    t, reasons, cells = score_one(rec, meta, src, conn)
                    t["ô đáp án cố định"] += sum(fixed.values())
                    t["ô đáp án cố định đọc đúng"] += sum((correct_cells(cells) & fixed).values())
                    if lost:
                        t["báo cáo không dựng lại được lần đầu"] += len(lost)
                    secs = rec.get("seconds")
                    if m in ("M5a", "M5b"):
                        secs = (rec.get("usage") or {}).get("seconds")
                    t["giây"] += secs or 0
                    t["BCTC có giờ chạy"] += secs is not None
                    usd = rec.get("usd") if rec.get("usd") is not None else (rec.get("usage") or {}).get("usd")
                    t["usd_micro"] += round((usd or 0) * 1e6)
                    t["BCTC"] += 1
                    results.setdefault((m, lv), Counter()).update(t)
                    for c in cells:
                        if c[3] != "đúng":
                            examples.setdefault((m, lv), []).append((name, *c))
                    n = sum(v for k, v in t.items() if k.startswith("tự động:"))
                    if args.verbose:
                        print(f"[{name}] {m} {LEVEL_NAMES[lv]}: {t['tự động: đúng']}/{n}; đáp án cố định "
                              f"{t['ô đáp án cố định đọc đúng']}/{t['ô đáp án cố định']}; báo: "
                              f"{', '.join(reasons[:4]) or 'không'}" + (f"; không dựng lại được {lost}" if lost else ""),
                              flush=True)
    rows = []
    print("\nPhương pháp | Mức | Ô đúng/tổng của bộ chấm (%) | Đúng trên 3.106 ô đáp án cố định (%) | Ô sai | "
          "Sai trong BCTC bị báo | Lọt | Sai trong cột có phép kiểm lệch | BCTC bị báo | BCTC tự kiểm chứng xong | "
          "Sai trong BCTC tự kiểm chứng xong | Giây/BCTC | USD/BCTC")
    for m in methods:
        for lv in LEVEL_KEYS:
            t = results.get((m, lv))
            if not t:
                continue
            n = sum(v for k, v in t.items() if k.startswith("tự động:"))
            ok = t["tự động: đúng"]
            sec = t["giây"] / t["BCTC có giờ chạy"] if t["BCTC có giờ chạy"] else None
            row = {"method": m, "level": lv, "bctc": t["BCTC"], "correct": ok, "total": n, "wrong": n - ok,
                   "sai": t["tự động: sai"], "thieu": t["tự động: thiếu"], "thua": t["tự động: thừa"],
                   "fixed_key": t["ô đáp án cố định"], "fixed_key_correct": t["ô đáp án cố định đọc đúng"],
                   "flagged_bctc": t["BCTC bị báo"], "wrong_in_flagged": t["ô sai trong BCTC bị báo"],
                   "wrong_slipped": t["ô sai lọt qua"], "wrong_in_failed_column": t["ô sai trong cột có phép kiểm lệch"],
                   "released_bctc": t["BCTC tự đi ra ngoài"], "wrong_released": t["ô sai trong BCTC tự đi ra ngoài"],
                   "wrong_held": t["ô sai trong BCTC chờ người xem"],
                   "unmatched_rows": t["dòng không ghép được"], "missed_rows": t["dòng đáp án bị bỏ sót"],
                   "not_reconstructed": t["báo cáo không dựng lại được lần đầu"],
                   "seconds_per_bctc": sec, "usd_per_bctc": t["usd_micro"] / 1e6 / t["BCTC"]}
            rows.append(row)
            fk = row["fixed_key"] or 1
            print(f"{m} | {LEVEL_NAMES[lv]} | {ok}/{n} ({100 * ok / n if n else 0:.2f}%) | "
                  f"{row['fixed_key_correct']}/{row['fixed_key']} ({100 * row['fixed_key_correct'] / fk:.2f}%) | "
                  f"{row['wrong']} (sai {row['sai']}, thiếu {row['thieu']}, thừa {row['thua']}) | "
                  f"{row['wrong_in_flagged']} | {row['wrong_slipped']} | {row['wrong_in_failed_column']} | "
                  f"{row['flagged_bctc']}/{row['bctc']} | {row['released_bctc']} | {row['wrong_released']} | "
                  + (f"{sec:.1f}" if sec is not None else "không ghi")
                  + f" | {row['usd_per_bctc']:.4f}"
                  + (f" | {row['not_reconstructed']} báo cáo giữ bản cuối" if row["not_reconstructed"] else ""))
    _save(out_dir() / ("summary" + os.environ.get("METHODS_VARIANT", "") + ".json"),
          {"rows": rows, "wrong_cells": {f"{m}|{lv}": v for (m, lv), v in examples.items()}})


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("prepare", help="ghi danh sách trang, góc xoay và ảnh dùng chung (image soi-app, cần CSDL)")
    pr.add_argument("--level", nargs="+", choices=LEVEL_KEYS, help="chỉ dựng lại các mức này")
    pr.add_argument("--only", nargs="+")
    r = sub.add_parser("run", help="chạy một phương pháp; lượt đã có kết quả thì bỏ qua")
    r.add_argument("--method", required=True, choices=["M1", "M2", "M3", "M4", "M5"])
    r.add_argument("--level", nargs="+", choices=LEVEL_KEYS)
    r.add_argument("--only", nargs="+", help="chỉ các tên, ví dụ PLC_Q2_2025 6070")
    r.add_argument("--force", action="store_true", help="chạy lại lượt đã có kết quả (M1-M3 dùng lại đầu ra thô)")
    r.add_argument("--max-usd", type=float, default=0.10,
                   help="M4, M5: không chạy lượt kế khi chi phí lần chạy cộng ước tính của lượt đó vượt mức này")
    c = sub.add_parser("reconvert", help="dựng lại bản ghi M1-M3 từ đầu ra thô đã lưu")
    c.add_argument("--only", nargs="+")
    s = sub.add_parser("score", help="chấm mọi lượt đã có bằng bộ chấm và phép kiểm của Soi (image soi-app)")
    s.add_argument("--method", nargs="+", choices=METHODS)
    s.add_argument("--only", nargs="+")
    s.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    {"prepare": prepare_main, "run": run_main, "reconvert": reconvert_main, "score": score_main}[args.cmd](args)


if __name__ == "__main__":
    main()
