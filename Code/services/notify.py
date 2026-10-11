"""Gửi email qua SMTP. Chưa cấu hình SMTP thì chỉ in ra màn hình.

Cấu hình trong Code/.env:
    SMTP_HOST=smtp.gmail.com   SMTP_PORT=587   SMTP_USER=...   SMTP_PASSWORD=...   (với Gmail: mật khẩu ứng dụng)
    MAIL_FROM=...              ADMIN_EMAIL=...  (người nhận thông báo vận hành)
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

import services.db  # noqa: F401  (nạp Code/.env)


def smtp_configured() -> bool:
    return all(os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"))


def send_email(to: str, subject: str, body: str) -> bool:
    """Trả về True nếu đã gửi qua SMTP; False nếu chưa cấu hình (khi đó chỉ in ra)."""
    if not smtp_configured() or not to:
        print(f"[email chưa gửi: chưa cấu hình SMTP] {subject}\n{body}")
        return False
    msg = EmailMessage()
    msg["From"] = os.environ.get("MAIL_FROM") or os.environ["SMTP_USER"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587")), timeout=30) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        s.send_message(msg)
    return True


def notify_admin(subject: str, body: str) -> bool:
    return send_email(os.environ.get("ADMIN_EMAIL", ""), subject, body)
