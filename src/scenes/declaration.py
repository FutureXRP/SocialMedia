"""declaration — one to three short lines fade+settle; one gets the thesis color."""

from . import ease_in, faded, settle_y, wrap_text

LINE_STAGGER = 0.9


def render(draw, t_local, duration, display, ctx):
    colors = ctx["brand"]["colors"]
    x0, y0, x1, y1 = ctx["content_box"]
    font = ctx["sans"](60, bold=True)

    lines = display.get("lines", [])[:3]
    emphasis = display.get("emphasis_index", 0)

    row_h = 80
    blocks = [wrap_text(s, font, x1 - x0 - 40) for s in lines]
    total_rows = sum(len(b) for b in blocks) + (len(blocks) - 1)
    y = (y0 + y1) // 2 - (total_rows * row_h) // 2

    for i, rows in enumerate(blocks):
        a = ease_in(t_local, 0.2 + i * LINE_STAGGER, 0.7)
        color = tuple(colors["green"]) if i == emphasis else tuple(colors["ink"])
        for row in rows:
            w = font.getbbox(row)[2]
            draw.text(((x0 + x1 - w) // 2, settle_y(y, a)), row, font=font,
                      fill=faded(ctx, color, a))
            y += row_h
        y += row_h  # blank row between lines
