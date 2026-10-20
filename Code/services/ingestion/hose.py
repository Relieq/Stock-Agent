"""Lấy danh sách BCTC từ trang công bố thông tin của HOSE (api.hsx.vn), nguồn thứ hai bên cạnh Vietstock.

Trang hsx.vn là ứng dụng JavaScript; dữ liệu lấy từ API công khai mà chính trang đó gọi:
  * tra mã -> mã công ty của HOSE: GET /l/api/v1/1/securities/stock?code=TCX
  * tệp công ty đã đăng, mới nhất trước: GET /m/api/v1/1/mediafiles/1/<mã công ty>?pageIndex=1&pageSize=30
    (relatedType 5 là BCTC; type "Quý"/"Bán niên"/"Năm", time "03.2026"/"2026"; createdDate là lúc HOSE đăng)
  * tải tệp: thay "~" trong filePath bằng https://staticfile.hsx.vn
Số "1" sau /v1/ là ngôn ngữ tiếng Việt.

So sánh trên 220 BCTC VN30 từ quý 4/2025 đến quý 3/2026 (đo 20/10/2026): HOSE đăng trước Vietstock ở 153 BCTC, sau
ở 57, gần như cùng lúc ở 10; 10% số BCTC có trên HOSE sớm hơn từ 15,5 giờ trở lên. Vì vậy dùng cả hai nguồn, BCTC
có ở nguồn nào trước thì đọc trước, và lấy giờ HOSE đăng làm giờ công bố chính thức.

Tên tệp trên HOSE không dấu và tự đặt; hợp nhất/riêng nhận theo các cách viết đã gặp ("hop nhat", "HN", "rieng", "RL",
"cong ty me", "CTM"). Tệp không ghi gì là BCTC duy nhất của công ty không có công ty con.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

API = "https://api.hsx.vn"
STATIC = "https://staticfile.hsx.vn"
RELATED_FINANCIAL_STATEMENT = 5
_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.hsx.vn/"}

_CONSOLIDATED = re.compile(r"\bhop ?nhat\b|\bhn\b")
_SEPARATE = re.compile(r"\brieng\b|\brl\b|cong ty me|\bctm\b")
_AMENDED = re.compile(r"dieu chinh|dinh chinh|sua doi|bo sung|thay the")
_DOC_TYPE = {"Quý": "fs_quarter", "Bán niên": "fs_semiannual", "Năm": "fs_annual"}


@dataclass(frozen=True)
class HoseStatement:
    ticker: str
    source_doc_id: str          # "<mã tin>/<băm tên tệp>": một tin có thể đính kèm nhiều tệp (hợp nhất và riêng)
    title: str
    url: str
    file_ext: str | None
    doc_type: str
    fiscal_year: int
    fiscal_period: str
    scope: str | None           # consolidated / separate / None (tên tệp không ghi)
    is_amended: bool
    posted_at: datetime


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s).replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def scope_of(file_name: str) -> str | None:
    name = _fold(re.sub(r"[_\-.]+", " ", file_name))
    if _CONSOLIDATED.search(name):
        return "consolidated"
    if _SEPARATE.search(name):
        return "separate"
    return None


def parse_entry(ticker: str, x: dict) -> HoseStatement | None:
    """Một tệp trong danh sách mediafiles -> BCTC; None nếu không phải BCTC quý, bán niên hoặc năm."""
    if x.get("relatedType") != RELATED_FINANCIAL_STATEMENT or x.get("type") not in _DOC_TYPE:
        return None
    t, tm = x["type"], str(x.get("time") or "")
    if t == "Quý":
        m = re.fullmatch(r"(\d{1,2})\.(\d{4})", tm)
        if not m or not 1 <= int(m.group(1)) <= 4:
            return None
        period, year = f"Q{int(m.group(1))}", int(m.group(2))
    elif re.fullmatch(r"\d{4}", tm):
        period, year = ("H1" if t == "Bán niên" else "FY"), int(tm)
    else:
        return None
    path = x["filePath"]
    m = re.search(r"UploadDocuments/(\d+)/", path)
    name = x.get("fileName") or path.rsplit("/", 1)[-1]
    news_id = m.group(1) if m else ""
    return HoseStatement(
        ticker=ticker, source_doc_id=f"{news_id}/{hashlib.sha1(name.encode()).hexdigest()[:12]}", title=name, url=STATIC + quote(path.lstrip("~"), safe="/"),
        file_ext=(x.get("fileType") or Path(name).suffix or "").lstrip(".").lower() or None,
        doc_type=_DOC_TYPE[t], fiscal_year=year, fiscal_period=period, scope=scope_of(name),
        is_amended=bool(_AMENDED.search(_fold(name))),
        posted_at=datetime.fromtimestamp(int(x["createdDate"]), tz=timezone.utc))


class HoseClient:
    def __init__(self, ids_path: Path | None = None, delay_seconds: float = 1.0, timeout: float = 30.0):
        self.session = requests.Session()
        self.session.headers.update(_HEADERS)
        self.delay_seconds = delay_seconds
        self.timeout = timeout
        self.ids_path = ids_path
        try:
            self.ids: dict[str, int] = json.loads(ids_path.read_text(encoding="utf-8")) if ids_path else {}
        except (OSError, ValueError):
            self.ids = {}

    def _get(self, url: str) -> dict:
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        time.sleep(self.delay_seconds)
        return resp.json()

    def company_id(self, ticker: str) -> int | None:
        if ticker not in self.ids:
            data = self._get(f"{API}/l/api/v1/1/securities/stock?code={quote(ticker)}")["data"]
            hit = next((x["id"] for x in data.get("list") or [] if x.get("code") == ticker), None)
            if hit is None:
                return None
            self.ids[ticker] = hit
            if self.ids_path:
                try:
                    self.ids_path.write_text(json.dumps(self.ids, indent=0), encoding="utf-8")
                except OSError:
                    pass
        return self.ids[ticker]

    def list_statements(self, ticker: str, page_size: int = 30) -> list[HoseStatement]:
        """BCTC mới nhất của mã trên HOSE (trang đầu, mới nhất trước); mã không niêm yết trên HOSE thì rỗng."""
        cid = self.company_id(ticker)
        if cid is None:
            return []
        data = self._get(f"{API}/m/api/v1/1/mediafiles/1/{cid}?pageIndex=1&pageSize={page_size}")["data"]
        out, seen = [], set()
        for x in data.get("list") or []:
            st = parse_entry(ticker, x)
            if st is not None and st.url not in seen:
                seen.add(st.url)
                out.append(st)
        return out

    def download(self, url: str, dest_path, chunk_size: int = 1 << 16) -> None:
        with self.session.get(url, stream=True, timeout=self.timeout) as resp:
            resp.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size):
                    f.write(chunk)
