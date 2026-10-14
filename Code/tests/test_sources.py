import io
import math

import pymupdf
from PIL import Image

from services.extraction.sources import is_low_dpi, native_dpi, render_sharp, render_strips


def _scan_pdf(dpi: int) -> pymupdf.Document:
    """Một trang A4 chỉ gồm ảnh scan ở độ phân giải `dpi`."""
    w_pt, h_pt = 595, 842
    img = Image.new("L", (round(w_pt * dpi / 72), round(h_pt * dpi / 72)), 255)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    doc = pymupdf.open()
    page = doc.new_page(width=w_pt, height=h_pt)
    page.insert_image(page.rect, stream=buf.getvalue())
    return doc


def _size(png: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(png)).size


def test_low_dpi_scan_is_upscaled_at_most_three_times():
    # GVR bán niên 2026: ảnh scan 72 dpi -> vẽ 216 dpi (gấp 3), không phải 288
    doc = _scan_pdf(72)
    assert round(native_dpi(doc, 1)) == 72 and is_low_dpi(doc, [1])
    w, h = _size(render_sharp(doc, 1))
    assert abs(w - 595 * 3) <= 2 and abs(h - 842 * 3) <= 2


def test_sharp_page_fits_original_detail_patch_budget():
    doc = pymupdf.open()
    doc.new_page(width=595, height=842).insert_text((72, 72), "1.234.567")
    assert native_dpi(doc, 1) is None and not is_low_dpi(doc, [1])
    w, h = _size(render_sharp(doc, 1))
    assert math.ceil(w / 32) * math.ceil(h / 32) <= 10000
    assert w >= 595 * 288 / 72 * 0.98          # trang vẽ bằng chữ: đủ 288 dpi vì vẫn vừa giới hạn


def test_strips_are_larger_than_whole_page_and_rotation_is_applied():
    doc = _scan_pdf(150)
    full_w, _ = _size(render_sharp(doc, 1))
    strips = render_strips(doc, 1)
    assert len(strips) == 3 and all(_size(s)[0] > full_w for s in strips)
    w, h = _size(render_sharp(doc, 1, rotate=90))
    assert w > h                                # trang dọc xoay 90 độ thành ảnh ngang
