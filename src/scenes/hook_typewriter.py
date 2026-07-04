"""hook_typewriter — the opening line types itself out, blinking cursor."""

from . import cursor_on, faded, wrap_text

CHARS_PER_SECOND = 24


def render(draw, t_local, duration, display, ctx):
    colors = ctx["brand"]["colors"]
    x0, y0, x1, y1 = ctx["content_box"]
    font = ctx["font"](64, bold=True)

    line = display.get("line", "")
    shown = line[: int(t_local * CHARS_PER_SECOND)]
    done = len(shown) >= len(line)

    rows = wrap_text(shown, font, x1 - x0)
    line_h = 84
    total_lines = len(wrap_text(line, font, x1 - x0)) or 1
    y = (y0 + y1) // 2 - (total_lines * line_h) // 2

    ink = tuple(colors["ink"])
    last_x = x0
    for i, row in enumerate(rows):
        draw.text((x0, y + i * line_h), row, font=font, fill=ink)
        if i == len(rows) - 1:
            last_x = x0 + font.getbbox(row)[2]

    # Blinking cursor rides the last glyph; solid while still typing.
    if (not done) or cursor_on(t_local):
        cy = y + (max(len(rows), 1) - 1) * line_h
        draw.rectangle([last_x + 10, cy + 8, last_x + 42, cy + 68],
                       fill=faded(ctx, tuple(colors["green"]), 1.0))
