"""Mở file đã tải, chọn đúng PDF cần đọc, đánh giá lớp text từng trang.

Thực tế quý 2/2026 của VN30 (58 file):
  * file .zip có thể chứa bản tiếng Anh, công văn CBTT, hoặc cả bản scan có chữ ký lẫn bản "tra cứu" có lớp text;
  * phần lớn là bản scan; một số có lớp text do OCR hỏng (mất dấu, sai ký tự), nên phải đánh giá chất lượng
    lớp text chứ không chỉ kiểm tra có text hay không.
"""

from __future__ import annotations

import io
import math
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from PIL import Image

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


# Ảnh "nét" cho các bước đọc lại (đo 14/10/2026 trên 86 ô đã biết là đọc sai: đọc lại ra đúng 73% so với 45% khi vẽ
# trang cạnh dài 3000 rồi để API tự thu nhỏ; ô đang đúng không bị đọc hỏng thêm; lợi ích dồn vào scan <= 100 dpi).
# Vẽ trang đúng độ phân giải ảnh scan gốc (1 điểm ảnh trang = 1 điểm ảnh scan, không để MuPDF phóng kiểu nhân bản điểm
# ảnh làm chữ số răng cưa), rồi phóng một lần bằng Lanczos tới cỡ chữ số cao khoảng 28 điểm ảnh. Gửi kèm
# detail="original" để API không thu nhỏ lại (mức mặc định của gpt-5.4-mini thu cạnh dài về 2048 và 2.500 ô 32x32).
SHARP_DPI = 288             # chữ số khoảng 7pt -> khoảng 28 điểm ảnh
SHARP_MAX_UPSCALE = 3.0     # phóng quá 3 lần ảnh gốc không thêm thông tin
SHARP_PATCH_BUDGET = 10000  # giới hạn của detail="original" (ô 32x32)
LOW_DPI = 100               # scan từ mức này trở xuống: dùng ảnh nét ngay từ lần chép đầu


def native_dpi(doc: pymupdf.Document, page: int) -> float | None:
    """Độ phân giải của ảnh scan chiếm gần hết trang; None nếu trang vẽ bằng chữ và nét (PDF xuất từ phần mềm)."""
    p = doc[page - 1]
    area = p.rect.width * p.rect.height
    best = None
    for img in p.get_images(full=True):
        try:
            bbox = p.get_image_bbox(img)
        except (ValueError, RuntimeError):
            continue
        if bbox.is_empty or bbox.is_infinite or bbox.width * bbox.height < 0.6 * area:
            continue
        best = max(best or 0.0, img[2] / bbox.width * 72)
    return best


def render_sharp(doc: pymupdf.Document, page: int, rotate: int = 0, dpi: float = SHARP_DPI,
                 clip: tuple[float, float] | None = None) -> bytes:
    """Ảnh PNG xám của trang (hoặc dải ngang `clip` = (trên, dưới) theo tỉ lệ chiều cao, tính trên ảnh đã xoay) ở độ
    phân giải `dpi`, không quá 3 lần ảnh scan gốc và vừa giới hạn ô của detail="original"."""
    p = doc[page - 1]
    nd = native_dpi(doc, page)
    frac = clip[1] - clip[0] if clip else 1.0
    target = dpi if nd is None else min(dpi, nd * SHARP_MAX_UPSCALE)
    target = min(target, 72 * math.sqrt(SHARP_PATCH_BUDGET * 0.95 * 1024 / (p.rect.width * p.rect.height * frac)))
    base = target if nd is None else min(nd, target)
    pix = p.get_pixmap(matrix=pymupdf.Matrix(base / 72, base / 72).prerotate(rotate), colorspace=pymupdf.csGRAY)
    img = Image.frombuffer("L", (pix.width, pix.height), pix.samples, "raw", "L", pix.stride, 1)
    if clip:
        img = img.crop((0, round(img.height * clip[0]), img.width, round(img.height * clip[1])))
    if target > base * 1.01:
        img = img.resize((round(img.width * target / base), round(img.height * target / base)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def is_low_dpi(doc: pymupdf.Document, pages) -> bool:
    """Có trang nào là scan từ LOW_DPI trở xuống (GVR bán niên 2026: 72 dpi)."""
    return any((nd := native_dpi(doc, int(pg))) is not None and nd <= LOW_DPI for pg in pages)


STRIPS = ((0.0, 0.4), (0.3, 0.7), (0.6, 1.0))


def render_strips(doc: pymupdf.Document, page: int, rotate: int = 0, dpi: float = SHARP_DPI * 1.5) -> list[bytes]:
    """Trang (đã xoay đúng chiều) cắt thành các dải ngang chồng lên nhau, mỗi dải là một ảnh nét (render_sharp) ở độ
    phân giải cao hơn ảnh cả trang. Dùng khi đọc lại cả trang vẫn lặp một lỗi đọc nhầm."""
    return [render_sharp(doc, page, rotate, dpi, clip=strip) for strip in STRIPS]
