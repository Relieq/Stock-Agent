"""Chấm kết quả trích xuất với bộ BCTC duyệt tay (Data/golden/*.csv).

    python eval/golden.py                                  # mặc định Data/golden/golden_q2_2026.csv
    python eval/golden.py --golden ../Data/golden/x.csv --pipeline-ver 0.1.0

So sánh số **như in trên BCTC** (cột value_as_printed của bộ duyệt tay với line_items.value_raw), sau khi đổi
chuỗi thành số theo dấu phân tách của từng tài liệu. Dòng được ghép theo mã số in trên BCTC; không có mã số
(ví dụ ngân hàng) thì ghép theo tên chỉ tiêu.
"""

from __future__ import annotations

import argparse
import csv
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from services.db import CODE_DIR, connect
from services.extraction.numbers import infer_thousands_sep, normalize_code, parse_amount
from services.extraction.pipeline import PIPELINE_VER


def _norm_label(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", s).casefold().split())


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--golden", type=Path, default=CODE_DIR.parent / "Data" / "golden" / "golden_q2_2026.csv")
    p.add_argument("--pipeline-ver", default=PIPELINE_VER)
    args = p.parse_args()

    with open(args.golden, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("value_as_printed") or "").strip()]
    if not rows:
        sys.exit("Bộ duyệt tay chưa có ô nào được điền (cột value_as_printed).")

    by_doc: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_doc[int(r["document_id"])].append(r)

    total = correct = missing = 0
    with connect() as conn:
        for doc_id, golden in sorted(by_doc.items()):
            items = conn.execute(
                """
                SELECT li.statement, li.code, li.label_raw, li.column_kind, li.value_raw
                FROM line_items li JOIN document_files f ON f.id = li.file_id
                WHERE f.document_id = %s AND li.pipeline_ver = %s
                """,
                (doc_id, args.pipeline_ver),
            ).fetchall()
            if not items:
                print(f"[{doc_id}] chưa có kết quả trích xuất phiên bản {args.pipeline_ver}")
                continue
            sep_pred = infer_thousands_sep(i[4] for i in items)
            sep_gold = infer_thousands_sep(r["value_as_printed"] for r in golden)
            by_code = {(s, c, col): v for s, c, _, col, v in items if c}
            by_label = defaultdict(list)
            for s, _, label, col, v in items:
                by_label[(s, col)].append((_norm_label(label or ""), v))

            doc_total = doc_ok = 0
            errors = []
            for g in golden:
                st, col = g["statement"], g["column_kind"]
                code = normalize_code(g.get("code_as_printed"))
                if code:
                    pred_raw = by_code.get((st, code, col))
                else:
                    want = _norm_label(g["label_hint"])
                    pred_raw = next((v for lab, v in by_label[(st, col)] if want in lab), None)
                gold = parse_amount(g["value_as_printed"], sep_gold)
                pred = parse_amount(pred_raw, sep_pred) if pred_raw else None
                doc_total += 1
                if pred is None:
                    missing += 1
                    errors.append(f"    thiếu   {st} {code or g['label_hint']} {col}: đúng là {g['value_as_printed']}")
                elif pred == gold:
                    doc_ok += 1
                else:
                    errors.append(f"    sai     {st} {code or g['label_hint']} {col}: đọc {pred_raw}, đúng là {g['value_as_printed']}")
            total += doc_total
            correct += doc_ok
            ticker = golden[0]["ticker"]
            print(f"[{doc_id}] {ticker}: {doc_ok}/{doc_total} ô đúng ({doc_ok / doc_total:.1%})")
            for e in errors:
                print(e)

    if total:
        print(f"\nTổng: {correct}/{total} ô đúng ({correct / total:.1%}); {missing} ô không tìm thấy trong kết quả.")


if __name__ == "__main__":
    main()
