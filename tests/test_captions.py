"""Caption phrase splitting and alignment mapping.

The Phase 2 acceptance criterion: caption changes land within ±100ms of the
spoken phrase. We synthesize an alignment at a known per-character rate and
spot-check that mapped phrase start times match the alignment exactly.
"""

from captions import (
    build_caption_events,
    build_caption_events_estimated,
    phrase_at_time,
    split_phrases,
)
from voice import concatenate_segments, segment_times

CHAR_SECONDS = 0.05  # synthetic: every character takes 50ms


def make_alignment(text):
    return {
        "characters": list(text),
        "character_start_times_seconds": [i * CHAR_SECONDS for i in range(len(text))],
        "character_end_times_seconds": [(i + 1) * CHAR_SECONDS for i in range(len(text))],
    }


def test_split_phrases_respects_word_bounds():
    text = ("Banks park trillions of dollars in accounts that earn nothing, "
            "and nobody planned this. It is plumbing. Plumbing is invisible "
            "until it leaks everywhere at once.")
    phrases = split_phrases(text)
    assert phrases, "no phrases produced"
    for p in phrases:
        assert 3 <= len(p.split()) <= 7, f"bad phrase length: {p!r}"
    # reassembles to the original words in order
    assert " ".join(phrases).split() == text.split()


def test_split_prefers_punctuation_boundaries():
    phrases = split_phrases("Settlement is the problem, not speculation about it.")
    assert phrases[0].endswith(",") or phrases[0].endswith("problem,")


def test_caption_events_match_alignment_within_100ms():
    segments = [
        {"voiceover": "Banks park trillions of dollars in accounts that earn nothing."},
        {"voiceover": "Settlement is the actual problem, and plumbing stays invisible."},
        {"voiceover": "Every input is published, so anyone can check the math."},
    ]
    full_text, offsets = concatenate_segments(segments)
    alignment = make_alignment(full_text)
    events = build_caption_events(full_text, offsets, alignment)

    assert len(events) >= 5
    for event in events[:5]:  # spot-check 5 phrases against the alignment
        char_index = full_text.index(event["text"])
        expected_start = char_index * CHAR_SECONDS
        assert abs(event["start"] - expected_start) <= 0.1, (
            f"{event['text']!r}: start {event['start']} vs expected {expected_start}"
        )


def test_phrase_at_time_returns_active_phrase():
    events = [
        {"text": "one two three", "start": 0.0, "end": 1.0},
        {"text": "four five six", "start": 1.0, "end": 2.0},
    ]
    assert phrase_at_time(events, 0.5) == "one two three"
    assert phrase_at_time(events, 1.0) == "four five six"
    assert phrase_at_time(events, 2.5) == ""


def test_events_tile_without_gaps():
    segments = [{"voiceover": "One two three four. Five six seven eight nine ten eleven."}]
    full_text, offsets = concatenate_segments(segments)
    events = build_caption_events(full_text, offsets, make_alignment(full_text))
    for a, b in zip(events, events[1:]):
        assert a["end"] >= a["start"]
        assert a["end"] == b["start"]


def test_segment_times_tile_the_timeline():
    segments = [
        {"voiceover": "First segment voiceover text here."},
        {"voiceover": "Second segment voiceover text follows."},
    ]
    full_text, offsets = concatenate_segments(segments)
    times = segment_times(offsets, make_alignment(full_text), full_text)
    assert times[0][0] == 0.0
    assert times[0][1] == times[1][0]
    assert times[1][1] >= len(full_text) * CHAR_SECONDS - 0.101


def test_estimated_events_cover_segment_windows():
    segments = [{"voiceover": "Alpha beta gamma delta epsilon zeta eta theta."}]
    events = build_caption_events_estimated(segments, [(0.0, 4.0)])
    assert events[0]["start"] == 0.0
    assert abs(events[-1]["end"] - 4.0) < 1e-6
