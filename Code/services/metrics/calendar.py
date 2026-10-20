"""Lịch công bố BCTC quý của các mã đang theo dõi: đã công bố chưa, hạn chót, ngày dự kiến theo thói quen các quý trước.

Hạn theo quy định công bố thông tin (vision-and-roadmap.md mục 3.2): BCTC quý trong 20 ngày sau khi hết quý, công ty mẹ
lập BCTC hợp nhất được 30 ngày. Ngày "công bố" ở đây là lúc BCTC xuất hiện sớm nhất trên Vietstock hoặc HOSE, thường trễ hơn
giờ công bố chính thức vài giờ; giờ chính thức (published_at) chưa thu thập.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg

VN = ZoneInfo("Asia/Ho_Chi_Minh")
QUARTER_END = {"Q1": (3, 31), "Q2": (6, 30), "Q3": (9, 30), "Q4": (12, 31)}
DEADLINE_DAYS = {"standalone": 20, "consolidated": 30}


def quarter_end(year: int, period: str) -> date:
    m, d = QUARTER_END[period]
    return date(year, m, d)


def deadline(year: int, period: str, consolidated: bool) -> date:
    return quarter_end(year, period) + timedelta(days=DEADLINE_DAYS["consolidated" if consolidated else "standalone"])


@dataclass
class Entry:
    ticker: str
    name: str
    consolidated: bool
    quarter_end: date
    deadline: date
    published: datetime | None          # lúc BCTC quý đầu tiên của kỳ xuất hiện (Vietstock hoặc HOSE)
    typical_days: int | None            # số ngày sau khi hết quý mà mã này thường công bố (trung vị các quý trước)
    history: int                        # số quý trước dùng để tính

    @property
    def expected(self) -> date | None:
        return None if self.typical_days is None else self.quarter_end + timedelta(days=self.typical_days)

    @property
    def published_date(self) -> date | None:
        return None if self.published is None else self.published.astimezone(VN).date()

    def status(self, today: date) -> str:
        """published / late (công bố sau hạn) / pending / overdue (quá hạn chưa thấy)."""
        if self.published is not None:
            return "late" if self.published_date > self.deadline else "published"
        return "overdue" if today > self.deadline else "pending"


def _listed(conn: psycopg.Connection) -> dict[tuple[str, int, str], datetime]:
    """(mã, năm, kỳ) -> lúc BCTC quý đầu tiên của kỳ đó xuất hiện công khai, ở nguồn nào sớm hơn (giờ Vietstock hay
    HOSE đăng; mọi phạm vi, bỏ bản tải lên riêng)."""
    rows = conn.execute(
        """SELECT ticker, fiscal_year, fiscal_period, min(LEAST(source_listed_at, published_at)) FROM documents
           WHERE doc_type = 'fs_quarter' AND owner_user_id IS NULL AND source_listed_at IS NOT NULL
             AND fiscal_period IN ('Q1', 'Q2', 'Q3', 'Q4')
           GROUP BY 1, 2, 3""").fetchall()
    return {(t, y, p): at for t, y, p, at in rows}


def today_vn() -> date:
    return datetime.now(VN).date()


def calendar(conn: psycopg.Connection, year: int, period: str) -> list[Entry]:
    listed = _listed(conn)
    consolidated = {t for (t,) in conn.execute(
        "SELECT DISTINCT ticker FROM documents WHERE scope = 'consolidated' AND owner_user_id IS NULL")}
    end = quarter_end(year, period)
    out = []
    for ticker, name in conn.execute("SELECT ticker, name FROM companies WHERE tracked ORDER BY ticker").fetchall():
        past = sorted((quarter_end(y, p), (at.astimezone(VN).date() - quarter_end(y, p)).days)
                      for (t, y, p), at in listed.items() if t == ticker and quarter_end(y, p) < end)
        past = [days for _, days in past if 0 <= days <= 120][-8:]   # 8 quý gần nhất
        out.append(Entry(ticker, name, ticker in consolidated, end, deadline(year, period, ticker in consolidated),
                         listed.get((ticker, year, period)), round(statistics.median(past)) if past else None,
                         len(past)))
    return out


def current_quarter(today: date | None = None) -> tuple[int, str]:
    """Quý vừa kết thúc gần nhất (mùa BCTC đang diễn ra): ngày 13/10/2026 -> (2026, "Q3")."""
    today = today or today_vn()
    ends = [(quarter_end(y, p), y, p) for y in (today.year - 1, today.year) for p in QUARTER_END]
    _, y, p = max(e for e in ends if e[0] < today)
    return y, p
