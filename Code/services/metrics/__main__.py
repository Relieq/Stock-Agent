"""Dòng lệnh cho bộ tính chỉ số.

    python -m services.metrics plans [--csv db/seeds/agm_plans_2026.csv]   # nạp kế hoạch ĐHCĐ (cột value_ty: tỷ đồng)
    python -m services.metrics card --ticker FPT --year 2026 --period Q2    # in thẻ KQKD
"""

from __future__ import annotations

import argparse
import csv
import sys
from decimal import Decimal
from pathlib import Path

from services.db import connect
from services.metrics.card import ty
from services.metrics.service import card_for, quarter_document

SEEDS = Path(__file__).resolve().parents[2] / "db" / "seeds"


def cmd_plans(args) -> None:
    n = skipped = 0
    with connect() as conn, open(args.csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not (row.get("value_ty") or "").strip() or not (row.get("source_url") or "").strip():
                skipped += 1
                continue
            value = Decimal(row["value_ty"].strip().replace(".", "").replace(",", ".")) * Decimal(10**9)
            conn.execute(
                """INSERT INTO agm_plans (ticker, fiscal_year, metric, value, source_url, note)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (ticker, fiscal_year, metric) DO UPDATE
                   SET value = EXCLUDED.value, source_url = EXCLUDED.source_url, note = EXCLUDED.note""",
                (row["ticker"].strip().upper(), int(row["fiscal_year"]), row["metric"].strip(), value,
                 row["source_url"].strip(), (row.get("note") or "").strip() or None))
            n += 1
    print(f"Đã nạp {n} kế hoạch; bỏ qua {skipped} dòng chưa điền số hoặc nguồn")


def cmd_card(args) -> None:
    with connect() as conn:
        doc_id = quarter_document(conn, args.ticker.upper(), args.year, args.period)
        got = card_for(conn, doc_id) if doc_id else None
    if got is None:
        sys.exit("Chưa có BCTC đã đọc của kỳ này")
    card, info = got
    print(f"{card.ticker} {card.period}/{card.year} ({info['status']}, {info['gate'][0]}/{info['gate'][1]} ràng buộc)")
    for m in card.metrics:
        print(f"  {m.name}: quý {m.q_change or '-'}; lũy kế {m.ytd_change or '-'}")
    if card.plan:
        print(f"  Lũy kế {card.plan['name']} đạt {card.plan['pct_text']} kế hoạch ({ty(card.plan['plan'])})")
    for f in card.flags:
        print(f"  CỜ {f.title}: {f.detail}")
    for n in card.not_evaluated:
        print(f"  chưa xét: {n}")


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="python -m services.metrics")
    sub = p.add_subparsers(dest="command", required=True)
    pl = sub.add_parser("plans", help="Nạp kế hoạch ĐHCĐ từ CSV")
    pl.add_argument("--csv", default=str(SEEDS / "agm_plans_2026.csv"))
    pl.set_defaults(func=cmd_plans)
    c = sub.add_parser("card", help="In thẻ KQKD của một mã")
    c.add_argument("--ticker", required=True)
    c.add_argument("--year", type=int, required=True)
    c.add_argument("--period", required=True)
    c.set_defaults(func=cmd_card)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
