"""Scene template modules for the frame renderer.

Each scene module exposes:

    render(draw, t_local, duration, display, ctx)

which draws one frame's animated content onto an ImageDraw whose image was
copied from the segment's precomputed static background. Modules may also
expose build_background(display, ctx) -> PIL.Image to customize that static
background; the default is the shared panel produced by base_background().

ctx is a dict carrying: brand (brand.json), font (size, bold=False) -> font,
content_box (x0, y0, x1, y1) inside the safe zones, and per-frame globals
t_global / total_duration set by render.py.

v2 stub: a `broll` scene type that overlays a provided MP4 clip may be added
here later. Deterministic Pillow scenes only in v1.
"""

import math

# Registry maps scene contract keys to module names in this package.
SCENE_KEYS = [
    "hook_typewriter",
    "stat_counter",
    "declaration",
    "chart_sqrt",
    "chart_bar",
    "chart_line",
    "quote_card",
    "list_reveal",
    "cta_card",
]

CHART_DRAW_SECONDS = 2.4  # charts draw on over this long
CURSOR_HZ = 2             # typewriter cursor blink rate


def get_scene(key):
    import importlib
    if key not in SCENE_KEYS:
        raise KeyError(f"unknown scene template: {key}")
    return importlib.import_module(f"{__package__}.{key}")


def smoothstep(t):
    """Smoothstep easing on t clamped to [0, 1]. Nothing pops in."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def ease_in(t_local, start, dur):
    """Smoothstepped 0→1 progress for an element appearing at `start`."""
    if dur <= 0:
        return 1.0
    return smoothstep((t_local - start) / dur)


def mix(c_from, c_to, t):
    """Linear blend between two RGB tuples; used to fade text over the
    solid panel color (cheaper than per-frame RGBA compositing)."""
    t = max(0.0, min(1.0, t))
    return tuple(round(a + (b - a) * t) for a, b in zip(c_from, c_to))


def faded(ctx, color, alpha):
    return mix(ctx["brand"]["colors"]["panel"], color, alpha)


def settle_y(y, alpha, travel=26):
    """Fade+settle: element drifts up `travel` px as it fades in."""
    return y + round((1.0 - alpha) * travel)


def text_width(font, s):
    return font.getbbox(s)[2] if s else 0


def wrap_text(s, font, max_width):
    """Greedy word wrap by pixel width."""
    words, lines, cur = s.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if cur and text_width(font, trial) > max_width:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def fit_font(font, s, max_width, min_size=22):
    """Shrink a font until `s` fits max_width (long annotations must never
    bleed past the panel)."""
    from PIL import ImageFont
    size = getattr(font, "size", 40)
    while text_width(font, s) > max_width and size > min_size:
        size -= 2
        font = ImageFont.truetype(font.path, size)
    return font


def draw_centered(draw, ctx, y, s, font, color):
    x0, _, x1, _ = ctx["content_box"]
    font = fit_font(font, s, x1 - x0)
    w = text_width(font, s)
    draw.text(((x0 + x1 - w) // 2, y), s, font=font, fill=color)


def base_background(display, ctx):
    """Shared static background: bg fill, inset panel, faint grid."""
    from PIL import Image, ImageDraw

    brand = ctx["brand"]
    colors = brand["colors"]
    w, h = brand["canvas"]
    img = Image.new("RGB", (w, h), tuple(colors["bg"]))
    d = ImageDraw.Draw(img)

    x0, y0, x1, y1 = ctx["content_box"]
    d.rounded_rectangle([x0 - 24, y0 - 24, x1 + 24, y1 + 24], radius=28,
                        fill=tuple(colors["panel"]), outline=tuple(colors["grid"]),
                        width=2)
    # subtle dot grid — the full crosshatch read as "robotic"
    grid = tuple(colors["grid"])
    for gx in range(x0 + 30, x1 - 29, 90):
        for gy in range(y0 + 30, y1 - 29, 90):
            d.ellipse([gx - 2, gy - 2, gx + 2, gy + 2], fill=grid)
    # brand accent tab on the panel's top edge
    d.rounded_rectangle([x0 - 24, y0 - 24, x0 + 96, y0 - 16], radius=4,
                        fill=tuple(colors["green"]))
    return img


def cursor_on(t_local):
    return int(t_local * CURSOR_HZ * 2) % 2 == 0
