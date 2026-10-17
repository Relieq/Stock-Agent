"""Phân loại mọi ô số đã đọc theo cách được xác nhận (không gọi mô hình).

    python eval/cell_funnel.py [--list-review]

"Được xác nhận" nghĩa là số khớp ít nhất một phép kiểm (phép cộng trong chính BCTC hoặc đối chiếu với BCTC kỳ khác), KHÔNG
phải đã được người đối chiếu với ảnh gốc; chỉ nhóm "sửa tay" là đã đối chiếu ảnh. Nhóm:
  1 đúng ngay lần đọc đầu, có ràng buộc xác nhận
  2 đọc lại riêng ô (định vị ô sai, đối chiếu kỳ, đọc lại) rồi mới khớp
  3 thuộc báo cáo phải chép lại trang rồi mới khớp
  4 sửa tay sau khi đối chiếu ảnh gốc
  5 cần xem lại: phép cộng hoặc BCTC kỳ khác chỉ ra nghi sai, chưa xử lý
  6 chưa kiểm được: không nằm trong phép kiểm nào (kể cả ô khác BCTC kỳ khác mà không có phép cộng nào xác nhận)
  7 lệch do chính BCTC: phép kiểm vẫn lệch nhưng người đã đối chiếu ảnh và duyệt BCTC (in sai trong bản công bố)
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter

from services.db import connect
from services.extraction.evidence import document_evidence
from services.extraction.numbers import normalize_code
from services.extraction.pipeline import _check_cached, _load_record

NAMES = {1: "đúng ngay lần đọc đầu, có ràng buộc xác nhận", 2: "đọc lại riêng ô rồi mới khớp",
         3: "thuộc báo cáo phải chép lại trang", 4: "sửa tay sau khi đối chiếu ảnh",
         5: "cần xem lại (nghi sai, chưa xử lý)", 6: "chưa kiểm được",
         7: "lệch do chính BCTC (đã đối chiếu ảnh, duyệt tay)"}


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def classify(conn, document_id: int) -> list[tuple[int, str, int, str, str, str]]:
    """(nhóm, báo cáo, dòng, cột, mẫu, tên dòng) cho mọi ô có số của một BCTC."""
    rec = _load_record(conn, document_id)
    ev = document_evidence(conn, document_id)
    if ev is None:
        return []
    _, _, _, template, _ = _check_cached(rec)
    approved = conn.execute("SELECT status FROM documents WHERE id = %s", (document_id,)).fetchone()[0] == "approved"
    manual = {(m["statement"], m["row"], m["column_kind"]) for m in rec.get("manual_fixes", [])}
    reread_cells = {(x["statement"], x["row"], x["column_kind"])
                    for k in ("cell_verifications", "repairs") for x in rec.get(k, [])
                    if "row" in x and (x.get("applied") or x.get("accepted"))}
    reextracted = {x["statement"] for x in rec.get("reextracts", []) if x.get("kept")}
    out = []
    for st, raw in rec["raw"].items():
        keys = ev.cells.item_keys.get(st, [])
        for i, row in enumerate(raw["rows"]):
            code = normalize_code(row.get("code"))
            key = keys[i] if i < len(keys) else None
            for col, v in row["values"].items():
                if not _digits(v):
                    continue
                s = ev.status.get((st, key, col), {}) if key else {}
                status = s.get("status", "none")
                rereads = [x for x in rec.get("rereads", []) if x["statement"] == st and code
                           and normalize_code(x.get("code")) == code and x["column_kind"] == col]
                reread_ok = any(_digits(x["after"]) != _digits(x["before"]) and _digits(x["after"]) == _digits(v)
                                for x in rereads)
                if (st, i, col) in manual:
                    cat = 4
                elif (st, i, col) in reread_cells or reread_ok:
                    cat = 2
                elif st in reextracted:
                    cat = 3
                elif status == "conflict":
                    cat = 7 if approved else 5
                elif status == "none" or (status in ("differs", "restated") and not s.get("sum")):
                    cat = 6
                else:
                    cat = 1
                out.append((cat, st, i, col, template or "?", row.get("label") or ""))
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list-review", action="store_true", help="liệt kê các ô nhóm 5 (cần xem lại)")
    args = ap.parse_args()
    tally, by_template, review = Counter(), Counter(), []
    with connect() as conn:
        docs = conn.execute("SELECT id, ticker, fiscal_period || '/' || fiscal_year FROM documents "
                            "WHERE owner_user_id IS NULL AND status IN ('verified', 'approved', 'needs_review') "
                            "ORDER BY id").fetchall()
        for d, ticker, period in docs:
            for cat, st, row, col, template, label in classify(conn, d):
                tally[cat] += 1
                if cat == 6:
                    by_template[template] += 1
                if cat == 5:
                    review.append(f"{ticker} {period} (doc {d}) {st} dòng {row} {label[:40]} {col}")
    n = sum(tally.values())
    print(f"Tổng {n:,} ô số trong {len(docs)} BCTC")
    for cat in sorted(NAMES):
        print(f"  {cat}. {NAMES[cat]}: {tally[cat]:,} ({100 * tally[cat] / n:.1f}%)")
    confirmed = tally[1] + tally[2] + tally[3] + tally[4]
    print(f"Được ràng buộc xác nhận (nhóm 1-4): {confirmed:,} ({100 * confirmed / n:.1f}%)")
    print("Chưa kiểm được theo mẫu:", dict(by_template))
    if args.list_review:
        for r in review:
            print("  cần xem lại:", r)


if __name__ == "__main__":
    main()
