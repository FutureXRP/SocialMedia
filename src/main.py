"""Orchestrator — entry point for the daily video pipeline.

Nightly run:      python src/main.py
Fixture render:   python src/main.py --fixture tests/fixture_script.json --no-voice

On failure at any stage, output/failure.json records {stage, error} so the
workflow can open a GitHub Issue — nothing fails silently. The QA firewall
cannot be bypassed: there is no --skip-qa and never will be.
"""

import argparse
import json
import random
import sys
import time
import traceback
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

OUTPUT_DIR = ROOT / "output"

CURRENT_STAGE = "startup"  # read by main() when a stage raises

SERIES_BY_FORMAT = {
    "field_note_explainer": "FIELD NOTES",
    "one_chart_one_claim": "OBSERVATORY",
    "term_of_the_day": "TERM OF THE DAY",
    "terminal_reading": "SETTLEMENT TERMINAL",
}


def load_config(name):
    return json.loads((ROOT / "config" / name).read_text())


def pick_format(formats_cfg, topic, run_date, override=None, duration_target=None):
    formats = formats_cfg["formats"]
    if override:
        if override not in formats:
            raise ValueError(f"unknown format: {override}")
        return override
    weights = formats_cfg["weekday_weights"][str(run_date.weekday())]
    eligible = {
        k: w for k, w in weights.items()
        if w > 0 and not (formats[k].get("requires_post") and topic["type"] != "post")
    }
    if duration_target:
        # a requested duration outranks the rotation: only formats whose
        # range contains it (a 60s request must never become a 265s video)
        fits = {k: w for k, w in eligible.items()
                if formats[k]["duration_range"][0] <= duration_target
                <= formats[k]["duration_range"][1]}
        if fits:
            eligible = fits
    rng = random.Random(run_date.toordinal())  # deterministic per day
    keys = list(eligible)
    return rng.choices(keys, weights=[eligible[k] for k in keys])[0]


def pick_duration(formats_cfg, format_key, settings, override=None):
    lo, hi = formats_cfg["formats"][format_key]["duration_range"]
    if override:
        return max(lo, min(hi, int(override)))
    return max(lo, min(hi, settings.get("duration_target_default", 120)))


def write_failure(stage, error):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "failure.json").write_text(json.dumps({
        "stage": stage,
        "error": str(error),
        "traceback": traceback.format_exc(),
    }, indent=2))


def _set_stage(name):
    global CURRENT_STAGE
    CURRENT_STAGE = name


