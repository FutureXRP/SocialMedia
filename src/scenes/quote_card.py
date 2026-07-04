"""quote_card — a short attributed quote fades in between rule lines."""

from . import ease_in, faded, settle_y, wrap_text, draw_centered, text_width


def render(draw, t_local, duration, display, ctx):
    colors = ctx["brand"]["colors"]
    x0, y0, x1, y1 = ctx["content_box"]

    quote_font = ctx["sans"](56, bold=True)
    attr_font = ctx["sans"](38)

    rows = wrap_text('“' + display.get("quote", "") + '”', quote_font, x1 - x0 - 80)
    row_h = 74
    y = (y0 + y1) // 2 - (len(rows) * row_h) // 2 - 40

    a_rule = ease_in(t_local, 0.0, 0.6)
    rule = faded(ctx, tuple(colors["dim"]), a_rule)
    draw.line([x0 + 60, y - 60, x1 - 60, y - 60], fill=rule, width=2)

    a = ease_in(t_local, 0.3, 0.8)
    for i, row in enumerate(rows):
        w = text_width(quote_font, row)
        draw.text(((x0 + x1 - w) // 2, settle_y(y + i * row_h, a)), row,
                  font=quote_font, fill=faded(ctx, tuple(colors["ink"]), a))

    bottom = y + len(rows) * row_h + 40
    draw.line([x0 + 60, bottom + 40, x1 - 60, bottom + 40], fill=rule, width=2)

    a_attr = ease_in(t_local, 1.0, 0.6)
    draw_centered(draw, ctx, settle_y(bottom + 90, a_attr),
                  "— " + display.get("attribution", ""),
                  attr_font, faded(ctx, tuple(colors["amber"]), a_attr))
