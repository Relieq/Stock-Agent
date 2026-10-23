"""Tình trạng hệ thống cho dịch vụ theo dõi bên ngoài (trang /suc-khoe): bộ canh còn chạy không.

Bộ canh ghi nhịp tim ở đầu và cuối mỗi lượt; khi máy tắt hoặc Docker dừng thì không còn ai gửi được email, nên cần một
dịch vụ bên ngoài gọi trang này và báo khi nhận mã lỗi."""

from __future__ import annotations

from datetime import datetime, timezone

from services.ingestion.registry import raw_data_dir

MAX_SILENCE_MIN = 120     # lượt cách nhau 15 phút; chưa đo lượt dài nhất (nhiều BCTC cùng về), báo nhầm thì nâng


def heartbeat_path():
    return raw_data_dir() / "watcher_heartbeat.txt"


def last_heartbeat() -> datetime | None:
    try:
        return datetime.fromisoformat(heartbeat_path().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def watcher_status(last: datetime | None, now: datetime, max_silence_min: int = MAX_SILENCE_MIN) -> dict:
    if last is None:
        return {"ok": False, "watcher": "chưa có nhịp tim"}
    minutes = int((now - last).total_seconds() // 60)
    return {"ok": minutes <= max_silence_min, "watcher_minutes_since_beat": minutes}


def status(now: datetime | None = None) -> dict:
    return watcher_status(last_heartbeat(), now or datetime.now(timezone.utc))
