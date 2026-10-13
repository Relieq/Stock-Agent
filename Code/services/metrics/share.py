"""Ảnh thẻ KQKD để chia sẻ (Facebook, Zalo): PNG 1200x630, vẽ bằng pymupdf từ thẻ đã kiểm chứng.

Chỉ vẽ số đã có trên thẻ (đã kiểm chứng hoặc đã duyệt tay), không thêm nhận định nào; chân ảnh ghi rõ là thông tin,
không phải khuyến nghị đầu tư. Phông DejaVu (gói fonts-dejavu-core trong image Docker) có đủ dấu tiếng Việt.
"""

from __future__ import annotations

import html
from pathlib import Path

import pymupdf

from services.metrics.card import Card, ty

WIDTH, HEIGHT = 1200, 630
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
SITE = "soi.rediov.com"

CSS = """
@font-face { font-family: dv; src: url(DejaVuSans.ttf); }
@font-face { font-family: dv; src: url(DejaVuSans-Bold.ttf); font-weight: bold; }
* { font-family: dv; color: #1d2329; }
.brand { font-size: 22px; color: #6b7480; }
.title { font-size: 54px; font-weight: bold; margin: 4px 0 0; }
.name { font-size: 22px; color: #6b7480; margin: 0 0 18px; }
.m { font-size: 26px; margin: 10px 0 0; }
.v { font-size: 40px; font-weight: bold; }
.c { font-size: 26px; color: #4a525c; }
.flags { font-size: 22px; color: #8a5a00; margin-top: 18px; }
.foot { font-size: 17px; color: #6b7480; }
"""


def _metric(card: Card, key: str):
    return next((m for m in card.metrics if m.key == key), None)


def card_png(card: Card, name: str) -> bytes:
    period = f"{card.period}/{card.year}"
    np = _metric(card, "npat_parent")
    second = _metric(card, "revenue") or _metric(card, "toi")
    rows = []
    for m in (np, second):
        if m is None or m.q_cur.value is None:
            continue
        rows.append(f'<p class="m">{html.escape(m.name)}, quý {card.period[1:]}</p>'
                    f'<p><span class="v">{ty(m.q_cur.value)}</span> '
                    f'<span class="c">{html.escape(m.q_change or "")}</span></p>')
    flags = ""
    if card.flags:
        flags = '<p class="flags">Cần xem kỹ: ' + html.escape("; ".join(f.title for f in card.flags[:3])) + "</p>"
    body = (f'<p class="brand">SOI · Thẻ KQKD đã kiểm chứng</p>'
            f'<p class="title">{html.escape(card.ticker)} · {period}</p>'
            f'<p class="name">{html.escape(name)}</p>{"".join(rows)}{flags}')
    foot = (f'<p class="foot">Số đọc từ BCTC đã công bố, kiểm chứng bằng ràng buộc kế toán; mỗi số mở được trang gốc tại '
            f'{SITE}. Thông tin, không phải khuyến nghị đầu tư.</p>')

    doc = pymupdf.open()
    page = doc.new_page(width=WIDTH, height=HEIGHT)
    page.draw_rect(page.rect, color=None, fill=(1, 1, 1))
    page.draw_rect(pymupdf.Rect(0, 0, 12, HEIGHT), color=None, fill=(0.07, 0.36, 0.68))
    archive = pymupdf.Archive(str(FONT_DIR))
    page.insert_htmlbox(pymupdf.Rect(56, 40, WIDTH - 56, HEIGHT - 90), body, css=CSS, archive=archive)
    page.insert_htmlbox(pymupdf.Rect(56, HEIGHT - 80, WIDTH - 56, HEIGHT - 20), foot, css=CSS, archive=archive)
    return page.get_pixmap(matrix=pymupdf.Matrix(1, 1)).tobytes("png")
