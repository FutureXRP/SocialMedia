"""Stage 2 — script generation via the Anthropic API.

One API call. Temperature 1.0 is fine; discipline comes from the prompt and
the QA pass, not sampling. Voiceover fields are sanitized of em/en dashes
before TTS (ElevenLabs alignment-drift issue found on Footsteps); display
fields may keep them.
"""

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTWRITER_PROMPT = ROOT / "prompts" / "scriptwriter.md"

_DASH_MID = re.compile(r"\s*[—–]\s*")      # dash inside a clause → comma pause
_DASH_END = re.compile(r"\s*[—–]\s*$")


def sanitize_voiceover_text(text):
    """Em/en dashes become commas (or a period at end of text) before TTS."""
    text = _DASH_END.sub(".", text)
    return _DASH_MID.sub(", ", text)


def sanitize_script(script):
    for seg in script.get("segments", []):
        seg["voiceover"] = sanitize_voiceover_text(seg.get("voiceover", ""))
    if "cta_voiceover" in script:
        script["cta_voiceover"] = sanitize_voiceover_text(script["cta_voiceover"])
    return script


def parse_script_json(raw):
    """The prompt demands bare JSON; strip fences defensively anyway."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    return json.loads(raw)


def build_user_message(duration_target, format_key, source_text, canonical,
                       recent_titles):
    return (
        f"DURATION TARGET\n{duration_target} seconds\n\n"
        f"FORMAT\n{format_key}\n\n"
        f"SOURCE MATERIAL\n{source_text}\n\n"
        f"CANONICAL DATA\n{json.dumps(canonical, indent=2)}\n\n"
        f"RECENT VIDEO TITLES\n" + ("\n".join(recent_titles) if recent_titles else "(none)")
    )


def generate_script(duration_target, format_key, source_text, canonical,
                    recent_titles, settings, qa_feedback=None):
    """Call the scriptwriter model; returns the parsed, sanitized script."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    user_message = build_user_message(duration_target, format_key, source_text,
                                      canonical, recent_titles)
    if qa_feedback:
        user_message += (
            "\n\nQA VIOLATIONS FROM PREVIOUS ATTEMPT (fix every one)\n"
            + json.dumps(qa_feedback, indent=2)
        )

    response = client.messages.create(
        model=settings["anthropic_model"],
        max_tokens=8000,
        temperature=1.0,
        system=SCRIPTWRITER_PROMPT.read_text(),
        messages=[{"role": "user", "content": user_message}],
    )
    script = parse_script_json(response.content[0].text)
    return sanitize_script(script)
