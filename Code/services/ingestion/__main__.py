"""Dòng lệnh cho module thu thập.

    python -m services.ingestion migrate
    python -m services.ingestion seed
    python -m services.ingestion discover --year 2026
    python -m services.ingestion report --year 2026 --period Q2
    python -m services.ingestion download --year 2026 --period Q2
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import timedelta, timezone

from services.db import connect, migrate
from services.ingestion.registry import discover, download_pending, seed_companies
from services.ingestion.vietstock import VietstockClient

VN_TZ = timezone(timedelta(hours=7))


def _tickers(conn, arg: str | None) -> list[str]:
    if arg:
        return [t.strip().upper() for t in arg.split(",") if t.strip()]
    return [r[0] for r in conn.execute("SELECT ticker FROM companies ORDER BY ticker")]


def cmd_migrate(args) -> None:
    with connect() as conn:
        done = migrate(conn)
    print("Đã áp dụng: " + ", ".join(done) if done else "CSDL đã ở phiên bản mới nhất.")


def cmd_seed(args) -> None:
    with connect() as conn:
        n = seed_companies(conn)
    print(f"Đã ghi {n} công ty.")


def cmd_discover(args) -> None:
    client = VietstockClient(delay_seconds=args.delay)
    with connect() as conn:
        tickers = _tickers(conn, args.tickers)
        print(f"Lấy danh sách BCTC năm {args.year or 'mọi năm'} cho {len(tickers)} mã...")
        stats = discover(conn, client, tickers, args.year)
    print(f"Xong: {stats['seen']} tài liệu, {stats['new']} mới, {stats['errors']} mã lỗi.")


def cmd_download(args) -> None:
    client = VietstockClient(delay_seconds=args.delay)
    with connect() as conn:
        tickers = _tickers(conn, args.tickers) if args.tickers else None
        stats = download_pending(conn, client, year=args.year, period=args.period, doc_type=args.doc_type, tickers=tickers)
    print(f"Xong: tải {stats['downloaded']} file ({stats['bytes'] / 1e6:.0f} MB), {stats['errors']} lỗi.")


def cmd_report(args) -> None:
    """Bảng độ phủ: mỗi mã có những BCTC nào cho kỳ đã chọn."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT c.ticker, c.template, d.scope, d.audit_status, d.content_kind, d.is_amended, d.file_ext,
                   d.source_listed_at, d.title_raw, d.source_url,
                   EXISTS (SELECT 1 FROM document_files f WHERE f.document_id = d.id) AS downloaded
            FROM companies c
            LEFT JOIN documents d ON d.ticker = c.ticker
                 AND d.fiscal_year = %s AND d.fiscal_period = %s AND d.doc_type = %s
            ORDER BY c.ticker, d.scope, d.source_listed_at
            """,
            (args.year, args.period, args.doc_type),
        ).fetchall()

    header = ["ticker", "template", "scope", "audit_status", "content_kind", "is_amended", "file_ext",
              "listed_at_vn", "downloaded", "title", "url"]
    table = []
    for (ticker, template, scope, audit, kind, amended, ext, listed, title, url, downloaded) in rows:
        listed_vn = listed.astimezone(VN_TZ).strftime("%Y-%m-%d %H:%M") if listed else ""
        table.append([ticker, template, scope or "-", audit or "", kind or "", "x" if amended else "", ext or "",
                      listed_vn, "x" if downloaded else "", title or "(không có)", url or ""])

    if args.csv:
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(table)
        print(f"Đã ghi {len(table)} dòng vào {args.csv}")

    missing = sorted({r[0] for r in table if r[2] == "-"})
    for r in table:
        print(f"{r[0]:<5} {r[1]:<10} {r[2]:<12} {r[3]:<8} {r[6]:<4} {r[7]:<16} {r[8]:<1}  {r[9]}")
    have = len({r[0] for r in table}) - len(missing)
    print(f"\n{have}/{have + len(missing)} mã có BCTC {args.period}/{args.year} ({args.doc_type}).")
    if missing:
        print("Chưa có: " + ", ".join(missing))


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    p = argparse.ArgumentParser(prog="python -m services.ingestion", description="Thu thập BCTC")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="Áp dụng migration CSDL").set_defaults(func=cmd_migrate)
    sub.add_parser("seed", help="Ghi danh sách công ty (VN30)").set_defaults(func=cmd_seed)

    d = sub.add_parser("discover", help="Lấy danh sách BCTC từ Vietstock")
    d.add_argument("--year", type=int, help="Năm tài chính; bỏ trống để lấy mọi năm")
    d.add_argument("--tickers", help="Danh sách mã, cách nhau bằng dấu phẩy; mặc định mọi mã trong bảng companies")
    d.add_argument("--delay", type=float, default=1.0, help="Số giây nghỉ giữa các request")
    d.set_defaults(func=cmd_discover)

    for name, func, helptext in (("download", cmd_download, "Tải file BCTC chưa tải"),
                                 ("report", cmd_report, "In bảng độ phủ BCTC theo kỳ")):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("--year", type=int, required=True)
        s.add_argument("--period", default="Q2" if name == "report" else None, help="Q1..Q4 / H1 / 9M / FY")
        s.add_argument("--doc-type", default="fs_quarter", help="fs_quarter / fs_semiannual / fs_9m / fs_annual")
        s.add_argument("--tickers")
        if name == "download":
            s.add_argument("--delay", type=float, default=1.0)
        else:
            s.add_argument("--csv", help="Ghi thêm ra file CSV")
        s.set_defaults(func=func)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
