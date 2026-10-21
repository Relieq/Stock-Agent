"""Biểu đồ SVG cho trang báo cáo (dùng chung web và PDF): thanh ngang theo mã, hoặc hai thanh kỳ này / cùng kỳ. Số lấy
từ đặc tả do code dựng (facts.chart_specs), không qua mô hình."""

from __future__ import annotations

from html import escape

W, LABEL, ROW, TOP = 640, 150, 26, 34
# Đơn vị tính theo phần trăm: in một chữ số thập phân kèm hậu tố; các đơn vị còn lại in số nguyên
PERCENT_SUFFIX = {"%": "%", "điểm %": " điểm %"}


def _num(v: float, unit: str) -> str:
    s = f"{abs(v):,.1f}" if unit in PERCENT_SUFFIX else f"{abs(v):,.0f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−" if v < 0 else "") + s + PERCENT_SUFFIX.get(unit, "")


def svg(spec: dict) -> str:
    rows = spec["items"]
    paired = spec["type"] == "paired"
    values = [v for r in rows for v in r[1:] if v is not None] or [0.0]
    lo, hi = min(0.0, min(values)), max(0.0, max(values))
    span = (hi - lo) or 1.0
    plot = W - LABEL - 80
    zero = LABEL + (0 - lo) / span * plot
    step = ROW * (2 if paired else 1) + 6
    h = TOP + step * len(rows) + (22 if paired else 6)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {h}" width="100%" role="img" '
           f'aria-label="{escape(spec["title"])}" class="chart">',
           f'<text x="0" y="16" class="t">{escape(spec["title"])} ({escape(spec["unit"])})</text>',
           f'<line x1="{zero:.1f}" y1="{TOP - 6}" x2="{zero:.1f}" y2="{h - (22 if paired else 6)}" class="axis"/>']
    for i, r in enumerate(rows):
        y = TOP + i * step
        hl = r[0] in spec.get("highlight", [])
        label_class = ' class="hl"' if hl else ""
        out.append(f'<text x="{LABEL - 8}" y="{y + 15}" text-anchor="end"{label_class}>'
                   f'{escape(str(r[0]))}</text>')
        for j, v in enumerate(r[1:]):
            if v is None:
                continue
            x = LABEL + (min(v, 0) - lo) / span * plot
            w = abs(v) / span * plot
            by = y + j * ROW
            kind = ("prev" if j else "cur") + (" hl" if hl else "")
            out.append(f'<rect x="{x:.1f}" y="{by + 3}" width="{max(w, 1):.1f}" height="{ROW - 8}" class="{kind}"/>')
            # nhãn của thanh âm đặt bên phải trục (không đè lên tên mã ở bên trái)
            tx = x + w + 4 if v >= 0 else zero + 4
            anchor = "start"
            out.append(f'<text x="{tx:.1f}" y="{by + 16}" text-anchor="{anchor}" class="v">{_num(v, spec["unit"])}</text>')
    if paired:
        ly = h - 8
        out.append(f'<rect x="{LABEL}" y="{ly - 9}" width="10" height="10" class="cur"/>'
                   f'<text x="{LABEL + 14}" y="{ly}">Kỳ này</text>'
                   f'<rect x="{LABEL + 80}" y="{ly - 9}" width="10" height="10" class="prev"/>'
                   f'<text x="{LABEL + 94}" y="{ly}">Cùng kỳ</text>')
    out.append("<style>.chart text{font:12px sans-serif;fill:#222}.chart .t{font-weight:600}.chart .cur{fill:#2b6cb0}"
               ".chart .prev{fill:#a0aec0}.chart rect.hl{fill:#dd6b20}.chart text.hl{font-weight:700}"
               ".chart .axis{stroke:#888}.chart .v{fill:#444}</style></svg>")
    return "".join(out)
