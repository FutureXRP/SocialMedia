"""ElevenLabs TTS with character-level timestamps.

One call to /v1/text-to-speech/{voice_id}/with-timestamps returns base64 MP3
plus alignment arrays. Segment voiceovers are concatenated with blank lines
(natural pauses); a char-offset map records where each segment starts so
per-segment start/end times can be derived for scene durations.
"""

import base64
import json
import os
from pathlib import Path

import requests

SEGMENT_SEPARATOR = "\n\n"
API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"


def concatenate_segments(segments):
    """Return (full_text, offsets) where offsets is a list of
    (segment_index, char_start, segment_text)."""
    offsets, parts, pos = [], [], 0
    for i, seg in enumerate(segments):
        text = seg["voiceover"]
        offsets.append((i, pos, text))
        parts.append(text)
        pos += len(text) + len(SEGMENT_SEPARATOR)
    return SEGMENT_SEPARATOR.join(parts), offsets


def synthesize(full_text, settings, output_dir):
    """Call ElevenLabs, persist raw response + decoded MP3, return
    (mp3_path, alignment)."""
    api_key = os.environ["ELEVENLABS_API_KEY"]
    voice_id = settings["elevenlabs_voice_id"]
    resp = requests.post(
        API_URL.format(voice_id=voice_id),
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={
            "text": full_text,
            "model_id": settings.get("elevenlabs_model_id", "eleven_multilingual_v2"),
            "output_format": settings.get("elevenlabs_output_format", "mp3_44100_128"),
        },
        timeout=600,
    )
    resp.raise_for_status()
    payload = resp.json()

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "elevenlabs_response.json").write_text(json.dumps(payload))
    mp3_path = output_dir / "voiceover.mp3"
    mp3_path.write_bytes(base64.b64decode(payload["audio_base64"]))
    return str(mp3_path), payload["alignment"]


def segment_times(offsets, alignment, full_text):
    """Derive per-segment (start, end) seconds from the char-offset map and
    the character alignment. These drive scene durations in the render."""
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]
    n = len(alignment["characters"])
    times = []
    for _i, char_start, text in offsets:
        a = min(char_start, n - 1)
        b = min(char_start + len(text) - 1, n - 1)
        times.append((starts[a], ends[b]))
    # segments tile the timeline: each ends where the next begins
    tiled = []
    for i, (s, e) in enumerate(times):
        end = times[i + 1][0] if i + 1 < len(times) else max(e, ends[-1])
        tiled.append((s if i else 0.0, end))
    return tiled
