"""Dựng lại bảng nhầm chữ số (services/extraction/digit_confusion.json) từ mọi lỗi đã sửa trong các bản ghi, không gọi
mô hình. Chạy lại sau mỗi mùa BCTC để bảng phản ánh người đọc đang dùng.

    python eval/confusion.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from services.db import connect
from services.extraction.confusion import TABLE, count_substitutions, error_pairs
from services.extraction.pipeline import _load_record


def collect(conn) -> list[tuple[str, str]]:
    pairs = []
    for (d,) in conn.execute("SELECT id FROM documents WHERE status IN ('verified', 'approved', 'needs_review')"):
        try:
            pairs += error_pairs(_load_record(conn, d))
        except RuntimeError:
            continue
    return pairs


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="chỉ in, không ghi file")
    args = ap.parse_args()
    with connect() as conn:
        pairs = collect(conn)
    subs = count_substitutions(pairs)
    n = sum(sum(v.values()) for v in subs.values())
    top = sorted(((c, f"{t}->{r}") for t, row in subs.items() for r, c in row.items()), reverse=True)[:10]
    print(f"{len(pairs)} lỗi đã sửa, {n} lỗi nhầm đúng một chữ số; hay gặp nhất (đúng->đọc thành): "
          + ", ".join(f"{k} ({c})" for c, k in top))
    if not args.dry_run:
        TABLE.write_text(json.dumps({"built": date.today().isoformat(), "pairs": len(pairs), "single_digit": n,
                                     "substitutions": subs}, ensure_ascii=False, indent=1, sort_keys=True),
                         encoding="utf-8")
        print(f"Đã ghi {TABLE}")


if __name__ == "__main__":
    main()
