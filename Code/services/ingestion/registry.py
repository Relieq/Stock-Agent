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
from services.ingestion.titles import parse_title
from services.ingestion.vietstock import SourceDocument, VietstockClient

SEEDS_DIR = CODE_DIR / "db" / "seeds"


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
        RETURNING (xmax = 0) AS inserted
        """,
        (
            doc.ticker, source, doc.source_doc_id, doc.url, doc.title, doc.file_ext,
            info.content_kind, info.doc_type, info.fiscal_year, info.fiscal_period, info.scope,
            info.audit_status, info.is_amended, doc.listed_at,
        ),
    ).fetchone()
    return bool(row[0])


def discover(conn: psycopg.Connection, client: VietstockClient, tickers: list[str], year: int | None) -> dict[str, int]:
    """Lấy danh sách BCTC của từng mã từ Vietstock và ghi vào bảng documents."""
    stats = {"seen": 0, "new": 0, "errors": 0}
    for ticker in tickers:
        try:
            docs = client.list_financial_statements(ticker, year=year)
        except Exception as e:  # một mã lỗi không làm dừng cả lượt
            print(f"  {ticker}: lỗi khi lấy danh sách: {e}")
            stats["errors"] += 1
            continue
        with conn.transaction():
            new = sum(upsert_document(conn, d) for d in docs)
        stats["seen"] += len(docs)
        stats["new"] += new
        print(f"  {ticker}: {len(docs)} tài liệu, {new} mới")
    return stats


def _safe_filename(url: str) -> str:
    name = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    name = re.sub(r"%20| ", "_", name)
    return re.sub(r"[^\w.\-]", "_", name) or "file"


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
        "SELECT id, ticker, source_doc_id, source_url FROM documents",
        "WHERE fiscal_year = %s AND NOT EXISTS (SELECT 1 FROM document_files f WHERE f.document_id = documents.id)",
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

    root = raw_data_dir()
    stats = {"downloaded": 0, "errors": 0, "bytes": 0}
    for doc_id, ticker, source_doc_id, url in rows:
        rel = Path("vietstock") / ticker / str(year) / f"{source_doc_id}_{_safe_filename(url)}"
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as tmp:
                tmp_path = Path(tmp.name)
            client.download(url, tmp_path)
            data = tmp_path.read_bytes()
            sha256 = hashlib.sha256(data).hexdigest()
            tmp_path.replace(dest)
        except Exception as e:
            print(f"  {ticker} {source_doc_id}: lỗi khi tải: {e}")
            tmp_path.unlink(missing_ok=True)
            stats["errors"] += 1
            continue
        with conn.transaction():
            conn.execute(
                "INSERT INTO document_files (document_id, sha256, size_bytes, storage_key, source_url)"
                " VALUES (%s, %s, %s, %s, %s) ON CONFLICT (document_id, sha256) DO NOTHING",
                (doc_id, sha256, len(data), rel.as_posix(), url),
            )
            conn.execute("UPDATE documents SET status = 'downloaded' WHERE id = %s AND status = 'discovered'", (doc_id,))
        stats["downloaded"] += 1
        stats["bytes"] += len(data)
        print(f"  {ticker} {source_doc_id}: {len(data) / 1e6:.1f} MB")
        time.sleep(client.delay_seconds)
    return stats
