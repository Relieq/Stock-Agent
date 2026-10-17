"""Người đọc thứ hai: chép lại các báo cáo của BCTC đã đọc bằng nhà cung cấp khác hãng với lần đọc đầu, rồi so từng ô
với số đang lưu. Không ghi đè bản ghi trích xuất.

    python eval/second_read.py run [--doc-id 8 10] [--limit 5]   # gọi mô hình, lưu Data/raw/second_read/<id>.json
    python eval/second_read.py compare [--list 50]               # so từng ô, không gọi mô hình

Phép cộng không thấy được lỗi đổi chỗ hai dòng cùng thuộc một tổng (cấy 500 lỗi như vậy, phép kiểm bắt buộc trong chính
BCTC chỉ bắt được 42%), và không phủ các dòng không có phép cộng nào (lãi trên cổ phiếu, mục ngoài bảng của ngân hàng).
Một người đọc khác hãng hầu như không mắc đúng lỗi đó, nên ô hai bên khác nhau là ô cần xem lại; ô hai bên trùng nhau có
thêm một bằng chứng độc lập với phép kiểm.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter
from dataclasses import asdict
from decimal import Decimal

from eval.cell_funnel import NAMES, classify
from services.db import connect
from services.extraction import prompts
from services.extraction.evidence import cells_of
from services.extraction.pipeline import (
    _check_cached,
    _extract_detail,
    _extract_image,
    _load_record,
    _rotation,
    open_record_pdf,
)
from services.ingestion.registry import raw_data_dir
from services.llm import VisionClient

STATEMENTS = ("BS", "IS", "CF")


def out_dir():
    d = raw_data_dir() / "second_read"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _documents(conn, ids: list[int] | None) -> list[tuple[int, str, str]]:
    rows = conn.execute("SELECT id, ticker, fiscal_period || '/' || fiscal_year FROM documents WHERE owner_user_id IS NULL "
                        "AND status IN ('verified', 'approved', 'needs_review') ORDER BY id").fetchall()
    return [r for r in rows if ids is None or r[0] in ids]


def statement_pages(record: dict) -> dict[str, list[int]]:
    """Trang của từng báo cáo: trang lần đọc đầu đã chép (theo dòng) cộng trang bước định vị đã chọn."""
    chosen = next((c for c in record.get("candidates", []) if c.get("name") == record.get("chosen")), {})
    out = {}
    for st in STATEMENTS:
        pages = {int(p) for p in (chosen.get("statement_pages") or {}).get(st, [])}
        pages |= {int(r["page"]) for r in record.get("raw", {}).get(st, {}).get("rows", []) if r.get("page")}
        if pages:
            out[st] = sorted(pages)
    return out


def run(ids: list[int] | None, limit: int | None) -> None:
    client = VisionClient()
    done = 0
    with connect() as conn:
        for d, ticker, period in _documents(conn, ids):
            path = out_dir() / f"{d}.json"
            if path.exists():
                continue
            if limit is not None and done >= limit:
                break
            record = _load_record(conn, d)
            provider = client.other_than(record.get("provider"))
            doc = open_record_pdf(conn, record)
            before = asdict(client.usage)
            raw, models = {}, set()
            for st, pages in statement_pages(record).items():
                images = [(f"Trang {p}", _extract_image(doc, p, _rotation(record, p))) for p in pages]
                raw[st] = client.json_from_images(prompts.extract_prompt(st), images, prompts.extract_schema(st),
                                                  f"statement_{st}", step=f"second_read_{st}",
                                                  detail=_extract_detail(doc, pages), provider=provider)
                models.add(client.last_model)
            usd = client.usage.usd - before["usd"]
            path.write_text(json.dumps({"document_id": d, "first_reader": f"{record.get('provider')}/{record.get('model')}",
                                        "second_reader": sorted(models), "usd": usd, "raw": raw},
                                       ensure_ascii=False), encoding="utf-8")
            done += 1
            print(f"[{d}] {ticker} {period}: {', '.join(sorted(models))}, {usd:.4f} USD", flush=True)
    print(f"Xong {done} BCTC, tổng {client.usage.usd:.2f} USD")


def compare_document(conn, d: int, period: str) -> list[dict]:
    """Mọi ô có số ở bản đang lưu: trùng / khác / người đọc thứ hai không thấy, kèm nhóm xác nhận (eval/cell_funnel)."""
    path = out_dir() / f"{d}.json"
    if not path.exists():
        return []
    second = json.loads(path.read_text(encoding="utf-8"))
    record = _load_record(conn, d)
    other = copy.deepcopy(record)
    other["raw"] = second["raw"]
    mine, theirs = cells_of(d, period, record), cells_of(d, period, other)
    cats = {(st, row, col): cat for cat, st, row, col, _, _ in classify(conn, d)}
    gate_ok = not [c for c in _check_cached(other)[4] if c.gate and not c.passed]
    out = []
    for (st, row, col), cat in cats.items():
        keys = mine.item_keys.get(st, [])
        key = keys[row] if row < len(keys) else None
        if key is None:
            continue                # lãi trên cổ phiếu và dòng không xác định được khóa
        a = mine.values.get((st, key), {}).get(col)
        b = theirs.values.get((st, key), {}).get(col)
        if b is None and record.get("doc_type") in ("fs_semiannual", "fs_annual"):
            # BCTC bán niên/năm chỉ in một cặp cột cả kỳ; mỗi lần chép có thể ghi vào q_* hoặc ytd_*
            twin = {"q_cur": "ytd_cur", "ytd_cur": "q_cur", "q_prev_year": "ytd_prev_year",
                    "ytd_prev_year": "q_prev_year"}.get(col)
            b = theirs.values.get((st, key), {}).get(twin) if twin else None
        if a is None:
            continue
        result = "không thấy" if b is None else ("trùng" if a == b else "khác")
        out.append({"document_id": d, "statement": st, "row": row, "key": key, "column_kind": col, "cat": cat,
                    "mine": str(a), "theirs": None if b is None else str(b), "result": result,
                    "second_gate_ok": gate_ok})
    return out


def compare(list_n: int) -> None:
    tally: dict[int, Counter] = {}
    docs, gate_ok, usd = 0, 0, 0.0
    differ = []
    with connect() as conn:
        for d, ticker, period in _documents(conn, None):
            rows = compare_document(conn, d, period.split("/")[0])
            if not rows:
                continue
            docs += 1
            gate_ok += rows[0]["second_gate_ok"]
            usd += json.loads((out_dir() / f"{d}.json").read_text(encoding="utf-8")).get("usd") or 0
            for r in rows:
                tally.setdefault(r["cat"], Counter())[r["result"]] += 1
                if r["result"] == "khác":
                    differ.append((ticker, period, r))
    print(f"{docs} BCTC đã có lần đọc thứ hai ({usd:.2f} USD); người đọc thứ hai tự đạt mọi phép kiểm bắt buộc ở "
          f"{gate_ok}/{docs} BCTC")
    for cat in sorted(tally):
        t = tally[cat]
        n = sum(t.values())
        print(f"  {cat}. {NAMES[cat]}: {n:,} ô; trùng {t['trùng']:,} ({100 * t['trùng'] / n:.1f}%), "
              f"khác {t['khác']:,}, không thấy {t['không thấy']:,}")
    for ticker, period, r in differ[:list_n]:
        print(f"  khác: {ticker} {period} (doc {r['document_id']}) {r['statement']} {r['key']} {r['column_kind']} "
              f"nhóm {r['cat']}: lưu {r['mine']} / người thứ hai {r['theirs']}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--doc-id", type=int, nargs="+")
    r.add_argument("--limit", type=int)
    c = sub.add_parser("compare")
    c.add_argument("--list", type=int, default=0, help="in N ô khác nhau đầu tiên")
    args = ap.parse_args()
    if args.cmd == "run":
        run(args.doc_id, args.limit)
    else:
        compare(args.list)


if __name__ == "__main__":
    main()
