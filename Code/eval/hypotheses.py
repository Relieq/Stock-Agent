"""Chạy phần giả thuyết (services/causes/hypotheses.py) trên mọi BCTC quý đã kiểm chứng hoặc đã duyệt, không gọi mô hình.

    python eval/hypotheses.py [--half dev|test] [--show] [--from 2025 --to 2026]

Đếm số lần mỗi loại bật và, với BCTC có công văn, số lần công văn nhắc tới ý đó. Nửa dev = mã tài liệu chẵn, nửa
test = lẻ: chỉnh ngưỡng chỉ nhìn nửa dev (--show), nửa test đo một lần.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from services.causes.hypotheses import for_document
from services.db import connect
from services.metrics.service import _record, explanation


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--half", choices=("dev", "test"))
    ap.add_argument("--show", action="store_true", help="in từng giả thuyết (không dùng với --half test)")
    ap.add_argument("--doc-id", type=int, nargs="+")
    args = ap.parse_args()
    if args.show and args.half == "test":
        sys.exit("không in từng ca của nửa test")
    kinds, letter = Counter(), Counter()
    docs = with_hit = 0
    with connect() as conn:
        rows = conn.execute(
            """SELECT id, ticker, fiscal_year, fiscal_period, scope FROM documents
               WHERE doc_type = 'fs_quarter' AND content_kind = 'full' AND status IN ('verified', 'approved')
                 AND owner_user_id IS NULL AND duplicate_of IS NULL AND NOT is_amended
                 AND (fiscal_year, fiscal_period) >= (2025, 'Q4') AND (%s::bigint[] IS NULL OR id = ANY(%s))
               ORDER BY fiscal_year, fiscal_period, ticker""", (args.doc_id, args.doc_id)).fetchall()
        for doc_id, ticker, year, period, scope in rows:
            if args.half and (doc_id % 2 == 0) != (args.half == "dev"):
                continue
            rec = _record(conn, doc_id)
            if rec is None:
                continue
            docs += 1
            hs = for_document(conn, doc_id, rec, explanation(conn, ticker, year, period, scope))
            with_hit += bool(hs)
            for h in hs:
                kinds[h.kind] += 1
                letter[(h.kind, h.company)] += 1
                if args.show:
                    print(f"[{doc_id}] {ticker} {period}/{year} {h.kind}: {h.text}")
                    print(f"      {h.company}{': ' + h.company_text[:160] if h.company_text else ''}")
    print(f"\n{docs} BCTC quý, {with_hit} có ít nhất một giả thuyết")
    for k, n in kinds.most_common():
        detail = ", ".join(f"{c} {letter[(k, c)]}" for c in ("công văn có nhắc tới", "công văn không nhắc tới",
                                                              "chưa có công văn") if letter[(k, c)])
        print(f"  {k}: {n} ({detail})")


if __name__ == "__main__":
    main()
