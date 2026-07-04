"""stat_counter — one big number counts up; supporting beats fade in below."""

import re

from . import ease_in, faded, settle_y, draw_centered

COUNT_SECONDS = 1.6


def _animated_value(value, progress):
    """Scale the first numeric run in `value` from 0 to its final figure,
    preserving surrounding text, digit grouping and decimal places."""
    m = re.search(r"[\d,]*\d(?:\.\d+)?", value)
    if not m or progress >= 1.0:
        return value
    raw = m.group(0)
    target = float(raw.replace(",", ""))
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    shown = target * progress
    text = f"{shown:,.{decimals}f}" if "," in raw or decimals else f"{shown:,.0f}".replace(",", "")
    return value[: m.start()] + text + value[m.end():]


def render(draw, t_local, duration, display, ctx):
    colors = ctx["brand"]["colors"]
    x0, y0, x1, y1 = ctx["content_box"]

    label_font = ctx["font"](40)
    value_font = ctx["font"](120, bold=True)
    beat_font = ctx["font"](42)

    a_label = ease_in(t_local, 0.0, 0.5)
    draw_centered(draw, ctx, settle_y(y0 + 120, a_label), display.get("label", "").upper(),
                  label_font, faded(ctx, tuple(colors["dim"]), a_label))

    progress = ease_in(t_local, 0.3, COUNT_SECONDS)
    value = _animated_value(display.get("value", ""), progress)
    draw_centered(draw, ctx, y0 + 260, value, value_font,
                  faded(ctx, tuple(colors["amber"]), ease_in(t_local, 0.15, 0.4)))

    for i, beat in enumerate(display.get("beats", [])[:3]):
        a = ease_in(t_local, 2.0 + i * 0.8, 0.6)
        draw_centered(draw, ctx, settle_y(y0 + 520 + i * 90, a), beat,
                      beat_font, faded(ctx, tuple(colors["ink"]), a))
