"""Ghi tài liệu và file tải về vào CSDL (Document Registry)."""

from __future__ import annotations

import csv
import hashlib
import os
import re
import tempfile
import time
from pathlib import Path

import psycopg

from services.db import CODE_DIR
from services.ingestion.hose import HoseClient
from services.ingestion.titles import parse_title
from services.ingestion.vietstock import SourceDocument, VietstockClient

SEEDS_DIR = CODE_DIR / "db" / "seeds"
MAX_FAILS_IN_ROW = 3     # số mã liền nhau lấy danh sách lỗi thì bỏ phần còn lại của lượt quét Vietstock


def raw_data_dir() -> Path:
    return (CODE_DIR / os.environ.get("RAW_DATA_DIR", "../Data/raw")).resolve()


def seed_companies(conn: psycopg.Connection, csv_path: Path | None = None) -> int:
    csv_path = csv_path or SEEDS_DIR / "companies_vn30.csv"
    with open(csv_path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    with conn.transaction():
        for r in rows:
            conn.execute(
                "INSERT INTO companies (ticker, name, exchange, template) VALUES (%s, %s, %s, %s)"
                " ON CONFLICT (ticker) DO UPDATE SET name = EXCLUDED.name, exchange = EXCLUDED.exchange,"
                " template = EXCLUDED.template",
                (r["ticker"], r["name"], r["exchange"], r["template"]),
            )
    return len(rows)


def upsert_document(conn: psycopg.Connection, doc: SourceDocument, source: str = "vietstock") -> bool:
    """Thêm hoặc cập nhật một tài liệu. Trả về True nếu là tài liệu mới."""
    info = parse_title(doc.title)
    row = conn.execute(
        """
        INSERT INTO documents (
            ticker, source, source_doc_id, source_url, title_raw, file_ext,
            content_kind, doc_type, fiscal_year, fiscal_period, scope, audit_status, is_amended,
            source_listed_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source, source_doc_id) DO UPDATE SET
            source_url = EXCLUDED.source_url,
            title_raw = EXCLUDED.title_raw,
            file_ext = EXCLUDED.file_ext,
            content_kind = EXCLUDED.content_kind,
            doc_type = EXCLUDED.doc_type,
            fiscal_year = EXCLUDED.fiscal_year,
            fiscal_period = EXCLUDED.fiscal_period,
            scope = EXCLUDED.scope,
            audit_status = EXCLUDED.audit_status,
            is_amended = EXCLUDED.is_amended,
            source_listed_at = EXCLUDED.source_listed_at,
            last_seen_at = now()
        RETURNING (xmax = 0) AS inserted, id
        """,
        (
            doc.ticker, source, doc.source_doc_id, doc.url, doc.title, doc.file_ext,
            info.content_kind, info.doc_type, info.fiscal_year, info.fiscal_period, info.scope,
            info.audit_status, info.is_amended, doc.listed_at,
        ),
    ).fetchone()
    if row[0] and info.content_kind == "full" and not info.is_amended and info.fiscal_period and info.scope:
        # Cùng BCTC đã có từ nguồn khác (HOSE đăng trước): không đọc lại lần nữa
        other = equivalent_document(conn, doc.ticker, info.fiscal_year, info.fiscal_period, info.doc_type, [info.scope],
                                    exclude_id=row[1], other_than_source=source)
        if other is not None:
            conn.execute("UPDATE documents SET status = 'duplicate', duplicate_of = %s WHERE id = %s", (other[0], row[1]))
    return bool(row[0])


def equivalent_document(conn: psycopg.Connection, ticker: str, year: int, period: str, doc_type: str, scopes: list[str],
                        exclude_id: int | None = None, other_than_source: str | None = None) -> tuple | None:
    """BCTC đầy đủ, không phải bản điều chỉnh, cùng mã, kỳ, loại và phạm vi đã có trong kho:
    (id, nguồn, giờ công bố chính thức, đã có file chưa)."""
    return conn.execute(
        """SELECT d.id, d.source, d.published_at, EXISTS (SELECT 1 FROM document_files f WHERE f.document_id = d.id)
           FROM documents d
           WHERE d.ticker = %s AND d.fiscal_year = %s AND d.fiscal_period = %s AND d.doc_type = %s
             AND d.content_kind = 'full' AND NOT d.is_amended AND d.duplicate_of IS NULL AND d.owner_user_id IS NULL
             AND d.scope = ANY(%s) AND d.id <> %s AND (%s::text IS NULL OR d.source <> %s)
           ORDER BY (d.scope = 'consolidated') DESC, d.id LIMIT 1""",
        (ticker, year, period, doc_type, scopes, exclude_id or 0, other_than_source, other_than_source)).fetchone()


def discover_hose(conn: psycopg.Connection, client: HoseClient, tickers: list[str], year: int) -> dict[str, int]:
    """Đối chiếu BCTC mới nhất trên HOSE với kho (services/ingestion/hose.py):
      * BCTC đã có (thường từ Vietstock): ghi giờ HOSE đăng làm giờ công bố chính thức nếu sớm hơn; nếu bản đó vẫn chưa
        tải được file (link Vietstock lỗi) thì tải file từ HOSE;
      * chưa có: thêm BCTC nguồn HOSE để đọc ngay, không chờ Vietstock. Chỉ thêm bản hợp nhất, hoặc bản duy nhất của công
        ty không có công ty con; tên tệp không ghi hợp nhất/riêng mà công ty có cả hai loại thì chờ Vietstock.
    BCTC riêng và bản điều chỉnh không thêm (Vietstock vẫn lấy như trước)."""
    stats = {"seen": 0, "new": 0, "published": 0, "attached": 0, "errors": 0}
    for ticker in tickers:
        try:
            items = client.list_statements(ticker)
        except Exception as e:  # một mã lỗi không làm dừng cả lượt
            print(f"  HOSE {ticker}: lỗi khi lấy danh sách: {e}")
            stats["errors"] += 1
            continue
        has_both = conn.execute(
            "SELECT coalesce(bool_or(scope = 'consolidated'), false) FROM documents"
            " WHERE ticker = %s AND content_kind = 'full'", (ticker,)).fetchone()[0]
        for st in items:
            if st.fiscal_year < year or st.is_amended or st.scope == "separate":
                continue
            stats["seen"] += 1
            scopes = [st.scope] if st.scope else ["standalone", "consolidated"]
            row = equivalent_document(conn, ticker, st.fiscal_year, st.fiscal_period, st.doc_type, scopes)
            if row is not None:
                doc_id, source, published, has_file = row
                if published is None or published > st.posted_at:
                    conn.execute("UPDATE documents SET published_at = %s WHERE id = %s", (st.posted_at, doc_id))
                    stats["published"] += 1
                if not has_file and _fetch_file(conn, client, doc_id, ticker, st.fiscal_year, "hose", st.source_doc_id,
                                                st.url):
                    stats["attached"] += 1
                    print(f"  HOSE {ticker}: {st.title}: lấy file từ HOSE cho BCTC {doc_id} (nguồn {source} chưa tải được)")
                conn.commit()
                continue
            if st.scope is None and has_both:
                continue
            conn.execute(
                """INSERT INTO documents (ticker, source, source_doc_id, source_url, title_raw, file_ext, content_kind,
                                          doc_type, fiscal_year, fiscal_period, scope, is_amended, source_listed_at,
                                          published_at)
                   VALUES (%s, 'hose', %s, %s, %s, %s, 'full', %s, %s, %s, %s, false, %s, %s)
                   ON CONFLICT (source, source_doc_id) DO NOTHING""",
                (ticker, st.source_doc_id, st.url, st.title, st.file_ext, st.doc_type, st.fiscal_year, st.fiscal_period,
                 st.scope or "standalone", st.posted_at, st.posted_at))
            conn.commit()
            stats["new"] += 1
            print(f"  HOSE {ticker}: {st.title}: mới, HOSE đăng trước Vietstock")
    return stats


def discover(conn: psycopg.Connection, client: VietstockClient, tickers: list[str], year: int | None) -> dict[str, int]:
    """Lấy danh sách BCTC và công văn giải trình kết quả kinh doanh của từng mã từ Vietstock, ghi vào bảng
    documents (công văn giải trình: doc_type 'explanation', kỳ là kỳ BCTC được giải trình)."""
    stats = {"seen": 0, "new": 0, "errors": 0, "explanations_new": 0}
    failed_in_row = 0
    for ticker in tickers:
        if failed_in_row >= MAX_FAILS_IN_ROW:
            # Vietstock đang quá tải (20/10/2026: gần như mọi mã hết thời gian chờ 30 giây, một lượt kéo dài nửa giờ):
            # bỏ phần còn lại của lượt này để bộ canh chuyển sang HOSE, lượt sau thử lại
            print(f"  Vietstock lỗi {failed_in_row} mã liền nhau: bỏ qua các mã còn lại trong lượt này")
            stats["errors"] += 1
            break
        try:
            docs = client.list_financial_statements(ticker, year=year)
            explanations = client.list_explanations(ticker, year=year)
        except Exception as e:  # một mã lỗi không làm dừng cả lượt
            print(f"  {ticker}: lỗi khi lấy danh sách: {e}")
            stats["errors"] += 1
            failed_in_row += 1
            continue
        failed_in_row = 0
        with conn.transaction():
            new = sum(upsert_document(conn, d) for d in docs)
            new_expl = sum(upsert_document(conn, d) for d in explanations)
        stats["seen"] += len(docs)
        stats["new"] += new
        stats["explanations_new"] += new_expl
        print(f"  {ticker}: {len(docs)} tài liệu, {new} mới; {len(explanations)} công văn giải trình, {new_expl} mới")
    return stats


def _safe_filename(url: str) -> str:
    name = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    name = re.sub(r"%20| ", "_", name)
    return re.sub(r"[^\w.\-]", "_", name) or "file"


def mark_duplicate(conn: psycopg.Connection, doc_id: int, sha256: str) -> int | None:
    """Công bố mà file trùng hệt file của một công bố khác (cùng mã băm) thì trỏ về công bố có trước, trạng thái
    'duplicate', không đọc lại. Trả về id công bố gốc nếu trùng."""
    row = conn.execute(
        """SELECT d.id FROM document_files f JOIN documents d ON d.id = f.document_id
           WHERE f.sha256 = %s AND d.id <> %s AND d.duplicate_of IS NULL
           ORDER BY d.source_listed_at NULLS LAST, d.id LIMIT 1""", (sha256, doc_id)).fetchone()
    if row is None:
        return None
    conn.execute("UPDATE documents SET status = 'duplicate', duplicate_of = %s WHERE id = %s", (row[0], doc_id))
    return row[0]


def download_pending(
    conn: psycopg.Connection,
    client: VietstockClient,
    *,
    year: int,
    period: str | None,
    doc_type: str | None,
    tickers: list[str] | None,
) -> dict[str, int]:
    """Tải các tài liệu khớp điều kiện mà chưa có file nào. Lưu theo <ticker>/<năm>/<mã tài liệu>_<tên file>."""
    query = [
        "SELECT id, ticker, source_doc_id, source_url, source FROM documents",
        "WHERE fiscal_year = %s AND duplicate_of IS NULL",
        "AND NOT EXISTS (SELECT 1 FROM document_files f WHERE f.document_id = documents.id)",
    ]
    params: list[object] = [year]
    if period:
        query.append("AND fiscal_period = %s")
        params.append(period)
    if doc_type:
        query.append("AND doc_type = %s")
        params.append(doc_type)
    if tickers:
        query.append("AND ticker = ANY(%s)")
        params.append(tickers)
    query.append("ORDER BY ticker, id")
    rows = conn.execute(" ".join(query), params).fetchall()

    stats = {"downloaded": 0, "errors": 0, "bytes": 0}
    for doc_id, ticker, source_doc_id, url, source in rows:
        size = _fetch_file(conn, client, doc_id, ticker, year, source, source_doc_id, url)
        if size is None:
            stats["errors"] += 1
            continue
        stats["downloaded"] += 1
        stats["bytes"] += size
        time.sleep(client.delay_seconds)
    return stats


def _fetch_file(conn: psycopg.Connection, client, doc_id: int, ticker: str, year: int, source: str, source_doc_id: str,
                url: str) -> int | None:
    """Tải file của một tài liệu, lưu theo <nguồn>/<ticker>/<năm>/<mã tài liệu>_<tên file>, ghi vào document_files.
    Trả về số byte, None nếu lỗi."""
    rel = Path(source) / ticker / str(year) / f"{_safe_filename(source_doc_id)}_{_safe_filename(url)}"
    dest = raw_data_dir() / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as tmp:
            tmp_path = Path(tmp.name)
        client.download(url, tmp_path)
        data = tmp_path.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()
        tmp_path.replace(dest)
    except Exception as e:
        print(f"  {ticker} {source_doc_id}: lỗi khi tải: {e}")
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        return None
    with conn.transaction():
        conn.execute(
            "INSERT INTO document_files (document_id, sha256, size_bytes, storage_key, source_url)"
            " VALUES (%s, %s, %s, %s, %s) ON CONFLICT (document_id, sha256) DO NOTHING",
            (doc_id, sha256, len(data), rel.as_posix(), url),
        )
        conn.execute("UPDATE documents SET status = 'downloaded' WHERE id = %s AND status = 'discovered'", (doc_id,))
        mark_duplicate(conn, doc_id, sha256)
    print(f"  {ticker} {source_doc_id}: {len(data) / 1e6:.1f} MB")
    return len(data)
