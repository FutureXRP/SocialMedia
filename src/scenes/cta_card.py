"""cta_card — closing card: headline, site, mandatory research disclaimer."""

from . import ease_in, faded, settle_y, wrap_text, draw_centered, text_width

DISCLAIMER = "Research, not investment advice."


def render(draw, t_local, duration, display, ctx):
    colors = ctx["brand"]["colors"]
    x0, y0, x1, y1 = ctx["content_box"]

    head_font = ctx["font"](58, bold=True)
    site_font = ctx["font"](64, bold=True)
    disc_font = ctx["font"](36)

    mid = (y0 + y1) // 2
    a_head = ease_in(t_local, 0.2, 0.7)
    rows = wrap_text(display.get("headline", ""), head_font, x1 - x0)
    y = mid - 200 - (len(rows) - 1) * 40
    for row in rows:
        w = text_width(head_font, row)
        draw.text(((x0 + x1 - w) // 2, settle_y(y, a_head)), row,
                  font=head_font, fill=faded(ctx, tuple(colors["ink"]), a_head))
        y += 80

    a_site = ease_in(t_local, 1.0, 0.7)
    site = display.get("site", "xrpvaluation.info")
    draw_centered(draw, ctx, settle_y(mid + 40, a_site), site,
                  site_font, faded(ctx, tuple(colors["green"]), a_site))
    w = text_width(site_font, site)
    ux = (x0 + x1 - w) // 2
    draw.line([ux, mid + 120, ux + int(w * a_site), mid + 120],
              fill=faded(ctx, tuple(colors["green"]), a_site), width=4)

    # The disclaimer is a §14 requirement on every cta_card — always drawn.
    a_disc = ease_in(t_local, 1.6, 0.6)
    draw_centered(draw, ctx, mid + 240, DISCLAIMER,
                  disc_font, faded(ctx, tuple(colors["dim"]), max(a_disc, 0.001)))
    if t_local >= duration - 0.05:  # guarantee full opacity by scene end
        draw_centered(draw, ctx, mid + 240, DISCLAIMER, disc_font, tuple(colors["dim"]))
