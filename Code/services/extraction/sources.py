"""Mở file đã tải, chọn đúng PDF cần đọc, đánh giá lớp text từng trang.

Thực tế quý 2/2026 của VN30 (58 file):
  * file .zip có thể chứa bản tiếng Anh, công văn CBTT, hoặc cả bản scan có chữ ký lẫn bản "tra cứu" có lớp text;
  * phần lớn là bản scan; một số có lớp text do OCR hỏng (mất dấu, sai ký tự), nên phải đánh giá chất lượng
    lớp text chứ không chỉ kiểm tra có text hay không.
"""

from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pymupdf

# Tên file trong zip cần bỏ qua
_SKIP_MEMBER = re.compile(
    r"cong[_\- ]?van|cbtt|en[_\- ]?ver|english|\beng?\b|financial[_\- ]?statements|quarter|_en[_.\-]",
    re.IGNORECASE,
)
# Bản có lớp text để tra cứu: ưu tiên
_SEARCHABLE_MEMBER = re.compile(r"tra[_\- ]?cuu", re.IGNORECASE)

_VN_LETTERS = set("ăâđêôơưàáạảãầấậẩẫằắặẳẵèéẹẻẽềếệểễìíịỉĩòóọỏõồốộổỗờớợởỡùúụủũừứựửữỳýỵỷỹ")
_KEYWORDS = ("tài sản", "nguồn vốn", "doanh thu", "lợi nhuận", "lưu chuyển", "tiền")


@dataclass
class PdfCandidate:
    name: str
    data: bytes
    note: str = ""


def candidates(path: Path) -> list[PdfCandidate]:
    """Các PDF nên đọc trong một file đã tải. Nhiều hơn một ứng viên nghĩa là chưa chọn được bằng tên file."""
    if not zipfile.is_zipfile(path):
        return [PdfCandidate(path.name, path.read_bytes())]

    with zipfile.ZipFile(path) as z:
        members = [m for m in z.namelist() if m.lower().endswith(".pdf")]
        kept = [m for m in members if not _SKIP_MEMBER.search(Path(m).stem)]
        searchable = [m for m in kept if _SEARCHABLE_MEMBER.search(m)]
        chosen = searchable or kept or members
        note = "bản tra cứu" if searchable else ("chưa phân biệt được bằng tên file" if len(chosen) > 1 else "")
        return [PdfCandidate(m, z.read(m), note) for m in chosen]


@dataclass
class PageText:
    page: int          # đánh số từ 1
    text: str
    usable: bool


def text_quality(text: str) -> tuple[int, float]:
    """(số chữ cái, tỷ lệ chữ có dấu tiếng Việt). Lớp text OCR hỏng thường gần như không có dấu."""
    t = unicodedata.normalize("NFC", text).casefold()
    letters = [c for c in t if c.isalpha()]
    if not letters:
        return 0, 0.0
    return len(letters), sum(c in _VN_LETTERS for c in letters) / len(letters)


def page_texts(doc: pymupdf.Document) -> list[PageText]:
    out = []
    for i, page in enumerate(doc):
        text = unicodedata.normalize("NFC", page.get_text())
        n_letters, vn_ratio = text_quality(text)
        lowered = text.casefold()
        usable = n_letters >= 200 and vn_ratio >= 0.08 and any(k in lowered for k in _KEYWORDS)
        out.append(PageText(i + 1, text, usable))
    return out


def open_pdf(candidate: PdfCandidate) -> pymupdf.Document:
    return pymupdf.open(stream=io.BytesIO(candidate.data), filetype="pdf")


def render_page(doc: pymupdf.Document, page: int, long_side: int, rotate: int = 0) -> bytes:
    """Ảnh PNG của trang (đánh số từ 1), cạnh dài khoảng `long_side` pixel, xoay `rotate` độ theo chiều kim đồng hồ."""
    p = doc[page - 1]
    zoom = long_side / max(p.rect.width, p.rect.height)
    pix = p.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom).prerotate(rotate), colorspace=pymupdf.csGRAY)
    return pix.tobytes("png")
