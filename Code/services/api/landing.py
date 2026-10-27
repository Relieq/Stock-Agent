"""Trang giới thiệu (trang đầu cho người chưa đăng nhập): đường dẫn công khai, video demo tính năng, số liệu sống.

Video demo dựng ngoài repo (Demo/video, không đưa lên git) rồi chép vào <RAW_DATA_DIR>/demo cùng videos.json
(slug, title, desc, seconds); mỗi slug có <slug>.mp4 và <slug>.jpg (ảnh bìa)."""
from __future__ import annotations

import json
import re
from pathlib import Path

# "/" chỉ công khai đúng trang chủ; các mục còn lại công khai theo tiền tố
PUBLIC_PREFIXES = ("/dang-nhap", "/static/", "/chia-se/", "/anh/", "/suc-khoe", "/video/", "/xin-dung-thu",
                   "/gioi-thieu")
INTRO = "gioi-thieu"
# Video phía quản trị: cho người xem thấy số được kiểm và duyệt thế nào
BEHIND = ("xem-anh", "duyet-tay", "chi-phi")
_NAME = re.compile(r"^[a-z0-9-]+\.(mp4|jpg)$")


def is_public(path: str) -> bool:
    return path == "/" or path.startswith(PUBLIC_PREFIXES)


def video_file(folder: Path, name: str) -> Path | None:
    """Tệp video/ảnh bìa trong thư mục demo; tên lạ hoặc tệp không có thì None."""
    if not _NAME.match(name):
        return None
    path = folder / name
    return path if path.is_file() else None


def available(folder: Path) -> dict[str, int]:
    """Tệp video/ảnh có trong thư mục demo -> thời điểm sửa (trang chỉ hiện phần có tệp; thời điểm sửa gắn vào đường
    dẫn để trình duyệt tải bản mới khi tệp được dựng lại, vì /video/ cho trình duyệt nhớ 1 ngày)."""
    if not folder.is_dir():
        return {}
    return {p.name: int(p.stat().st_mtime) for p in folder.glob("*") if _NAME.match(p.name)}


def demo_videos(folder: Path) -> dict:
    """{"intro": video giới thiệu hoặc None, "user": [...], "behind": [...]} theo thứ tự trong videos.json, bỏ video
    thiếu tệp."""
    out = {"intro": None, "user": [], "behind": []}
    try:
        items = json.loads((folder / "videos.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    for it in items:
        if video_file(folder, f"{it['slug']}.mp4") is None:
            continue
        if it["slug"] == INTRO:
            out["intro"] = it
        else:
            out["behind" if it["slug"] in BEHIND else "user"].append(it)
    return out


def site_stats(conn) -> dict:
    """Số liệu sống cho trang giới thiệu: BCTC đã kiểm chứng (không tính tài liệu riêng của người dùng, bản trùng) và
    BCTC xử lý xong gần nhất."""
    row = conn.execute(
        """SELECT count(*), count(DISTINCT ticker) FROM documents
           WHERE status IN ('verified', 'approved') AND content_kind = 'full'
             AND owner_user_id IS NULL AND duplicate_of IS NULL""").fetchone()
    last = conn.execute(
        """SELECT ticker, fiscal_period, fiscal_year, processed_at FROM documents
           WHERE status IN ('verified', 'approved') AND content_kind = 'full'
             AND owner_user_id IS NULL AND duplicate_of IS NULL AND processed_at IS NOT NULL
           ORDER BY processed_at DESC LIMIT 1""").fetchone()
    return {"documents": row[0], "tickers": row[1],
            "last": {"ticker": last[0], "period": last[1], "year": last[2], "at": last[3]} if last else None,
            **coverage(conn)}


def coverage(conn) -> dict:
    """Các mã đang theo dõi và mã nào đã có BCTC quý kiểm chứng của kỳ quý mới nhất."""
    latest = conn.execute(
        """SELECT fiscal_year, fiscal_period FROM documents
           WHERE status IN ('verified', 'approved') AND doc_type = 'fs_quarter' AND owner_user_id IS NULL
           ORDER BY fiscal_year DESC, fiscal_period DESC LIMIT 1""").fetchone()
    done = set()
    if latest:
        done = {r[0] for r in conn.execute(
            """SELECT DISTINCT ticker FROM documents WHERE status IN ('verified', 'approved') AND doc_type = 'fs_quarter'
               AND owner_user_id IS NULL AND fiscal_year = %s AND fiscal_period = %s""", latest).fetchall()}
    tickers = [r[0] for r in conn.execute("SELECT ticker FROM companies WHERE tracked ORDER BY ticker").fetchall()]
    return {"coverage": [(t, t in done) for t in tickers],
            "season": f"{latest[1]}/{latest[0]}" if latest else None}
