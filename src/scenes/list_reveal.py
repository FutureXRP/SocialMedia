"""list_reveal — a title, then 2–5 items reveal one by one."""

from . import ease_in, faded, settle_y, wrap_text, draw_centered

ITEM_STAGGER = 1.0


def render(draw, t_local, duration, display, ctx):
    colors = ctx["brand"]["colors"]
    x0, y0, x1, y1 = ctx["content_box"]

    title_font = ctx["font"](50, bold=True)
    item_font = ctx["font"](44)

    a_title = ease_in(t_local, 0.0, 0.6)
    draw_centered(draw, ctx, settle_y(y0 + 80, a_title), display.get("title", ""),
                  title_font, faded(ctx, tuple(colors["green"]), a_title))

    y = y0 + 260
    for i, item in enumerate(display.get("items", [])[:5]):
        a = ease_in(t_local, 0.8 + i * ITEM_STAGGER, 0.6)
        marker = faded(ctx, tuple(colors["amber"]), a)
        draw.text((x0, settle_y(y, a)), f"{i + 1:02d}", font=item_font, fill=marker)
        rows = wrap_text(item, item_font, x1 - x0 - 110)
        for row in rows:
            draw.text((x0 + 110, settle_y(y, a)), row, font=item_font,
                      fill=faded(ctx, tuple(colors["ink"]), a))
            y += 60
        y += 46
