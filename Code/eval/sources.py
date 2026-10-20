"""So thời điểm hai nguồn đăng cùng một BCTC: Vietstock (giờ đăng lại) và HOSE (giờ sở giao dịch đăng).

    python eval/sources.py [--since-year 2025] [--verbose]

Lấy toàn bộ tệp BCTC của từng mã đang theo dõi trên HOSE (nhiều trang, có nghỉ giữa các lần gọi), ghép với BCTC đầy đủ
từ Vietstock trong kho theo mã, kỳ, loại và phạm vi (hợp nhất/riêng/duy nhất), rồi đếm nguồn nào đăng trước. Không
gọi mô hình.
"""

from __future__ import annotations

import argparse
import statistics
import sys

from services.db import connect
from services.ingestion.hose import API, HoseClient, parse_entry
from services.ingestion.registry import raw_data_dir


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since-year", type=int, default=2025, help="từ năm tài chính này (quý 4/2025 trở đi khi là 2025)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    client = HoseClient(ids_path=raw_data_dir() / "hose_ids.json")
    with connect() as conn:
        tickers = [r[0] for r in conn.execute(
            "SELECT ticker FROM companies WHERE tracked AND exchange = 'HOSE' ORDER BY ticker")]
        hose: dict[tuple, object] = {}
        for t in tickers:
            cid = client.company_id(t)
            page, pages = 1, 1
            while cid is not None and page <= pages:
                data = client._get(f"{API}/m/api/v1/1/mediafiles/1/{cid}?pageIndex={page}&pageSize=100")["data"]
                pages = data["paging"]["totalPages"]
                for x in data["list"]:
                    st = parse_entry(t, x)
                    if st is None or st.is_amended or st.fiscal_year < args.since_year:
                        continue
                    k = (t, st.fiscal_year, st.fiscal_period, st.doc_type, st.scope)
                    if k not in hose or st.posted_at < hose[k].posted_at:
                        hose[k] = st
                page += 1
        rows = conn.execute(
            """SELECT ticker, fiscal_year, fiscal_period, doc_type, scope, source_listed_at FROM documents
               WHERE source = 'vietstock' AND content_kind = 'full' AND NOT is_amended AND doc_type LIKE 'fs_%%'
                 AND scope IN ('consolidated', 'separate', 'standalone') AND source_listed_at IS NOT NULL
                 AND (fiscal_year > %s OR (fiscal_year = %s AND fiscal_period = 'Q4'))
                 AND ticker IN (SELECT ticker FROM companies WHERE tracked AND exchange = 'HOSE')""",
            (args.since_year, args.since_year)).fetchall()
    diffs, missing = [], []
    for t, y, p, dt, scope, listed in rows:
        st = hose.get((t, y, p, dt, scope)) or (hose.get((t, y, p, dt, None)) if scope == "standalone" else None)
        if st is None:
            missing.append(f"{t} {p}/{y} {scope}")
            continue
        diffs.append((st.posted_at - listed).total_seconds() / 3600)
        if args.verbose:
            print(f"  {t} {p}/{y} {scope}: HOSE trừ Vietstock {diffs[-1]:+.1f} giờ")
    diffs.sort()
    n = len(diffs)
    early = sum(d < -0.25 for d in diffs)
    late = sum(d > 0.25 for d in diffs)
    print(f"{n} BCTC có ở cả hai nguồn: HOSE đăng trước {early}, Vietstock đăng trước {late}, "
          f"cách nhau dưới 15 phút {n - early - late}; không thấy trên HOSE {len(missing)}")
    if n:
        print(f"HOSE trừ Vietstock (giờ): trung vị {statistics.median(diffs):+.1f}; 10% đầu {diffs[n // 10]:+.1f}; "
              f"90% {diffs[9 * n // 10]:+.1f}")
    if missing and args.verbose:
        print("Không thấy trên HOSE:", ", ".join(missing))


if __name__ == "__main__":
    main()
