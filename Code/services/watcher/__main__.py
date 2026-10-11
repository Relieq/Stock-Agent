"""Bộ canh BCTC: định kỳ lấy danh sách từ Vietstock, tải file mới, đọc và kiểm chứng BCTC mới, báo cho người vận hành.

    python -m services.watcher                      # chạy mãi, mỗi 15 phút một lượt
    python -m services.watcher --once               # chạy một lượt rồi dừng
    python -m services.watcher --interval 60 --year 2026

Chỉ tự động đọc BCTC **phát hiện từ lúc bộ canh bắt đầu chạy** (--since, mặc định hôm nay), loại BCTC đầy đủ,
bản hợp nhất hoặc báo cáo duy nhất. Dữ liệu lịch sử chạy bù bằng `python -m services.extraction run`.
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from datetime import date, datetime, timedelta, timezone

from services.db import connect
from services.extraction.pipeline import extract_document
from services.ingestion.registry import discover, download_pending
from services.ingestion.vietstock import VietstockClient
from services.llm import VisionClient
from services.notify import notify_admin

VN_TZ = timezone(timedelta(hours=7))


def _pending_extraction(conn, since: date) -> list[tuple]:
    return conn.execute(
        """
        SELECT d.id, d.ticker, d.title_raw, d.source_listed_at, d.discovered_at
        FROM documents d
        WHERE d.status = 'downloaded' AND d.content_kind = 'full' AND d.scope IN ('consolidated', 'standalone')
          AND d.discovered_at >= %s
        ORDER BY d.discovered_at
        """,
        (datetime.combine(since, datetime.min.time(), VN_TZ),),
    ).fetchall()


def one_pass(year: int, since: date, vision: VisionClient | None) -> None:
    vs = VietstockClient()
    with connect() as conn:
        tickers = [r[0] for r in conn.execute("SELECT ticker FROM companies ORDER BY ticker")]
        stats = discover(conn, vs, tickers, year)
        conn.commit()
        # Luôn thử tải các tài liệu chưa có file (kể cả lượt trước tải lỗi); chỉ là một truy vấn nếu không có gì
        for period in ("Q1", "Q2", "Q3", "Q4", "H1", "9M", "FY"):
            download_pending(conn, vs, year=year, period=period, doc_type=None, tickers=None)
        conn.commit()
        pending = _pending_extraction(conn, since)
        lines = []
        for doc_id, ticker, title, listed_at, discovered_at in pending:
            if vision is None:
                lines.append(f"{ticker}: {title} (chưa đọc vì chưa cấu hình mô hình)")
                continue
            try:
                rec = extract_document(conn, doc_id, vision)
            except Exception as e:  # một tài liệu lỗi không dừng bộ canh
                conn.execute("UPDATE documents SET status = 'failed' WHERE id = %s", (doc_id,))
                conn.commit()
                lines.append(f"{ticker}: {title} -> LỖI {e}")
                continue
            conn.commit()
            s = rec["summary"]
            lag = datetime.now(timezone.utc) - listed_at if listed_at else None
            lines.append(
                f"{ticker}: {title} -> {rec['status']} ({s['gate_checks'] - s['gate_failed']}/{s['gate_checks']} ràng buộc"
                f" bắt buộc đạt); Vietstock đăng {listed_at.astimezone(VN_TZ):%d/%m %H:%M}"
                + (f", xử lý xong sau {lag.total_seconds() / 60:.0f} phút" if lag else "")
            )
    stamp = datetime.now(VN_TZ).strftime("%d/%m %H:%M")
    print(f"[{stamp}] {stats['seen']} tài liệu trong danh sách, {stats['new']} mới, {len(pending)} BCTC mới đã xử lý")
    if lines:
        body = "\n".join(lines)
        print(body)
        n_review = sum("needs_review" in l or "LỖI" in l for l in lines)
        notify_admin(f"[Soi] {len(lines)} BCTC mới" + (f", {n_review} cần duyệt" if n_review else ""), body)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="python -m services.watcher", description="Bộ canh BCTC")
    p.add_argument("--year", type=int, default=date.today().year)
    p.add_argument("--interval", type=int, default=15, help="Số phút giữa hai lượt")
    p.add_argument("--since", type=date.fromisoformat, default=date.today(),
                   help="Chỉ tự đọc BCTC phát hiện từ ngày này (YYYY-MM-DD)")
    p.add_argument("--once", action="store_true")
    args = p.parse_args()

    try:
        vision = VisionClient()
    except RuntimeError as e:
        print(f"Chưa cấu hình mô hình đọc ảnh ({e}); bộ canh chỉ thu thập, không đọc BCTC.")
        vision = None

    while True:
        try:
            one_pass(args.year, args.since, vision)
        except Exception:  # lỗi mạng, CSDL... thì báo và chờ lượt sau
            err = traceback.format_exc()
            print(err)
            notify_admin("[Soi] Bộ canh gặp lỗi", err)
        if args.once:
            break
        time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()
