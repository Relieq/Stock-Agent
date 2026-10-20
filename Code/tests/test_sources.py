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


def test_text_layer_tells_whether_a_page_is_upside_down():
    import pymupdf
    from services.extraction.sources import text_orientation
    doc = pymupdf.open()
    for rotate in (0, 180):
        page = doc.new_page()
        for i in range(12):
            page.insert_text((300, 100 + 40 * i) if rotate else (60, 100 + 40 * i),
                             "Tổng lợi nhuận kế toán trước thuế 11.030.887", rotate=rotate)
    doc.new_page()                                        # trang trắng (bản scan không có lớp chữ)
    assert [text_orientation(doc, p) for p in (1, 2, 3)] == [0, 180, None]


def test_flip_is_saved_only_when_confirmed(monkeypatch):
    # VPB quý 3/2026: trang 8 đứng thẳng theo lớp chữ, nên không được lưu hướng xoay 180 dù bản chép ngược ít lệch hơn
    from services.extraction import pipeline
    monkeypatch.setattr(pipeline, "text_orientation", lambda doc, page: 0)
    assert not pipeline._confirm_upside_down(None, None, 8, 0)
    assert pipeline._confirm_upside_down(None, None, 8, 180)
    monkeypatch.setattr(pipeline, "text_orientation", lambda doc, page: None)
    monkeypatch.setattr(pipeline, "render_page", lambda *a, **k: b"")

    class Client:
        def json_from_images(self, prompt, images, schema, name, **k):
            return {"upright": "B"}
    assert pipeline._confirm_upside_down(Client(), None, 86, 90)
