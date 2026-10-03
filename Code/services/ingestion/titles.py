"""Nhận dạng tài liệu BCTC từ tiêu đề do nguồn đặt.

Luật viết theo tiêu đề thực tế của Vietstock (526 tài liệu năm 2025-2026 của VN30, xem tests/test_titles.py), ví dụ:
    "BCTC Hợp nhất quý 2 năm 2026"
    "BCTC Công ty mẹ Soát xét 6 tháng đầu năm 2026"
    "BCTC Kiểm toán năm 2025"                       (công ty không có công ty con)
    "KQKD Hợp nhất Soát xét quý 3 năm 2025"         (chỉ có báo cáo KQKD)
    "Thuyết minh BCTC Hợp nhất quý 1 năm 2025 (điều chỉnh)"

Trường nào không nhận dạng được thì để None; không đoán.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

DOC_TYPE_BY_PERIOD = {
    "Q1": "fs_quarter",
    "Q2": "fs_quarter",
    "Q3": "fs_quarter",
    "Q4": "fs_quarter",
    "H1": "fs_semiannual",
    "9M": "fs_9m",
    "FY": "fs_annual",
}

# Thứ tự quan trọng: "thuyết minh bctc" phải đứng trước "bctc"
_CONTENT_PREFIXES = [
    ("thuyết minh bctc", "notes"),
    ("bctc", "full"),
    ("kqkd", "income_statement"),
    ("lctt", "cash_flow"),
    ("cđkt", "balance_sheet"),
    ("bcđkt", "balance_sheet"),
]

_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_QUARTER_RE = re.compile(r"\bquý\s*([1-4])\b")


@dataclass(frozen=True)
class TitleInfo:
    content_kind: str | None
    doc_type: str | None
    fiscal_year: int | None
    fiscal_period: str | None
    scope: str | None
    audit_status: str | None
    is_amended: bool

    @property
    def is_recognized(self) -> bool:
        return None not in (self.content_kind, self.fiscal_year, self.fiscal_period, self.scope)


def _normalize(title: str) -> str:
    text = unicodedata.normalize("NFC", title)
    return re.sub(r"\s+", " ", text).strip().casefold()


def parse_title(title: str) -> TitleInfo:
    t = _normalize(title)

    content_kind = next((kind for prefix, kind in _CONTENT_PREFIXES if t.startswith(prefix)), None)

    if "hợp nhất" in t:
        scope = "consolidated"
    elif "công ty mẹ" in t or "riêng" in t:
        scope = "separate"
    elif content_kind is not None:
        # Tiêu đề không ghi phạm vi: công ty chỉ lập một báo cáo (không có công ty con)
        scope = "standalone"
    else:
        scope = None

    if "soát xét" in t:
        audit_status = "reviewed"
    elif "kiểm toán" in t:
        audit_status = "audited"
    else:
        audit_status = "none"

    years = _YEAR_RE.findall(t)
    fiscal_year = int(years[-1]) if years else None

    quarter = _QUARTER_RE.search(t)
    if quarter:
        fiscal_period = f"Q{quarter.group(1)}"
    elif "6 tháng" in t:
        fiscal_period = "H1"
    elif "9 tháng" in t:
        fiscal_period = "9M"
    elif fiscal_year is not None and re.search(r"\bnăm\s+20\d{2}\b", t):
        fiscal_period = "FY"
    else:
        fiscal_period = None

    return TitleInfo(
        content_kind=content_kind,
        doc_type=DOC_TYPE_BY_PERIOD.get(fiscal_period) if fiscal_period else None,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        scope=scope,
        audit_status=audit_status,
        is_amended="điều chỉnh" in t,
    )
