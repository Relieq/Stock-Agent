"""Bộ canh BCTC: định kỳ lấy danh sách từ Vietstock và HOSE (services/ingestion/hose.py), tải file mới, đọc và kiểm
chứng BCTC mới, báo cho người vận hành.

    python -m services.watcher                      # chạy mãi, mỗi 15 phút một lượt
    python -m services.watcher --once               # chạy một lượt rồi dừng
    python -m services.watcher --interval 60 --year 2026

Chỉ tự động đọc BCTC **phát hiện từ đầu quý hiện tại** (--since; mùa BCTC quý trước rơi vào quý này), loại BCTC
đầy đủ, bản hợp nhất hoặc báo cáo duy nhất. Trước đây mặc định là ngày khởi động, nên máy khởi động lại giữa mùa thì
các BCTC đã phát hiện mà chưa đọc (ví dụ do hết tiền) bị bỏ qua. Dữ liệu lịch sử chạy bù bằng
`python -m services.extraction run`.

Mỗi lượt tạo kết nối mô hình mới: nhà cung cấp bị đánh dấu hỏng (quá tải, giới hạn lượt) được thử lại ở lượt sau, và
lựa chọn trên trang quản trị có hiệu lực mà không phải khởi động lại. BCTC đọc lỗi được thử lại một lần ở lượt sau.

Sau mỗi lượt bộ canh ghi thời điểm vào Data/raw/watcher_heartbeat.txt. Khi khởi động mà lượt trước đã cách quá hai lượt
thì gửi thư cho quản trị: tối 18/10/2026 Docker dừng, bộ canh nằm im gần một ngày mà không ai biết.
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from datetime import date, datetime, timedelta, timezone

from services.db import connect
from services.extraction.pipeline import extract_document
from services.extraction.second_read import after_extraction
from services.ingestion.hose import HoseClient
from services.ingestion.registry import discover, discover_hose, download_pending, raw_data_dir
from services.ingestion.vietstock import VietstockClient
from services.llm import VisionClient
from services.alerts import notify_watchers
from services.notify import notify_admin
from services.ondemand import process_queue

VN_TZ = timezone(timedelta(hours=7))


def _out_of_credit(e: Exception) -> bool:
    """Tài khoản mô hình hết tiền: lỗi của cả lượt, không phải của tài liệu."""
    return "insufficient_quota" in str(e) or "credit_balance_exhausted" in str(e)


def _quarter_start(today: date) -> date:
    return date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)


_retried: set[int] = set()      # BCTC lỗi đã thử lại trong tiến trình này (mỗi BCTC thử lại một lần)


def _heartbeat_path():
    return raw_data_dir() / "watcher_heartbeat.txt"


def _last_heartbeat() -> datetime | None:
    try:
        return datetime.fromisoformat(_heartbeat_path().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _beat() -> None:
    try:
        _heartbeat_path().write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    except OSError:
        pass


STUCK_HOURS = 6


def _stuck_path():
    return raw_data_dir() / "stuck_downloads_alerted.txt"


def stuck_downloads(conn, now: datetime, hours: int = STUCK_HOURS) -> list[tuple]:
    """BCTC đầy đủ (hợp nhất hoặc báo cáo duy nhất) của mã đang theo dõi mà nguồn đã đăng quá `hours` giờ vẫn chưa tải
    được file (TCX quý 3/2026: Vietstock đăng tiêu đề nhưng link file trả 404). Bỏ bản trùng: TCB quý 3/2026 đã đọc từ
    file HOSE, bản Vietstock đánh dấu trùng không có file vẫn bị báo nhầm."""
    return conn.execute(
        """SELECT d.id, d.ticker, d.title_raw, d.source_listed_at, d.source_url FROM documents d
           WHERE d.content_kind = 'full' AND d.doc_type LIKE 'fs_%%' AND d.scope IN ('consolidated', 'standalone')
             AND d.owner_user_id IS NULL AND d.duplicate_of IS NULL AND d.source_listed_at < %s
             AND d.source_listed_at > %s - interval '30 days'
             AND NOT EXISTS (SELECT 1 FROM document_files f WHERE f.document_id = d.id)
             AND EXISTS (SELECT 1 FROM companies c WHERE c.ticker = d.ticker AND c.tracked)
           ORDER BY d.source_listed_at""", (now - timedelta(hours=hours), now)).fetchall()


def stuck_notice(rows: list[tuple], already: set[int], now: datetime) -> tuple[str | None, list[int]]:
    """Thư báo quản trị cho các BCTC chưa tải được file mà chưa từng báo; mỗi BCTC chỉ báo một lần."""
    new = [r for r in rows if r[0] not in already]
    if not new:
        return None, []
    lines = [f"{t}: {title} - nguồn đăng lúc {listed.astimezone(VN_TZ):%H:%M %d/%m}, đã "
             f"{int((now - listed).total_seconds() // 3600)} giờ mà chưa tải được file ({url})"
             for _, t, title, listed, url in new]
    body = ("Các BCTC sau đã được đăng tiêu đề nhưng bộ canh vẫn chưa tải được file (link lỗi hoặc nguồn chưa đưa file "
            "lên). Bộ canh vẫn tự thử lại mỗi lượt; nếu kéo dài, có thể tải file từ trang công ty rồi đưa vào bằng trang "
            "Yêu cầu.\n\n" + "\n".join(lines))
    return body, [r[0] for r in new]


def _check_stuck(conn) -> None:
    now = datetime.now(timezone.utc)
    try:
        already = {int(x) for x in _stuck_path().read_text(encoding="utf-8").split()}
    except (OSError, ValueError):
        already = set()
    body, ids = stuck_notice(stuck_downloads(conn, now), already, now)
    if body:
        print(body)
        notify_admin(f"[Soi] {len(ids)} BCTC đã đăng quá {STUCK_HOURS} giờ mà chưa tải được file", body)
        try:
            _stuck_path().write_text(" ".join(str(i) for i in sorted(already | set(ids))), encoding="utf-8")
        except OSError:
            pass


def downtime_notice(last: datetime | None, now: datetime, interval_min: int) -> str | None:
    """Nội dung thư báo bộ canh vừa chạy lại sau một thời gian dừng; None nếu không cần báo. Khoảng lặng chỉ hơn một
    lượt (khởi động lại sau khi sửa code) thì không báo."""
    if last is None or now - last <= timedelta(minutes=2 * interval_min + 5):
        return None
    minutes = int((now - last).total_seconds() // 60)
    return (f"Bộ canh chạy lại lúc {now.astimezone(VN_TZ):%H:%M %d/%m}; lượt trước kết thúc lúc "
            f"{last.astimezone(VN_TZ):%H:%M %d/%m}, tức đã dừng khoảng {minutes // 60} giờ {minutes % 60} phút "
            "(máy tắt, ngủ hoặc Docker dừng). BCTC đăng trong thời gian này được đọc ngay ở lượt đầu; thời gian xử lý "
            "của chúng sẽ dài hơn bình thường.")


def _pending_extraction(conn, since: date, year: int) -> list[tuple]:
    rows = conn.execute(
        """
        SELECT d.id, d.ticker, d.title_raw, LEAST(d.source_listed_at, d.published_at), d.discovered_at, d.status
        FROM documents d
        WHERE d.status IN ('downloaded', 'failed') AND d.content_kind = 'full' AND d.scope IN ('consolidated', 'standalone')
          AND d.discovered_at >= %s AND d.fiscal_year >= %s AND d.owner_user_id IS NULL
          AND EXISTS (SELECT 1 FROM companies c WHERE c.ticker = d.ticker AND c.tracked)
        ORDER BY d.discovered_at
        """,
        (datetime.combine(since, datetime.min.time(), VN_TZ), year),
    ).fetchall()
    out = [r[:5] for r in rows if r[5] == "downloaded" or r[0] not in _retried]
    _retried.update(r[0] for r in rows if r[5] == "failed")
    return out


def one_pass(year: int, since: date, vision: VisionClient | None) -> None:
    vs = VietstockClient()
    started = datetime.now(timezone.utc)
    with connect() as conn:
        tickers = [r[0] for r in conn.execute("SELECT ticker FROM companies WHERE tracked ORDER BY ticker")]
        stats = discover(conn, vs, tickers, year)
        conn.commit()
        # Nguồn thứ hai: HOSE (giờ công bố chính thức; BCTC HOSE đăng trước Vietstock thì đọc ngay)
        hose_tickers = [r[0] for r in conn.execute(
            "SELECT ticker FROM companies WHERE tracked AND exchange = 'HOSE' ORDER BY ticker")]
        hstats = discover_hose(conn, HoseClient(ids_path=raw_data_dir() / "hose_ids.json"), hose_tickers, year)
        conn.commit()
        # Công văn giải trình kết quả kinh doanh: chỉ tải về (cùng lượt tải bên dưới) và báo, chưa đọc nội dung
        new_explanations = [f"{t}: {title.strip()} (công văn giải trình, đã lưu)" for t, title in conn.execute(
            "SELECT ticker, title_raw FROM documents WHERE doc_type = 'explanation' AND discovered_at >= %s"
            " ORDER BY ticker", (started,))]
        # Luôn thử tải các tài liệu chưa có file (kể cả lượt trước tải lỗi); chỉ là một truy vấn nếu không có gì
        for period in ("Q1", "Q2", "Q3", "Q4", "H1", "9M", "FY"):
            download_pending(conn, vs, year=year, period=period, doc_type=None, tickers=None)
        conn.commit()
        _check_stuck(conn)
        # Chỉ tự đọc BCTC của năm đang canh; dữ liệu năm trước chạy bù bằng services.extraction run
        pending = _pending_extraction(conn, since, year)
        lines = []
        for doc_id, ticker, title, listed_at, discovered_at in pending:
            if vision is None:
                lines.append(f"{ticker}: {title} (chưa đọc vì chưa cấu hình mô hình)")
                continue
            try:
                rec = extract_document(conn, doc_id, vision)
            except Exception as e:  # một tài liệu lỗi không dừng bộ canh
                conn.rollback()
                if _out_of_credit(e):
                    # Giữ trạng thái 'downloaded' để lượt sau đọc lại khi đã nạp tiền
                    lines.append(f"Tài khoản mô hình đã hết tiền: dừng đọc, còn {len(pending)} BCTC chờ. Nạp tiền rồi bộ canh tự đọc tiếp.")
                    break
                conn.execute("UPDATE documents SET status = 'failed' WHERE id = %s", (doc_id,))
                conn.commit()
                lines.append(f"{ticker}: {title} -> LỖI {e}")
                continue
            conn.commit()
            s = rec["summary"]
            lag = datetime.now(timezone.utc) - listed_at if listed_at else None
            sent = notify_watchers(conn, doc_id)
            conn.commit()
            # Sau khi đã báo người theo dõi: ô không phép kiểm nào phủ được nhà cung cấp còn lại đọc lần hai
            second = after_extraction(conn, doc_id, vision)
            lines.append(
                f"{ticker}: {title} -> {rec['status']} ({s['gate_checks'] - s['gate_failed']}/{s['gate_checks']} ràng buộc"
                f" bắt buộc đạt); công bố {listed_at.astimezone(VN_TZ):%d/%m %H:%M} (Vietstock hoặc HOSE, nguồn sớm hơn)"
                + (f", xử lý xong sau {lag.total_seconds() / 60:.0f} phút" if lag else "")
                + (f"; gửi {sent} email cho người theo dõi" if sent else "")
                + (f"; {second}" if second else "")
            )
        # Yêu cầu của người dùng: mã ngoài danh sách, file tải lên
        lines += process_queue(conn, vision)
        # Báo cáo của agent đang chờ đọc BCTC: chạy tiếp khi các yêu cầu đọc đã xong
        try:
            from services.analyst.report import resume_waiting
            lines += resume_waiting(conn)
        except Exception as e:      # noqa: BLE001 - lỗi chạy tiếp báo cáo không làm hỏng lượt canh
            lines.append(f"LỖI chạy tiếp báo cáo: {e}")
        conn.commit()
        lines += new_explanations
    stamp = datetime.now(VN_TZ).strftime("%d/%m %H:%M")
    print(f"[{stamp}] {stats['seen']} tài liệu trong danh sách, {stats['new']} mới (HOSE: {hstats['seen']} BCTC, "
          f"{hstats['new']} mới, {hstats['letters_new']} công văn mới, {hstats['attached']} lấy file thay Vietstock), {len(pending)} BCTC mới đã xử lý")
    if lines:
        body = "\n".join(lines)
        print(body)
        n_review = sum("needs_review" in l or "LỖI" in l for l in lines)
        n_docs = len(lines) - len(new_explanations)
        parts = ([f"{n_docs} BCTC mới" + (f", {n_review} cần duyệt" if n_review else "")] if n_docs else []) + (
            [f"{len(new_explanations)} công văn giải trình"] if new_explanations else [])
        notify_admin("[Soi] " + ", ".join(parts), body)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="python -m services.watcher", description="Bộ canh BCTC")
    p.add_argument("--year", type=int, default=date.today().year)
    p.add_argument("--interval", type=int, default=15, help="Số phút giữa hai lượt")
    p.add_argument("--since", type=date.fromisoformat, default=_quarter_start(date.today()),
                   help="Chỉ tự đọc BCTC phát hiện từ ngày này (YYYY-MM-DD), mặc định đầu quý hiện tại")
    p.add_argument("--once", action="store_true")
    args = p.parse_args()

    notice = downtime_notice(_last_heartbeat(), datetime.now(timezone.utc), args.interval)
    if notice:
        print(notice)
        notify_admin("[Soi] Bộ canh vừa chạy lại sau khi dừng", notice)
    while True:
        try:
            vision = VisionClient()
        except RuntimeError as e:
            print(f"Chưa cấu hình mô hình đọc ảnh ({e}); bộ canh chỉ thu thập, không đọc BCTC.")
            vision = None
        try:
            one_pass(args.year, args.since, vision)
        except Exception:  # lỗi mạng, CSDL... thì báo và chờ lượt sau
            err = traceback.format_exc()
            print(err)
            notify_admin("[Soi] Bộ canh gặp lỗi", err)
        _beat()
        if args.once:
            break
        time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()
