"""Lấy danh sách tài liệu BCTC từ Vietstock.

Cách gọi endpoint `data/getdocument` (lấy token từ trang tài liệu rồi POST theo trang) dựa trên
nodes/extract_link.py của repo khóa trước, giấy phép MIT:
https://github.com/buinguyenkhai/stock-report-agent-20251 (Copyright (c) 2025 buinguyenkhai).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

BASE_URL = "https://finance.vietstock.vn"
DOC_TYPE_FINANCIAL_STATEMENTS = 1  # tham số `type` của Vietstock cho BCTC

_USER_AGENT = "Mozilla/5.0"
_TOKEN_RE = re.compile(r"name=__RequestVerificationToken[^>]*value=([^\s>]+)")
_DATE_RE = re.compile(r"/Date\((\d+)\)/")


@dataclass(frozen=True)
class SourceDocument:
    ticker: str
    source_doc_id: str
    title: str
    url: str
    file_ext: str | None
    listed_at: datetime | None


def parse_dotnet_date(value: str | None) -> datetime | None:
    """'/Date(1785206047917)/' -> datetime UTC."""
    if not value:
        return None
    m = _DATE_RE.fullmatch(value.strip())
    if not m:
        return None
    return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc)


class VietstockClient:
    def __init__(self, delay_seconds: float = 1.0, timeout: float = 30.0):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = _USER_AGENT
        self.delay_seconds = delay_seconds
        self.timeout = timeout

    def _token(self, page_url: str) -> str:
        html = self.session.get(page_url, timeout=self.timeout).text
        m = _TOKEN_RE.search(html)
        if not m:
            raise RuntimeError(f"Không lấy được __RequestVerificationToken từ {page_url}")
        return m.group(1).strip("\"'")

    def list_financial_statements(self, ticker: str, year: int | None = None, max_pages: int = 30) -> list[SourceDocument]:
        ticker = ticker.upper()
        page_url = f"{BASE_URL}/{ticker}/tai-tai-lieu.htm?doctype={DOC_TYPE_FINANCIAL_STATEMENTS}"
        token = self._token(page_url)
        headers = {"X-Requested-With": "XMLHttpRequest", "Referer": page_url}

        docs: dict[str, SourceDocument] = {}
        total_rows: int | None = None
        for page in range(1, max_pages + 1):
            payload: dict[str, object] = {
                "code": ticker,
                "page": page,
                "type": DOC_TYPE_FINANCIAL_STATEMENTS,
                "__RequestVerificationToken": token,
            }
            if year is not None:
                payload["year"] = year
            resp = self.session.post(f"{BASE_URL}/data/getdocument", data=payload, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            if "application/json" not in (resp.headers.get("content-type") or "").lower():
                raise RuntimeError(f"Vietstock trả về {resp.headers.get('content-type')!r} thay vì JSON ({ticker}, trang {page})")
            items = resp.json()
            if not isinstance(items, list) or not items:
                break

            for it in items:
                doc_id = str(it.get("FileInfoID") or "").strip()
                title = (it.get("Title") or "").strip()
                url = (it.get("Url") or "").strip()
                if not doc_id or not title or not url:
                    continue
                docs[doc_id] = SourceDocument(
                    ticker=ticker,
                    source_doc_id=doc_id,
                    title=title,
                    url=url,
                    file_ext=(it.get("FileExt") or "").strip().lstrip(".").lower() or None,
                    listed_at=parse_dotnet_date(it.get("LastUpdate")),
                )

            if total_rows is None:
                total_rows = int(items[0].get("TotalRow") or 0)
            if total_rows and len(docs) >= total_rows:
                break
            time.sleep(self.delay_seconds)

        return list(docs.values())

    def download(self, url: str, dest_path, chunk_size: int = 1 << 16) -> None:
        with self.session.get(url, stream=True, timeout=self.timeout) as resp:
            resp.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size):
                    f.write(chunk)
