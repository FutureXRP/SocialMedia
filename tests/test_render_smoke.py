"""Render smoke test: every scene template draws a frame without error and
frames are non-blank, correctly sized, and carry the chrome."""

import json
from pathlib import Path

from PIL import Image, ImageDraw

import render
from captions import build_caption_events_estimated
from scenes import SCENE_KEYS, base_background, get_scene

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = json.loads((ROOT / "tests" / "fixture_script.json").read_text())
BRAND = json.loads((ROOT / "config" / "brand.json").read_text())


def fixture_display(scene_key):
    for seg in FIXTURE["segments"]:
        if seg["scene"] == scene_key:
            return seg["display"]
    raise AssertionError(f"fixture missing scene {scene_key}")


def test_fixture_covers_all_scene_templates():
    covered = {seg["scene"] for seg in FIXTURE["segments"]}
    assert covered == set(SCENE_KEYS)


def test_every_scene_draws_at_multiple_timepoints():
    ctx = render.build_ctx(BRAND)
    for key in SCENE_KEYS:
        display = fixture_display(key)
        img = base_background(display, ctx)
        for t in (0.0, 0.5, 2.0, 4.9):
            frame = img.copy()
            get_scene(key).render(ImageDraw.Draw(frame), t, 5.0, display, ctx)
        assert frame.size == tuple(BRAND["canvas"])


def test_rendered_frame_has_chrome_and_content(tmp_path):
    script = {"segments": FIXTURE["segments"][:1]}
    times = render.estimate_segment_times(script["segments"])
    events = build_caption_events_estimated(script["segments"], times)
    n, duration = render.render_frames(script, BRAND, times, events, tmp_path)
    assert n == int(round(duration * BRAND["fps"]))

    frame = Image.open(tmp_path / "f000030.png")  # 1 second in
    assert frame.size == tuple(BRAND["canvas"])
    colors = frame.getcolors(maxcolors=1_000_000)
    assert len(colors) > 10, "frame appears blank"
    # AI-GENERATED label chrome: amber pixels present near top-right
    amber = tuple(BRAND["colors"]["amber"])
    top_right = frame.crop((frame.width - 300, 90, frame.width, 190))
    assert any(p == amber for p in top_right.getdata()), "AI label missing"


def test_estimate_segment_times_150wpm():
    segs = [{"voiceover": " ".join(["word"] * 150)}]
    times = render.estimate_segment_times(segs)
    assert abs(times[0][1] - 60.0) < 1e-6