def run_pipeline(args):
    import assemble
    import captions
    import content
    import deliver
    import render
    import voice
    from qa import run_qa
    from script import generate_script

    settings = load_config("settings.json")
    brand = load_config("brand.json")
    formats_cfg = load_config("formats.json")
    run_date = date.today()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    _set_stage("content")
    qa_verdicts = []

    if args.fixture:
        script = json.loads(Path(args.fixture).read_text())
        topic = {"type": "fixture", "key": Path(args.fixture).stem}
        format_key = args.format_override or "one_chart_one_claim"
        source_url = f"https://{settings['site']}"
    else:
        posts = content.fetch_posts(settings)
        topics = content.load_topics()
        topic = content.select_topic(topics, posts, override=args.topic_override)
        print(f"[content] topic: {topic}")
        source_text, source_url = content.gather_source_material(
            topic, settings, max_words=settings.get("source_max_words", 2500))
        canonical = content.load_canonical()
        format_key = pick_format(formats_cfg, topic, run_date,
                                 args.format_override, args.duration_target)
        duration_target = pick_duration(formats_cfg, format_key, settings,
                                        args.duration_target)
        print(f"[content] format: {format_key}, target: {duration_target}s")

        _set_stage("script")
        titles = deliver.recent_titles()
        script = generate_script(duration_target, format_key, source_text,
                                 canonical, titles, settings)
        (OUTPUT_DIR / "script.json").write_text(json.dumps(script, indent=2))

        _set_stage("qa")
        verdict = run_qa(script, source_text, canonical, settings,
                         duration_target=duration_target)
        qa_verdicts.append(verdict)
        if verdict["verdict"] == "fail":
            print(f"[qa] fail: {verdict['violations']} — one retry")
            script = generate_script(duration_target, format_key, source_text,
                                     canonical, titles, settings,
                                     qa_feedback=verdict["violations"])
            (OUTPUT_DIR / "script.json").write_text(json.dumps(script, indent=2))
            verdict = run_qa(script, source_text, canonical, settings,
                             duration_target=duration_target)
            qa_verdicts.append(verdict)
            if verdict["verdict"] == "fail":
                raise RuntimeError(
                    "QA failed twice; aborting. Violations: "
                    + json.dumps([v["violations"] for v in qa_verdicts])
                )
        print("[qa] pass")

    segments = script["segments"]

    _set_stage("voice")
    if args.no_voice:
        mp3_path = None
        segment_times = render.estimate_segment_times(segments)
        caption_events = captions.build_caption_events_estimated(segments, segment_times)
    else:
        full_text, offsets = voice.concatenate_segments(segments)
        mp3_path, alignment = voice.synthesize(full_text, settings, OUTPUT_DIR)
        segment_times = voice.segment_times(offsets, alignment, full_text)
        caption_events = captions.build_caption_events(full_text, offsets, alignment)
    print(f"[voice] {len(segments)} segments, "
          f"{segment_times[-1][1]:.1f}s total")

    _set_stage("render")
    t0 = time.time()
    frames_dir = OUTPUT_DIR / "frames"
    frame_format = settings.get("frame_format", "png")
    n_frames, total_duration = render.render_frames(
        script, brand, segment_times, caption_events, frames_dir,
        frame_format=frame_format,
        jpeg_quality=settings.get("jpeg_quality", 92),
        series=SERIES_BY_FORMAT.get(format_key, "OBSERVATORY"),
    )
    render_seconds = time.time() - t0
    print(f"[render] {n_frames} frames in {render_seconds:.1f}s")

    _set_stage("assemble")
    mp4_path = OUTPUT_DIR / f"xrpv_{run_date.isoformat()}.mp4"
    assemble.assemble(
        frames_dir, mp3_path, mp4_path, fps=brand["fps"],
        frame_ext="jpg" if frame_format == "jpeg" else "png",
        ambient=settings.get("ambient_bed", False),
        ambient_db=settings.get("ambient_bed_db", -22),
        silent_duration=total_duration if args.no_voice else None,
    )
    caption_path = assemble.write_caption_file(
        script.get("caption_text", ""),
        OUTPUT_DIR / f"xrpv_{run_date.isoformat()}_caption.txt",
    )
    print(f"[assemble] {mp4_path}")

    if args.fixture or args.no_deliver:
        print("[deliver] skipped (fixture / --no-deliver run)")
        return

    _set_stage("deliver")
    release_url = deliver.create_release(
        run_date, mp4_path, caption_path, script, format_key, source_url,
        total_duration,
    )
    print(f"[deliver] release: {release_url}")
    if settings.get("email_delivery"):
        deliver.send_email(release_url, script.get("caption_text", ""), run_date)

    _set_stage("history")
    deliver.write_history(run_date, topic, format_key, script, qa_verdicts,
                          {"total": total_duration,
                           "segments": segment_times},
                          render_seconds)
    content.save_topics(content.mark_used(content.load_topics(), topic))
    print("[history] written; topic moved queue → used")


def main():
    parser = argparse.ArgumentParser(description="xrpv daily video pipeline")
    parser.add_argument("--fixture", help="render a fixture script JSON instead of generating one")
    parser.add_argument("--no-voice", action="store_true",
                        help="skip TTS; estimate timing and render silent")
    parser.add_argument("--no-deliver", action="store_true",
                        help="skip release/email/history stages")
    parser.add_argument("--topic-override", help="post slug or evergreen key")
    parser.add_argument("--duration-target", type=int,
                        choices=[60, 120, 180, 300])
    parser.add_argument("--format-override",
                        choices=["field_note_explainer", "one_chart_one_claim",
                                 "term_of_the_day", "terminal_reading"])
    args = parser.parse_args()

    try:
        run_pipeline(args)
    except Exception as e:  # record the failing stage for the workflow issue
        write_failure(CURRENT_STAGE, e)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
