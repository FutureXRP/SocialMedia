"""chart_sqrt — the square-root impact curve draws on, annotated."""

import math

from . import CHART_DRAW_SECONDS, ease_in, faded, settle_y, draw_centered


def render(draw, t_local, duration, display, ctx):
    colors = ctx["brand"]["colors"]
    x0, y0, x1, y1 = ctx["content_box"]

    cx0, cy0 = x0 + 40, y0 + 180
    cx1, cy1 = x1 - 40, y0 + 720
    axis = tuple(colors["dim"])
    draw.line([cx0, cy1, cx1, cy1], fill=axis, width=3)
    draw.line([cx0, cy0, cx0, cy1], fill=axis, width=3)

    progress = ease_in(t_local, 0.3, CHART_DRAW_SECONDS)
    n = max(2, int(240 * progress))
    pts = []
    for i in range(n):
        f = (i / 239)
        px = cx0 + f * (cx1 - cx0)
        py = cy1 - math.sqrt(f) * (cy1 - cy0 - 20)
        pts.append((px, py))
    if len(pts) >= 2:
        draw.line(pts, fill=tuple(colors["green"]), width=6)
        # tracer dot at the pen tip while drawing
        if progress < 1.0:
            px, py = pts[-1]
            draw.ellipse([px - 10, py - 10, px + 10, py + 10], fill=tuple(colors["amber"]))

    a = ease_in(t_local, CHART_DRAW_SECONDS * 0.6, 0.7)
    ann_font = ctx["sans"](46, bold=True)
    draw_centered(draw, ctx, settle_y(cy1 + 80, a), display.get("annotation", ""),
                  ann_font, faded(ctx, tuple(colors["amber"]), a))

    sub_font = ctx["sans"](36)
    for i, sub in enumerate(display.get("sub_lines", [])[:2]):
        sa = ease_in(t_local, CHART_DRAW_SECONDS * 0.6 + 0.5 + i * 0.5, 0.6)
        draw_centered(draw, ctx, settle_y(cy1 + 180 + i * 62, sa), sub,
                      sub_font, faded(ctx, tuple(colors["ink"]), sa))
