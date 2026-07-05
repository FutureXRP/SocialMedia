"""Frame renderer.

Renders 1080×1920 @ 30fps frames to a directory. Per segment, the scene's
static background is computed once; each frame copies it and draws only
animated elements plus the dynamic chrome (progress bar, blinking status dot,
active caption phrase). Every frame carries the header chrome, the
AI-GENERATED label (TikTok AI-content disclosure — always on,
non-configurable), the progress bar, and the caption panel.
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from captions import event_at_time
from scenes import get_scene, base_background, smoothstep, text_width

WORDS_PER_MINUTE = 150
MIN_SEGMENT_SECONDS = 2.5

_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_MONO_FILES = {
    False: _FONT_DIR / "DejaVuSansMono.ttf",
    True: _FONT_DIR / "DejaVuSansMono-Bold.ttf",
}
_SANS_FILES = {
    False: _FONT_DIR / "DejaVuSans.ttf",
    True: _FONT_DIR / "DejaVuSans-Bold.ttf",
}


def make_font_loader(files):
    cache = {}

    def font(size, bold=False):
        key = (size, bold)
        if key not in cache:
            cache[key] = ImageFont.truetype(str(files[bold]), size)
        return cache[key]

    return font


def build_ctx(brand, series="OBSERVATORY"):
    w, h = brand["canvas"]
    sz = brand["safe_zones"]
    caption_panel_h = 200
    ctx = {
        "brand": brand,
        # mono is the data/chrome voice; sans is the narrative voice —
        # all-mono everywhere read as "robotic" in review
        "font": make_font_loader(_MONO_FILES),
        "sans": make_font_loader(_SANS_FILES),
        "series": series,
        # content sits inside safe zones, above the caption panel
        "content_box": (sz["sides_px"], sz["top_px"] + 60,
                        w - sz["sides_px"], h - sz["bottom_px"] - caption_panel_h - 40),
        "caption_box": (sz["sides_px"], h - sz["bottom_px"] - caption_panel_h,
                        w - sz["sides_px"], h - sz["bottom_px"]),
    }
    return ctx


def estimate_segment_times(segments):
    """No-voice mode: durations from word count at ~150 wpm."""
    times, t = [], 0.0
    for seg in segments:
        words = len(seg.get("voiceover", "").split())
        dur = max(MIN_SEGMENT_SECONDS, words / WORDS_PER_MINUTE * 60.0)
        times.append((t, t + dur))
        t += dur
    return times


def draw_static_chrome(img, ctx):
    """Chrome that never changes: header bar, labels, caption panel frame."""
    brand = ctx["brand"]
    colors = brand["colors"]
    w, _h = brand["canvas"]
    d = ImageDraw.Draw(img)
    font = ctx["font"]

    d.rectangle([0, 90, w, 190], fill=tuple(colors["panel"]))
    d.line([0, 190, w, 190], fill=tuple(colors["grid"]), width=2)
    d.text((110, 112), brand["chrome"]["header"], font=font(30, bold=True),
           fill=tuple(colors["ink"]))
    sub = brand["chrome"]["subheader_pattern"].replace("{SERIES}", ctx["series"])
    d.text((110, 152), sub, font=font(24), fill=tuple(colors["dim"]))

    ai = brand["chrome"]["ai_label"]
    ai_font = font(24, bold=True)
    aw = text_width(ai_font, ai)
    d.rectangle([w - aw - 56, 106, w - 24, 150], outline=tuple(colors["amber"]), width=2)
    d.text((w - aw - 40, 116), ai, font=ai_font, fill=tuple(colors["amber"]))

    # captions draw boxless (karaoke style) — no panel here
    return img


def draw_karaoke_caption(d, ctx, event, t):
    """TikTok-native captions: big, boxless, outlined, with the word being
    spoken highlighted — driven by the character-level alignment."""
    colors = ctx["brand"]["colors"]
    cx0, cy0, cx1, cy1 = ctx["caption_box"]
    font = ctx["sans"](58, bold=True)
    words = event.get("words") or [{"text": w, "start": event["start"]}
                                   for w in event["text"].split()]

    space = text_width(font, " ")
    max_w = cx1 - cx0
    lines, cur, cur_w = [], [], 0
    for wd in words:
        ww = text_width(font, wd["text"])
        if cur and cur_w + space + ww > max_w:
            lines.append(cur)
            cur, cur_w = [wd], ww
        else:
            cur.append(wd)
            cur_w += (space if len(cur) > 1 else 0) + ww
    if cur:
        lines.append(cur)
    lines = lines[:3]

    active = -1
    for i, wd in enumerate(words):
        if wd["start"] <= t:
            active = i
    row_h = 76
    y = (cy0 + cy1) // 2 - (len(lines) * row_h) // 2
    outline = tuple(colors["bg"])
    idx = 0
    for line in lines:
        lw = sum(text_width(font, wd["text"]) for wd in line) \
            + space * (len(line) - 1)
        x = (cx0 + cx1 - lw) // 2
        for wd in line:
            color = tuple(colors["green"]) if idx == active else tuple(colors["ink"])
            d.text((x, y), wd["text"], font=font, fill=color,
                   stroke_width=6, stroke_fill=outline)
            x += text_width(font, wd["text"]) + space
            idx += 1
        y += row_h


def draw_dynamic_chrome(d, ctx, t_global, total_duration, caption_events,
                        seg_i=0, n_segments=1):
    brand = ctx["brand"]
    colors = brand["colors"]
    w, h = brand["canvas"]

    # status dot blinks at 1Hz next to the header
    if int(t_global * 2) % 2 == 0:
        d.ellipse([56, 126, 84, 154], fill=tuple(colors["green"]))
    else:
        d.ellipse([56, 126, 84, 154], outline=tuple(colors["green"]), width=3)

    # segment ticks under the header: where you are in the video
    if n_segments > 1:
        tick_w = max(12, min(64, (w - 220) // n_segments - 10))
        for i in range(n_segments):
            x = 110 + i * (tick_w + 10)
            color = tuple(colors["green"]) if i <= seg_i else tuple(colors["grid"])
            d.rectangle([x, 206, x + tick_w, 212], fill=color)

    if brand["chrome"].get("progress_bar", True) and total_duration > 0:
        frac = min(1.0, t_global / total_duration)
        d.rectangle([0, h - 14, w, h - 6], fill=tuple(colors["grid"]))
        d.rectangle([0, h - 14, int(w * frac), h - 6], fill=tuple(colors["green"]))
        tip = int(w * frac)
        d.ellipse([tip - 8, h - 18, tip + 8, h - 2], fill=tuple(colors["amber"]))

    event = event_at_time(caption_events, t_global)
    if event:
        draw_karaoke_caption(d, ctx, event, t_global)


def render_frames(script, brand, segment_times, caption_events, frames_dir,
                  frame_format="png", jpeg_quality=92, series="OBSERVATORY"):
    """Render every frame. Returns (frame_count, total_duration)."""
    frames_dir = Path(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    ctx = build_ctx(brand, series=series)
    fps = brand["fps"]

    segments = script["segments"]
    total_duration = segment_times[-1][1]
    total_frames = int(round(total_duration * fps))

    # precompute one static background (scene bg + static chrome) per segment
    backgrounds = []
    for seg in segments:
        mod = get_scene(seg["scene"])
        builder = getattr(mod, "build_background", None) or base_background
        bg = builder(seg.get("display", {}), ctx)
        backgrounds.append(draw_static_chrome(bg, ctx))

    def compose(i, t_local):
        img = backgrounds[i].copy()
        seg = segments[i]
        start, end = segment_times[i]
        get_scene(seg["scene"]).render(ImageDraw.Draw(img), t_local,
                                       end - start, seg.get("display", {}), ctx)
        return img

    TRANSITION = 0.3  # cross-fade between scenes; cuts feel less slideshow
    ext = "jpg" if frame_format == "jpeg" else "png"
    seg_i = 0
    for f in range(total_frames):
        t = f / fps
        while seg_i + 1 < len(segments) and t >= segment_times[seg_i][1]:
            seg_i += 1
        start, _end = segment_times[seg_i]

        img = compose(seg_i, t - start)
        if seg_i > 0 and t - start < TRANSITION:
            prev_start, prev_end = segment_times[seg_i - 1]
            prev = compose(seg_i - 1, prev_end - prev_start)
            img = Image.blend(prev, img, smoothstep((t - start) / TRANSITION))

        draw_dynamic_chrome(ImageDraw.Draw(img), ctx, t, total_duration,
                            caption_events, seg_i, len(segments))

        path = frames_dir / f"f{f:06d}.{ext}"
        if ext == "jpg":
            img.save(path, quality=jpeg_quality)
        else:
            img.save(path)
    return total_frames, total_duration


def load_json(path):
    return json.loads(Path(path).read_text())
