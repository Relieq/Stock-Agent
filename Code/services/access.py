"""Xin dùng thử: khách để lại email ở trang giới thiệu, quản trị xem danh sách ở /quan-tri và bấm mời.

Khách luôn nhận cùng một câu trả lời, dù email đã có tài khoản hay đã xin gần đây, để người lạ không dò được email nào
đã đăng ký."""

from __future__ import annotations

from services.users import EMAIL_RE

MAX_NOTE = 500
REPEAT_DAYS = 7           # cùng một email xin lại trong 7 ngày: không lưu, không báo quản trị lần nữa
HOURLY_LIMIT = 20         # tổng số yêu cầu mới mỗi giờ, chặn gửi dồn làm đầy hộp thư quản trị


def clean_request(email: str | None, note: str | None) -> tuple[str, str]:
    email, note = (email or "").strip().lower(), (note or "").strip()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise ValueError("Email chưa đúng")
    if len(note) > MAX_NOTE:
        raise ValueError(f"Ghi chú dài quá {MAX_NOTE} ký tự")
    return email, note


def save(conn, email: str, note: str) -> bool:
    """Lưu yêu cầu; True khi là yêu cầu mới cần báo quản trị. Email đã có tài khoản hoặc vừa xin: False (không lỗi)."""
    email, note = clean_request(email, note)
    if conn.execute("SELECT count(*) FROM users WHERE lower(email) = %s", (email,)).fetchone()[0]:
        return False
    if conn.execute(f"""SELECT count(*) FROM access_requests WHERE email = %s
                        AND created_at > now() - interval '{REPEAT_DAYS} days'""", (email,)).fetchone()[0]:
        return False
    if conn.execute("SELECT count(*) FROM access_requests WHERE created_at > now() - interval '1 hour'"
                    ).fetchone()[0] >= HOURLY_LIMIT:
        raise ValueError("Đang có nhiều yêu cầu, bạn thử lại sau ít phút nhé")
    conn.execute("INSERT INTO access_requests (email, note) VALUES (%s, %s)", (email, note))
    conn.commit()
    return True


def pending(conn) -> list[dict]:
    """Yêu cầu chưa mời (mỗi email lấy lần xin gần nhất), email chưa có tài khoản."""
    rows = conn.execute(
        """SELECT DISTINCT ON (r.email) r.email, r.note, r.created_at FROM access_requests r
           WHERE r.invited_at IS NULL AND NOT EXISTS (SELECT 1 FROM users u WHERE lower(u.email) = r.email)
           ORDER BY r.email, r.created_at DESC""").fetchall()
    out = [dict(zip(("email", "note", "created_at"), r)) for r in rows]
    return sorted(out, key=lambda r: r["created_at"], reverse=True)


def mark_invited(conn, email: str) -> None:
    conn.execute("UPDATE access_requests SET invited_at = now() WHERE email = %s AND invited_at IS NULL",
                 ((email or "").strip().lower(),))
    conn.commit()


def email_body(email: str, note: str) -> str:
    return (f"{email} xin dùng thử Soi.\n\n" + (f"Ghi chú: {note}\n\n" if note else "")
            + "Mời ở trang Quản trị > Người dùng.\n")
