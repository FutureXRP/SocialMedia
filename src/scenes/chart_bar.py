"""chart_bar — 2–5 horizontal bars grow to their normalized lengths."""

from . import CHART_DRAW_SECONDS, ease_in, faded, draw_centered, text_width


def render(draw, t_local, duration, display, ctx):
    colors = ctx["brand"]["colors"]
    x0, y0, x1, y1 = ctx["content_box"]

    title_font = ctx["font"](46, bold=True)
    a_title = ease_in(t_local, 0.0, 0.5)
    draw_centered(draw, ctx, y0 + 60, display.get("title", ""),
                  title_font, faded(ctx, tuple(colors["ink"]), a_title))

    bars = display.get("bars", [])[:5]
    label_font = ctx["font"](36)
    value_font = ctx["font"](36, bold=True)
    bar_h, gap = 64, 130
    top = y0 + 220
    max_w = (x1 - x0) - 40

    for i, bar in enumerate(bars):
        start = 0.5 + i * 0.35
        grow = ease_in(t_local, start, CHART_DRAW_SECONDS * 0.6)
        by = top + i * (bar_h + gap)
        draw.text((x0, by - 48), bar.get("label", ""), font=label_font,
                  fill=faded(ctx, tuple(colors["dim"]), ease_in(t_local, start, 0.4)))
        norm = max(0.0, min(1.0, float(bar.get("value_norm", 0))))
        w = int(max_w * norm * grow)
        draw.rectangle([x0, by, x0 + max(w, 4), by + bar_h], fill=tuple(colors["green"]))
        if grow >= 1.0:
            vd = bar.get("value_display", "")
            vx = min(x0 + w + 18, x1 - text_width(value_font, vd))
            draw.text((vx, by + 12), vd, font=value_font, fill=tuple(colors["amber"]))
