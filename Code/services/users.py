"""Người dùng: chỉ vào được bằng lời mời, đăng nhập bằng link gửi qua email (không mật khẩu), danh sách theo dõi.

    python -m services.users invite ban@example.com [--admin]
    python -m services.users list

Token đăng nhập và phiên chỉ lưu mã băm SHA-256 trong CSDL; token thật chỉ nằm trong link email và cookie.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import secrets
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import psycopg

from services.db import connect
from services.notify import send_email

LOGIN_TTL = timedelta(minutes=30)
SESSION_TTL = timedelta(days=30)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def site_url() -> str:
    return (os.environ.get("SITE_URL") or "http://127.0.0.1:8765").rstrip("/")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class User:
    id: int
    email: str
    role: str
    daily_quota: int

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def invite(conn: psycopg.Connection, email: str, admin: bool = False) -> User:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError(f"Email không hợp lệ: {email!r}")
    row = conn.execute(
        """INSERT INTO users (email, role) VALUES (%s, %s)
           ON CONFLICT (email) DO UPDATE SET role = CASE WHEN %s THEN 'admin' ELSE users.role END
           RETURNING id, email, role, daily_quota""", (email, "admin" if admin else "user", admin)).fetchone()
    return User(*row)


def find_user(conn: psycopg.Connection, email: str) -> User | None:
    row = conn.execute("SELECT id, email, role, daily_quota FROM users WHERE email = %s",
                       (email.strip().lower(),)).fetchone()
    return User(*row) if row else None


def start_login(conn: psycopg.Connection, email: str) -> tuple[bool, str | None]:
    """Gửi link đăng nhập nếu email đã được mời. Trả về (đã gửi qua SMTP, link). Không tiết lộ email có được mời hay
    không: người gọi luôn hiện cùng một thông báo."""
    user = find_user(conn, email)
    if user is None:
        return False, None
    token = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO login_tokens (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                 (_hash(token), user.id, datetime.now(timezone.utc) + LOGIN_TTL))
    link = f"{site_url()}/dang-nhap/{token}"
    sent = send_email(user.email, "[Soi] Link đăng nhập",
                      f"Bấm vào link sau để đăng nhập Soi (hết hạn sau 30 phút, dùng một lần):\n\n{link}\n\n"
                      "Nếu bạn không yêu cầu đăng nhập, hãy bỏ qua email này.")
    return sent, link


def finish_login(conn: psycopg.Connection, token: str) -> str | None:
    """Đổi token đăng nhập (một lần, còn hạn) lấy token phiên cho cookie."""
    row = conn.execute(
        """UPDATE login_tokens SET used_at = now()
           WHERE token_hash = %s AND used_at IS NULL AND expires_at > now() RETURNING user_id""",
        (_hash(token),)).fetchone()
    if row is None:
        return None
    session = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                 (_hash(session), row[0], datetime.now(timezone.utc) + SESSION_TTL))
    conn.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (row[0],))
    return session


def session_user(conn: psycopg.Connection, session: str | None) -> User | None:
    if not session:
        return None
    row = conn.execute(
        """SELECT u.id, u.email, u.role, u.daily_quota FROM sessions s JOIN users u ON u.id = s.user_id
           WHERE s.token_hash = %s AND s.expires_at > now()""", (_hash(session),)).fetchone()
    return User(*row) if row else None


def end_session(conn: psycopg.Connection, session: str | None) -> None:
    if session:
        conn.execute("DELETE FROM sessions WHERE token_hash = %s", (_hash(session),))


def list_users(conn: psycopg.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT u.id, u.email, u.role, u.daily_quota, u.invited_at, u.last_login_at,
                  (SELECT count(*) FROM watchlist w WHERE w.user_id = u.id),
                  (SELECT count(*) FROM processing_requests r WHERE r.user_id = u.id)
           FROM users u ORDER BY u.role, u.email""").fetchall()
    keys = ("id", "email", "role", "daily_quota", "invited_at", "last_login_at", "watching", "requests")
    return [dict(zip(keys, r)) for r in rows]


