"""Thời gian từ lúc BCTC được công bố đến lúc hệ thống có thẻ (time-to-insight), không gọi mô hình.

    python eval/latency.py [--since 2026-10-12] [--verbose]

Lúc công bố là lúc BCTC xuất hiện sớm nhất ở một trong hai nguồn (giờ Vietstock đăng hoặc giờ HOSE đăng). Tách làm hai
đoạn: chờ (công bố -> bộ canh thấy BCTC) và xử lý (thấy -> đọc, kiểm chứng xong). Chỉ tính BCTC đầy đủ (hợp nhất hoặc
duy nhất) của mã đang theo dõi, công bố từ ngày bộ canh chạy thật (--since); BCTC cũ đọc bù không phản ánh tốc độ.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from datetime import timedelta, timezone

from services.db import connect

VN = timezone(timedelta(hours=7))


def _q(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def _fmt(minutes: float) -> str:
    return f"{minutes:.0f} phút" if minutes < 120 else f"{minutes / 60:.1f} giờ"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", default="2026-10-12", help="chỉ tính BCTC công bố từ ngày này (bộ canh chạy thật)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        rows = conn.execute(
            """SELECT d.ticker, d.fiscal_period, d.fiscal_year, d.source,
                      LEAST(d.source_listed_at, d.published_at) AS first_public,
                      CASE WHEN d.published_at < d.source_listed_at OR d.source = 'hose' THEN 'HOSE' ELSE 'Vietstock' END,
                      d.discovered_at, d.processed_at, d.status
               FROM documents d
               WHERE d.content_kind = 'full' AND d.doc_type LIKE 'fs_%%' AND d.scope IN ('consolidated', 'standalone')
                 AND d.owner_user_id IS NULL AND d.duplicate_of IS NULL AND d.processed_at IS NOT NULL
                 AND LEAST(d.source_listed_at, d.published_at) >= %s::date
                 AND d.ticker IN (SELECT ticker FROM companies WHERE tracked)
               ORDER BY first_public""", (args.since,)).fetchall()
    if not rows:
        print(f"Chưa có BCTC nào công bố từ {args.since} đã xử lý xong")
        return
    total, wait, work = [], [], []
    for t, p, y, src, first, where, seen, done, status in rows:
        w = max((seen - first).total_seconds() / 60, 0)
        k = (done - max(seen, first)).total_seconds() / 60
        total.append(w + k)
        wait.append(w)
        work.append(k)
        if args.verbose:
            print(f"  {t} {p}/{y}: công bố {first.astimezone(VN):%H:%M %d/%m} ({where}), thấy sau {_fmt(w)}, "
                  f"xử lý {_fmt(k)}, tổng {_fmt(w + k)} -> {status}")
    print(f"{len(rows)} BCTC công bố từ {args.since}:")
    for name, xs in (("tổng (công bố -> có thẻ)", total), ("chờ bộ canh thấy", wait), ("đọc và kiểm chứng", work)):
        print(f"  {name}: trung vị {_fmt(statistics.median(xs))}, 95% {_fmt(_q(xs, 0.95))}, lâu nhất {_fmt(max(xs))}")


if __name__ == "__main__":
    main()
