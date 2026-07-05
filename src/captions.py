"""Timestamp → phrase caption mapping.

Splits voiceover into 3–7 word phrases at natural boundaries and maps each
phrase to start/end times using the ElevenLabs character-level alignment
(binary search over character_start_times — the Footsteps approach). The
active phrase must change exactly when the voice reaches it; this burned-in
sync is the single biggest watchability lever.
"""

import re
from bisect import bisect_left

MIN_WORDS = 3
MAX_WORDS = 7

# Split points in preference order: sentence enders, then clause breaks.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_CLAUSE_RE = re.compile(r"(?<=[,;:])\s+")


def split_phrases(text):
    """Split text into caption phrases of 3–7 words, punctuation first,
    then length. Short trailing fragments merge back into the prior phrase."""
    phrases = []
    for sentence in _SENTENCE_RE.split(text.strip()):
        if not sentence:
            continue
        for clause in _CLAUSE_RE.split(sentence):
            words = clause.split()
            while words:
                if len(words) <= MAX_WORDS:
                    take = len(words)
                elif len(words) - MAX_WORDS < MIN_WORDS:
                    take = len(words) - MIN_WORDS  # rebalance: no short tail
                else:
                    take = MAX_WORDS
                chunk, words = words[:take], words[take:]
                phrases.append(" ".join(chunk))
    # merge any still-short phrases (from short clauses) into a neighbor
    merged = []
    for p in phrases:
        if merged and (len(p.split()) < MIN_WORDS or len(merged[-1].split()) < MIN_WORDS) \
                and len(merged[-1].split()) + len(p.split()) <= MAX_WORDS:
            merged[-1] = merged[-1] + " " + p
        else:
            merged.append(p)
    return merged


def _char_time(alignment, char_index, key):
    times = alignment[key]
    return times[min(max(char_index, 0), len(times) - 1)]


def find_char_index(alignment, offset):
    """Index into the alignment arrays for a character offset in the
    concatenated voiceover string (identity when texts match; kept as a
    function so drift handling stays in one place)."""
    return min(offset, len(alignment["characters"]) - 1)


def event_at_time(caption_events, t):
    """Return the active caption event at time t (binary search), or None."""
    starts = [e["start"] for e in caption_events]
    i = bisect_left(starts, t)
    if i > 0 and (i == len(starts) or starts[i] > t):
        i -= 1
    if 0 <= i < len(caption_events):
        e = caption_events[i]
        if e["start"] <= t < e["end"]:
            return e
    return None


def phrase_at_time(caption_events, t):
    """Return the active caption text at time t."""
    e = event_at_time(caption_events, t)
    return e["text"] if e else ""


def build_caption_events(concatenated_text, segments_offsets, alignment):
    """Map every phrase of every segment to [start, end) seconds.

    segments_offsets: list of (segment_index, char_start, voiceover_text) for
    the concatenated string sent to TTS. alignment: the ElevenLabs alignment
    dict with characters / character_start_times_seconds /
    character_end_times_seconds.
    """
    events = []
    for _seg_i, seg_start, seg_text in segments_offsets:
        cursor = 0
        for phrase in split_phrases(seg_text):
            local = seg_text.find(phrase, cursor)
            if local < 0:  # whitespace normalization shifted it; fall back
                local = cursor
            cursor = local + len(phrase)
            a = find_char_index(alignment, seg_start + local)
            b = find_char_index(alignment, seg_start + local + len(phrase) - 1)
            # per-word start times drive the karaoke highlight
            words, wpos = [], 0
            for w in phrase.split():
                at = phrase.find(w, wpos)
                wpos = at + len(w)
                wi = find_char_index(alignment, seg_start + local + at)
                words.append({"text": w,
                              "start": _char_time(alignment, wi,
                                                  "character_start_times_seconds")})
            events.append({
                "text": phrase,
                "start": _char_time(alignment, a, "character_start_times_seconds"),
                "end": _char_time(alignment, b, "character_end_times_seconds"),
                "words": words,
            })
    # captions must not overlap or gap visibly: extend each to the next start
    for i in range(len(events) - 1):
        events[i]["end"] = max(events[i]["end"], events[i]["start"])
        events[i]["end"] = min(max(events[i]["end"], events[i + 1]["start"]),
                               events[i + 1]["start"])
        if events[i]["end"] < events[i + 1]["start"]:
            events[i]["end"] = events[i + 1]["start"]
    return events


def build_caption_events_estimated(segments, segment_times):
    """No-voice mode: distribute each segment's phrases proportionally to
    word count across the segment's [start, end) window."""
    events = []
    for seg, (start, end) in zip(segments, segment_times):
        phrases = split_phrases(seg.get("voiceover", ""))
        total_words = sum(len(p.split()) for p in phrases) or 1
        t = start
        for p in phrases:
            dur = (end - start) * len(p.split()) / total_words
            wlist = p.split()
            words = [{"text": w, "start": t + dur * i / len(wlist)}
                     for i, w in enumerate(wlist)]
            events.append({"text": p, "start": t, "end": t + dur, "words": words})
            t += dur
    return events
