"""Kết nối PostgreSQL và áp dụng migration trong db/migrations/."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

CODE_DIR = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = CODE_DIR / "db" / "migrations"

load_dotenv(CODE_DIR / ".env")

DEFAULT_DATABASE_URL = "postgresql://soi:soi@localhost:5433/soi"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def connect() -> psycopg.Connection:
    return psycopg.connect(database_url())


def migrate(conn: psycopg.Connection) -> list[str]:
    """Áp dụng các file .sql chưa chạy, theo thứ tự tên file. Trả về danh sách file vừa áp dụng."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version TEXT PRIMARY KEY,"
        " applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    conn.commit()
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}

    done = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,))
        done.append(path.name)
    return done