def _admins(conn) -> int:
    return conn.execute("SELECT count(*) FROM users WHERE role = 'admin'").fetchone()[0]


def update_user(conn: psycopg.Connection, user_id: int, role: str, daily_quota: int) -> None:
    if role not in ("user", "admin") or not 0 <= daily_quota <= 50:
        raise ValueError("Quyền là user/admin, hạn mức 0-50 yêu cầu mỗi ngày")
    current = conn.execute("SELECT role FROM users WHERE id = %s", (user_id,)).fetchone()
    if current is None:
        raise ValueError("Không có người dùng này")
    if current[0] == "admin" and role != "admin" and _admins(conn) <= 1:
        raise ValueError("Phải còn ít nhất một quản trị")
    conn.execute("UPDATE users SET role = %s, daily_quota = %s WHERE id = %s", (role, daily_quota, user_id))


def remove_user(conn: psycopg.Connection, user_id: int, acting_user_id: int) -> None:
    """Xóa người dùng cùng phiên, danh sách theo dõi, yêu cầu (bảng liên quan ON DELETE CASCADE). BCTC riêng họ tải
    lên vẫn giữ trong kho (owner_user_id về NULL thì thành công khai, nên chặn: phải xử lý các BCTC đó trước)."""
    if user_id == acting_user_id:
        raise ValueError("Không tự xóa chính mình")
    row = conn.execute("SELECT role FROM users WHERE id = %s", (user_id,)).fetchone()
    if row is None:
        raise ValueError("Không có người dùng này")
    if row[0] == "admin" and _admins(conn) <= 1:
        raise ValueError("Phải còn ít nhất một quản trị")
    if conn.execute("SELECT 1 FROM documents WHERE owner_user_id = %s LIMIT 1", (user_id,)).fetchone():
        raise ValueError("Người này có BCTC riêng tự tải lên; cần xử lý các BCTC đó trước khi xóa")
    conn.execute("UPDATE documents SET reviewed_by = NULL WHERE reviewed_by = %s", (user_id,))
    conn.execute("DELETE FROM users WHERE id = %s", (user_id,))


def send_invitation(user: User) -> bool:
    return send_email(user.email, "[Soi] Lời mời dùng thử Soi",
                      "Bạn được mời dùng thử Soi: thẻ KQKD đã kiểm chứng cho các mã VN30, kèm cờ cảnh báo và nguồn tới "
                      f"từng trang BCTC.\n\nĐăng nhập bằng email này tại: {site_url()}/dang-nhap\n\n"
                      "Đây là sản phẩm thử nghiệm trong khuôn khổ đồ án tốt nghiệp, chỉ cung cấp thông tin, không phải "
                      "khuyến nghị đầu tư.")


def watchlist(conn: psycopg.Connection, user_id: int) -> list[str]:
    return [r[0] for r in conn.execute("SELECT ticker FROM watchlist WHERE user_id = %s ORDER BY ticker", (user_id,))]


def set_watch(conn: psycopg.Connection, user_id: int, ticker: str, on: bool) -> None:
    if on:
        conn.execute("INSERT INTO watchlist (user_id, ticker) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                     (user_id, ticker.upper()))
    else:
        conn.execute("DELETE FROM watchlist WHERE user_id = %s AND ticker = %s", (user_id, ticker.upper()))


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="python -m services.users", description="Quản lý người dùng được mời")
    sub = p.add_subparsers(dest="command", required=True)
    i = sub.add_parser("invite", help="Mời một email (hoặc nâng lên quyền quản trị)")
    i.add_argument("email")
    i.add_argument("--admin", action="store_true", help="Người duyệt nội bộ: vào được hàng duyệt")
    sub.add_parser("list", help="Liệt kê người dùng")
    args = p.parse_args(argv)
    with connect() as conn:
        if args.command == "invite":
            u = invite(conn, args.email, args.admin)
            print(f"Đã mời {u.email} ({u.role}). Đăng nhập tại {site_url()}/dang-nhap")
        else:
            for row in conn.execute("SELECT email, role, invited_at, last_login_at FROM users ORDER BY id"):
                print(*row)


if __name__ == "__main__":
    main()
