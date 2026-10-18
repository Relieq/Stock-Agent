"""Đọc BCTC ngoài danh sách theo dõi khi người dùng yêu cầu, và file người dùng tải lên (kế hoạch MVP mục 2.6).

Một kho chung: BCTC đã đọc thì ai hỏi sau cũng dùng lại, không tốn thêm. File tải lên được nhận diện bằng mã băm
SHA-256 (dấu vân tay của file: cùng nội dung thì cùng mã); trùng file đã có thì trả kết quả ngay. Chưa có thì ưu tiên
bản chính thức trên Vietstock; không tìm được bản chính thức mới đọc file tải lên, và chỉ người tải lên xem được.

Giới hạn chi phí: mỗi người `users.daily_quota` yêu cầu mới mỗi ngày (yêu cầu trả ngay từ kho không tính); tổng chi
phí đọc BCTC theo yêu cầu người dùng trong tháng không vượt `LLM_MONTHLY_BUDGET_USD` (mặc định 5), vượt thì yêu cầu
nằm chờ tháng sau. Đọc theo lịch cho các mã đang theo dõi không tính vào trần này.
Bộ canh xử lý hàng chờ mỗi lượt (services/watcher).
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import psycopg
import requests

from services.alerts import notify_watchers  # noqa: F401  (dùng ở bộ canh)
from services.extraction import prompts
from services.extraction.bank import fold
from services.extraction.pipeline import LOCATE_LONG_SIDE, extract_document
from services.extraction.second_read import after_extraction
from services.extraction.sources import candidates, open_pdf, render_page
from services.ingestion.registry import discover, download_pending, raw_data_dir
from services.ingestion.vietstock import BASE_URL, VietstockClient
from services.llm import VisionClient
from services.metrics.service import quarter_document
from services.notify import send_email
from services.users import User, site_url

TICKER_RE = re.compile(r"^[A-Z0-9]{3}$")
UPLOAD_EXTS = {".pdf", ".zip"}
MAX_UPLOAD_BYTES = 60 * 1024 * 1024


UPLOAD_DAILY = 1                    # file tải lên mỗi người mỗi ngày (cần mô hình đọc trang đầu để nhận diện)


def monthly_budget() -> float:
    return float(os.environ.get("LLM_MONTHLY_BUDGET_USD") or 5)


def month_spend(conn: psycopg.Connection) -> float:
    """Chi phí tính vào trần tháng: các BCTC đọc theo yêu cầu người dùng trong tháng (services/costs.py)."""
    from services.costs import requested_spend
    return requested_spend(conn)


def used_today(conn: psycopg.Connection, user_id: int, kind: str | None = None) -> int:
    return conn.execute(
        """SELECT count(*) FROM processing_requests WHERE user_id = %s AND created_at > now() - interval '1 day'
           AND status IN ('queued', 'processing', 'done') AND note IS DISTINCT FROM 'có sẵn trong kho'
           AND (%s::text IS NULL OR kind = %s)""",
        (user_id, kind, kind)).fetchone()[0]


def _ready_document(conn, ticker: str, year: int, period: str) -> int | None:
    doc_id = quarter_document(conn, ticker, year, period)
    if doc_id is None:
        return None
    done = conn.execute("SELECT processed_at IS NOT NULL AND owner_user_id IS NULL FROM documents WHERE id = %s",
                        (doc_id,)).fetchone()[0]
    return doc_id if done else None


def request_ticker(conn: psycopg.Connection, user: User, ticker: str, year: int, period: str) -> tuple[int, str]:
    """Tạo yêu cầu đọc BCTC quý của một mã. Trả về (id yêu cầu, trạng thái)."""
    ticker = ticker.strip().upper()
    if not TICKER_RE.match(ticker) or period not in ("Q1", "Q2", "Q3", "Q4"):
        raise ValueError("Mã chứng khoán gồm 3 ký tự, kỳ là Q1..Q4")
    if (doc_id := _ready_document(conn, ticker, year, period)) is not None:
        rid = conn.execute(
            """INSERT INTO processing_requests (user_id, kind, ticker, fiscal_year, fiscal_period, document_id, status,
                                               note, finished_at)
               VALUES (%s, 'ticker', %s, %s, %s, %s, 'done', 'có sẵn trong kho', now()) RETURNING id""",
            (user.id, ticker, year, period, doc_id)).fetchone()[0]
        return rid, "done"
    if used_today(conn, user.id) >= user.daily_quota:
        raise PermissionError(f"Đã dùng hết {user.daily_quota} yêu cầu mới trong 24 giờ qua")
    rid = conn.execute(
        """INSERT INTO processing_requests (user_id, kind, ticker, fiscal_year, fiscal_period)
           VALUES (%s, 'ticker', %s, %s, %s) RETURNING id""", (user.id, ticker, year, period)).fetchone()[0]
    return rid, "queued"


def request_upload(conn: psycopg.Connection, user: User, filename: str, data: bytes, ticker: str, year: int,
                   period: str) -> tuple[int, str]:
    """Lưu file tải lên và tạo yêu cầu. File trùng mã băm với file đã đọc thì trả kết quả ngay."""
    ticker = ticker.strip().upper()
    ext = Path(filename).suffix.lower()
    if ext not in UPLOAD_EXTS:
        raise ValueError("Chỉ nhận file PDF hoặc ZIP")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("File quá lớn (tối đa 60 MB)")
    if not TICKER_RE.match(ticker) or period not in ("Q1", "Q2", "Q3", "Q4"):
        raise ValueError("Mã chứng khoán gồm 3 ký tự, kỳ là Q1..Q4")
    sha = hashlib.sha256(data).hexdigest()
    known = conn.execute(
        """SELECT d.id FROM document_files f JOIN documents d ON d.id = f.document_id
           WHERE f.sha256 = %s AND d.processed_at IS NOT NULL AND (d.owner_user_id IS NULL OR d.owner_user_id = %s)
           ORDER BY d.owner_user_id NULLS FIRST LIMIT 1""", (sha, user.id)).fetchone()
    if known:
        rid = conn.execute(
            """INSERT INTO processing_requests (user_id, kind, ticker, fiscal_year, fiscal_period, upload_sha256,
                                               document_id, status, note, finished_at)
               VALUES (%s, 'upload', %s, %s, %s, %s, %s, 'done', 'có sẵn trong kho', now()) RETURNING id""",
            (user.id, ticker, year, period, sha, known[0])).fetchone()[0]
        return rid, "done"
    if used_today(conn, user.id) >= user.daily_quota:
        raise PermissionError(f"Đã dùng hết {user.daily_quota} yêu cầu mới trong 24 giờ qua")
    if used_today(conn, user.id, "upload") >= UPLOAD_DAILY:
        raise PermissionError(f"Mỗi ngày chỉ tải lên được {UPLOAD_DAILY} file BCTC chưa có trong kho")
    rel = Path("uploads") / f"{sha}{ext}"
    dest = raw_data_dir() / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_bytes(data)
    rid = conn.execute(
        """INSERT INTO processing_requests (user_id, kind, ticker, fiscal_year, fiscal_period, upload_sha256, upload_key)
           VALUES (%s, 'upload', %s, %s, %s, %s, %s) RETURNING id""",
        (user.id, ticker, year, period, sha, rel.as_posix())).fetchone()[0]
    return rid, "queued"


# ---- xử lý hàng chờ (bộ canh gọi) ---------------------------------------------------------------------------------

def company_from_vietstock(ticker: str) -> tuple[str, str] | None:
    html = requests.get(f"{BASE_URL}/{ticker}/tai-tai-lieu.htm?doctype=1", headers={"User-Agent": "Mozilla/5.0"},
                        timeout=30).text
    return parse_company_title(ticker, html)


def parse_company_title(ticker: str, html: str) -> tuple[str, str] | None:
    """(tên công ty, mẫu BCTC đoán theo tên) từ tiêu đề trang tài liệu của mã trên Vietstock, dạng
    "HUT: CTCP Tasco - Tasco - CTCP - Tải tài liệu | VietstockFinance"."""
    m = re.search(rf"<title>\s*{ticker}:\s*(.+?)\s+-\s", html)
    if not m:
        return None
    name = m.group(1).strip()
    low = name.lower()
    template = ("bank" if "ngân hàng" in low else "securities" if "chứng khoán" in low
                else "insurance" if "bảo hiểm" in low else "corporate")
    return name, template


def _ensure_company(conn, ticker: str) -> bool:
    if conn.execute("SELECT 1 FROM companies WHERE ticker = %s", (ticker,)).fetchone():
        return True
    info = company_from_vietstock(ticker)
    if info is None:
        return False
    conn.execute("INSERT INTO companies (ticker, name, template, tracked) VALUES (%s, %s, %s, false)",
                 (ticker, *info))
    return True


def _finish(conn, rid: int, status: str, note: str, document_id: int | None = None) -> None:
    conn.execute("UPDATE processing_requests SET status = %s, note = %s, document_id = COALESCE(%s, document_id),"
                 " finished_at = now() WHERE id = %s", (status, note, document_id, rid))
    user_email, ticker, year, period = conn.execute(
        """SELECT u.email, r.ticker, r.fiscal_year, r.fiscal_period FROM processing_requests r
           JOIN users u ON u.id = r.user_id WHERE r.id = %s""", (rid,)).fetchone()
    link = f"{site_url()}/yeu-cau"
    send_email(user_email, f"[Soi] Yêu cầu {ticker} {period}/{year}: {'xong' if status == 'done' else 'không thực hiện được'}",
               f"{note}\n\nXem: {link}")


_NAME_NOISE = re.compile(r"\b(cong ty|tong cong ty|tap doan|co phan|ctcp|tnhh|jsc|corporation|group|viet nam|vn)\b")


def _name_tokens(name: str) -> set[str]:
    return set(_NAME_NOISE.sub(" ", fold(name or "").lower()).split())


def names_match(printed: str | None, registered: str) -> bool:
    """Tên in trên file có phải tên công ty đã đăng ký không: bỏ dấu, bỏ các từ chung (công ty, cổ phần...), rồi
    phần lớn từ còn lại của tên đăng ký phải có trong tên in."""
    a, b = _name_tokens(printed or ""), _name_tokens(registered)
    return bool(b) and len(a & b) >= max(1, round(len(b) * 0.6))


def identify_upload(path: Path, vision: VisionClient) -> dict:
    """Đọc 2 trang đầu (ảnh nhỏ) để biết file là BCTC của công ty nào, kỳ nào. Khoảng 0,002 USD một file."""
    doc = open_pdf(candidates(path)[0])
    images = [(f"Trang {p}", render_page(doc, p, LOCATE_LONG_SIDE)) for p in range(1, min(doc.page_count, 2) + 1)]
    return vision.json_from_images(prompts.IDENTIFY_PROMPT, images, prompts.IDENTIFY_SCHEMA, "identify_upload")


def check_upload(found: dict, ticker: str, company_name: str, year: int, period: str) -> str | None:
    """Lý do từ chối nếu file không khớp với mã và kỳ người dùng khai; None nếu khớp."""
    if not found.get("is_financial_statement"):
        return "File không phải báo cáo tài chính"
    printed_ticker = (found.get("ticker") or "").strip().upper()
    if printed_ticker and printed_ticker != ticker:
        return f"File in mã {printed_ticker}, không phải {ticker}"
    if not printed_ticker and not names_match(found.get("company_name"), company_name):
        return f"File là BCTC của \"{found.get('company_name')}\", không khớp {ticker} ({company_name})"
    if found.get("fiscal_year") != year or found.get("period") != period:
        return f"File là BCTC kỳ {found.get('period')}/{found.get('fiscal_year')}, không phải {period}/{year}"
    return None


def _official_document(conn, vs: VietstockClient, ticker: str, year: int, period: str) -> int | None:
    discover(conn, vs, [ticker], year)
    download_pending(conn, vs, year=year, period=period, doc_type="fs_quarter", tickers=[ticker])
    return quarter_document(conn, ticker, year, period)


def _private_document(conn, rid: int, user_id: int, ticker: str, year: int, period: str, sha: str, key: str,
                      size: int) -> int:
    doc_id = conn.execute(
        """INSERT INTO documents (ticker, source, source_doc_id, source_url, title_raw, file_ext, content_kind,
                                  doc_type, fiscal_year, fiscal_period, scope, status, owner_user_id)
           VALUES (%s, 'upload', %s, %s, %s, %s, 'full', 'fs_quarter', %s, %s, 'consolidated', 'downloaded', %s)
           ON CONFLICT (source, source_doc_id) DO UPDATE SET last_seen_at = now() RETURNING id""",
        (ticker, f"{user_id}:{sha}", f"upload:{sha}", f"Tệp tải lên: BCTC {period}/{year} {ticker}",
         Path(key).suffix.lstrip("."), year, period, user_id)).fetchone()[0]
    conn.execute("""INSERT INTO document_files (document_id, sha256, size_bytes, storage_key, source_url)
                    VALUES (%s, %s, %s, %s, %s) ON CONFLICT (document_id, sha256) DO NOTHING""",
                 (doc_id, sha, size, key, f"upload:{sha}"))
    return doc_id


def process_queue(conn: psycopg.Connection, vision: VisionClient | None, limit: int = 5) -> list[str]:
    """Xử lý các yêu cầu đang chờ, cũ trước. Trả về các dòng tóm tắt cho người vận hành."""
    lines: list[str] = []
    if vision is None:
        return lines
    queued = conn.execute(
        """SELECT id, user_id, kind, ticker, fiscal_year, fiscal_period, upload_sha256, upload_key
           FROM processing_requests WHERE status = 'queued' ORDER BY created_at LIMIT %s""", (limit,)).fetchall()
    if queued and month_spend(conn) >= monthly_budget():
        return [f"{len(queued)} yêu cầu đang chờ: đã chạm trần chi phí tháng {monthly_budget():.0f} USD"]
    vs = VietstockClient()
    for rid, user_id, kind, ticker, year, period, sha, key in queued:
        conn.execute("UPDATE processing_requests SET status = 'processing' WHERE id = %s", (rid,))
        conn.commit()
        try:
            if not _ensure_company(conn, ticker):
                _finish(conn, rid, "rejected", f"Không tìm thấy mã {ticker} trên Vietstock")
                lines.append(f"yêu cầu {rid}: không có mã {ticker}")
                continue
            if kind == "upload":
                found = identify_upload(raw_data_dir() / key, vision)
                name = conn.execute("SELECT name FROM companies WHERE ticker = %s", (ticker,)).fetchone()[0]
                if (reason := check_upload(found, ticker, name, year, period)) is not None:
                    _finish(conn, rid, "rejected", reason + ". Kiểm tra lại mã và kỳ rồi tải lên lại.")
                    lines.append(f"yêu cầu {rid}: từ chối file tải lên: {reason}")
                    continue
            doc_id = _official_document(conn, vs, ticker, year, period)
            note = ""
            if doc_id is None and kind == "upload":
                size = (raw_data_dir() / key).stat().st_size
                doc_id = _private_document(conn, rid, user_id, ticker, year, period, sha, key, size)
                note = "Không tìm thấy bản chính thức trên Vietstock: đã đọc file bạn tải lên, chỉ bạn xem được. "
            elif kind == "upload":
                note = "Đã dùng bản chính thức trên Vietstock thay cho file tải lên. "
            if doc_id is None:
                _finish(conn, rid, "failed", f"Vietstock chưa có BCTC {period}/{year} của {ticker}")
                lines.append(f"yêu cầu {rid}: chưa có BCTC {ticker} {period}/{year}")
                continue
            processed = conn.execute("SELECT processed_at IS NOT NULL FROM documents WHERE id = %s", (doc_id,)).fetchone()[0]
            if not processed:
                rec = extract_document(conn, doc_id, vision)
                conn.commit()
                after_extraction(conn, doc_id, vision)
                note += f"Kết quả đọc: {'đã kiểm chứng' if rec['status'] == 'verified' else 'cần duyệt tay trước khi xuất bản'}."
            else:
                note += "Có sẵn trong kho."
            _finish(conn, rid, "done", note, doc_id)
            lines.append(f"yêu cầu {rid}: {ticker} {period}/{year} -> {note}")
        except Exception as e:  # một yêu cầu lỗi không dừng hàng chờ
            conn.rollback()
            if "insufficient_quota" in str(e) or "credit_balance_exhausted" in str(e):
                conn.execute("UPDATE processing_requests SET status = 'queued' WHERE id = %s", (rid,))
                conn.commit()
                lines.append("Tài khoản mô hình đã hết tiền: các yêu cầu nằm chờ tới khi nạp tiền")
                break
            _finish(conn, rid, "failed", f"Lỗi khi xử lý: {e}")
            lines.append(f"yêu cầu {rid}: LỖI {e}")
        conn.commit()
    return lines
