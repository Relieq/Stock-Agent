"""Biểu đồ SVG cho trang báo cáo (dùng chung web và PDF): thanh ngang theo mã, hai thanh kỳ này / cùng kỳ, hoặc đường
theo quý (xu hướng, mỗi mã một đường). Số lấy từ đặc tả do code dựng (facts.chart_specs, facts.trend_charts), không qua
mô hình."""

from __future__ import annotations

from html import escape

W, LABEL, ROW, TOP = 640, 150, 26, 34
# Đơn vị tính theo phần trăm: in một chữ số thập phân kèm hậu tố; các đơn vị còn lại in số nguyên
PERCENT_SUFFIX = {"%": "%", "điểm %": " điểm %"}


def _num(v: float, unit: str) -> str:
    s = f"{abs(v):,.1f}" if unit in PERCENT_SUFFIX else f"{abs(v):,.0f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−" if v < 0 else "") + s + PERCENT_SUFFIX.get(unit, "")


LINE_H, LINE_LEFT, LINE_RIGHT, LINE_TOP, LINE_BOTTOM, LINE_PAD = 240, 70, 20, 44, 34, 36
PALETTE = ("#2b6cb0", "#dd6b20", "#2f855a", "#805ad5", "#c53030", "#718096")
STYLE = ("<style>.chart text{font:12px sans-serif;fill:#222}.chart .t{font-weight:600}.chart .cur{fill:#2b6cb0}"
         ".chart .prev{fill:#a0aec0}.chart rect.hl{fill:#dd6b20}.chart text.hl{font-weight:700}"
         ".chart .axis{stroke:#888}.chart .grid{stroke:#e2e8f0}.chart .v{fill:#444}</style></svg>")


def line_svg(spec: dict) -> str:
    """Đường theo quý: trục ngang là các quý, mỗi mã một đường; quý chưa có số thì đứt đường. Một mã thì ghi số ở từng
    điểm; nhiều mã thì có chú thích tên mã."""
    labels, series = spec["labels"], spec["series"]
    values = [v for s in series for v in s["values"] if v is not None] or [0.0]
    lo, hi = min(0.0, min(values)), max(0.0, max(values))
    span = (hi - lo) or 1.0
    plot_w, plot_h = W - LINE_LEFT - LINE_RIGHT - 2 * LINE_PAD, LINE_H - LINE_TOP - LINE_BOTTOM
    legend = 20 if len(series) > 1 else 0
    h = LINE_H + legend
    step = plot_w / max(len(labels) - 1, 1)
    x = lambda i: LINE_LEFT + LINE_PAD + (i * step if len(labels) > 1 else plot_w / 2)    # noqa: E731
    y = lambda v: LINE_TOP + (hi - v) / span * plot_h                                     # noqa: E731
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {h}" width="100%" role="img" '
           f'aria-label="{escape(spec["title"])}" class="chart">',
           f'<text x="0" y="16" class="t">{escape(spec["title"])} ({escape(spec["unit"])})</text>']
    for v in sorted({lo, hi, 0.0}):
        out.append(f'<line x1="{LINE_LEFT}" y1="{y(v):.1f}" x2="{W - LINE_RIGHT}" y2="{y(v):.1f}" '
                   f'class="{"axis" if v == 0 else "grid"}"/>'
                   f'<text x="{LINE_LEFT - 6}" y="{y(v) + 4:.1f}" text-anchor="end" class="v">{_num(v, spec["unit"])}'
                   f'</text>')
    for i, lab in enumerate(labels):
        out.append(f'<text x="{x(i):.1f}" y="{LINE_H - LINE_BOTTOM + 18}" text-anchor="middle">{escape(lab)}</text>')
    for k, s in enumerate(series):
        color = PALETTE[k % len(PALETTE)]
        pts = [(x(i), y(v), v) for i, v in enumerate(s["values"]) if v is not None]
        segs, cur = [], []
        for i, v in enumerate(s["values"]):
            if v is None:
                if cur:
                    segs.append(cur)
                cur = []
            else:
                cur.append(f"{x(i):.1f},{y(v):.1f}")
        if cur:
            segs.append(cur)
        for seg in segs:
            out.append(f'<polyline points="{" ".join(seg)}" fill="none" stroke="{color}" stroke-width="2"/>')
        for px, py, v in pts:
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="{color}"/>')
            if len(series) == 1:
                out.append(f'<text x="{px:.1f}" y="{py - 8:.1f}" text-anchor="middle" class="v">'
                           f'{_num(v, spec["unit"])}</text>')
        if legend:
            lx = LINE_LEFT + k * 90
            out.append(f'<rect x="{lx}" y="{h - 14}" width="10" height="10" fill="{color}"/>'
                       f'<text x="{lx + 14}" y="{h - 5}">{escape(s["name"])}</text>')
    out.append(STYLE)
    return "".join(out)


def svg(spec: dict) -> str:
    if spec["type"] == "line":
        return line_svg(spec)
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
    out.append(STYLE)
    return "".join(out)
