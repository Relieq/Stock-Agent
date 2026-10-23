"""Góp ý của người dùng thử: lưu kèm trang đang xem, báo email cho quản trị, quản trị xem danh sách trên web."""

from __future__ import annotations

MAX_LEN = 2000
DAILY_LIMIT = 10          # chặn gửi lặp; người dùng thử thật không cần nhiều hơn


def safe_page(page: str | None) -> str:
    """Chỉ nhận đường dẫn trong trang (không cho chuyển hướng ra ngoài qua `//host`)."""
    page = (page or "").strip()
    if not page.startswith("/") or page.startswith("//") or "\\" in page:
        return "/"
    return page[:300]


def clean_message(message: str | None) -> str:
    text = (message or "").strip()
    if not text:
        raise ValueError("Góp ý đang trống")
    if len(text) > MAX_LEN:
        raise ValueError(f"Góp ý dài quá {MAX_LEN} ký tự")
    return text


def save(conn, user_id: int, page: str, message: str) -> int:
    page, text = safe_page(page), clean_message(message)
    sent = conn.execute("SELECT count(*) FROM feedback WHERE user_id = %s AND created_at > now() - interval '1 day'",
                        (user_id,)).fetchone()[0]
    if sent >= DAILY_LIMIT:
        raise ValueError("Hôm nay bạn đã gửi nhiều góp ý, mai gửi tiếp nhé")
    fid = conn.execute("INSERT INTO feedback (user_id, page, message) VALUES (%s, %s, %s) RETURNING id",
                       (user_id, page, text)).fetchone()[0]
    conn.commit()
    return fid


def recent(conn, limit: int = 200) -> list[dict]:
    rows = conn.execute("""SELECT f.id, u.email, f.page, f.message, f.created_at FROM feedback f
                           JOIN users u ON u.id = f.user_id ORDER BY f.created_at DESC LIMIT %s""", (limit,)).fetchall()
    return [dict(zip(("id", "email", "page", "message", "created_at"), r)) for r in rows]


def email_body(email: str, page: str, message: str) -> str:
    return f"{email} góp ý ở trang {page}:\n\n{message}\n"
