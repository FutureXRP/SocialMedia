"""chart_line — a polyline through 4–10 normalized points draws on."""

from . import CHART_DRAW_SECONDS, ease_in, faded, settle_y, draw_centered


def render(draw, t_local, duration, display, ctx):
    colors = ctx["brand"]["colors"]
    x0, y0, x1, y1 = ctx["content_box"]

    title_font = ctx["font"](46, bold=True)
    draw_centered(draw, ctx, y0 + 60, display.get("title", ""),
                  title_font, faded(ctx, tuple(colors["ink"]), ease_in(t_local, 0.0, 0.5)))

    points = display.get("points", [])[:10]
    if len(points) < 2:
        return

    cx0, cy0 = x0 + 40, y0 + 220
    cx1, cy1 = x1 - 40, y0 + 760
    axis = tuple(colors["dim"])
    draw.line([cx0, cy1, cx1, cy1], fill=axis, width=3)
    draw.line([cx0, cy0, cx0, cy1], fill=axis, width=3)

    coords = []
    for i, p in enumerate(points):
        f = i / (len(points) - 1)
        norm = max(0.0, min(1.0, float(p.get("value_norm", 0))))
        coords.append((cx0 + f * (cx1 - cx0), cy1 - norm * (cy1 - cy0 - 20)))

    progress = ease_in(t_local, 0.4, CHART_DRAW_SECONDS)
    total = len(coords) - 1
    reach = progress * total
    drawn = []
    for i in range(len(coords) - 1):
        if reach <= i:
            break
        seg_t = min(1.0, reach - i)
        ax, ay = coords[i]
        bx, by = coords[i + 1]
        drawn.append((ax, ay))
        drawn.append((ax + (bx - ax) * seg_t, ay + (by - ay) * seg_t))
    if len(drawn) >= 2:
        draw.line(drawn, fill=tuple(colors["green"]), width=6)

    label_font = ctx["font"](28)
    for i, ((px, py), p) in enumerate(zip(coords, points)):
        if reach >= i:
            draw.ellipse([px - 8, py - 8, px + 8, py + 8], fill=tuple(colors["amber"]))
            label = p.get("label", "")
            if label and (i % max(1, len(points) // 5) == 0 or i == len(points) - 1):
                w = label_font.getbbox(label)[2]
                draw.text((min(max(px - w // 2, cx0), cx1 - w), cy1 + 16),
                          label, font=label_font, fill=axis)

    a = ease_in(t_local, CHART_DRAW_SECONDS + 0.3, 0.6)
    ann_font = ctx["font"](42, bold=True)
    draw_centered(draw, ctx, settle_y(cy1 + 90, a), display.get("annotation", ""),
                  ann_font, faded(ctx, tuple(colors["amber"]), a))
