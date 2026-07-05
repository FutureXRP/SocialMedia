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


def extract_json_object(raw):
    """Parse the first JSON object out of a model response, tolerating
    markdown fences, leading prose, and trailing commentary — models
    sometimes append text after the JSON despite the prompt."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    start = raw.find("{")
    if start < 0:
        raise ValueError("model response contains no JSON object")
    obj, _end = json.JSONDecoder().raw_decode(raw[start:])
    return obj


def parse_script_json(raw):
    return extract_json_object(raw)


SOURCE_NOTES = {
    "post": "The source is a published xrpvaluation.info article. Walk its "
            "argument; do not extend it.",
    "evergreen": "This is a concept explainer. Teach one idea from scratch "
                 "using the canonical data; assume zero prior knowledge.",
    "feature": "The source is a live page on xrpvaluation.info (the "
               "Settlement Terminal or the calculator). Describe what the "
               "tool shows and how a viewer can use it themselves — every "
               "input is public and editable. Only speak numbers that appear "
               "on the page or in canonical data.",
    "external": "The source is a third-party institutional document (BIS, "
                "IMF, central bank, market infrastructure). Attribute every "
                "claim to the institution by name ('according to the BIS "
                "...'). NEVER imply the institution endorses XRP or any "
                "asset — connect their facts to the settlement thesis "
                "yourself, and label that connection as the framework's "
                "reading. Invite viewers to read the original document.",
}


def build_user_message(duration_target, format_key, source_text, canonical,
                       recent_titles, source_kind="post"):
    word_budget = round(duration_target / 60 * 150)
    return (
        f"DURATION TARGET\n{duration_target} seconds. HARD LIMIT: total "
        f"voiceover across all segments must be {round(word_budget * 0.8)}–"
        f"{round(word_budget * 1.1)} words (target ~{word_budget}). Scripts "
        f"outside this range are rejected.\n\n"
        f"FORMAT\n{format_key}\n\n"
        f"SOURCE TYPE\n{SOURCE_NOTES.get(source_kind, SOURCE_NOTES['post'])}\n\n"
        f"SOURCE MATERIAL\n{source_text}\n\n"
        f"CANONICAL DATA\n{json.dumps(canonical, indent=2)}\n\n"
        f"RECENT VIDEO TITLES\n" + ("\n".join(recent_titles) if recent_titles else "(none)")
    )


def generate_script(duration_target, format_key, source_text, canonical,
                    recent_titles, settings, qa_feedback=None,
                    source_kind="post"):
    """Call the scriptwriter model; returns the parsed, sanitized script."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    user_message = build_user_message(duration_target, format_key, source_text,
                                      canonical, recent_titles, source_kind)
    if qa_feedback:
        user_message += (
            "\n\nQA VIOLATIONS FROM PREVIOUS ATTEMPT (fix every one)\n"
            + json.dumps(qa_feedback, indent=2)
        )

    # no temperature: Opus 4.7+ rejects sampling params; discipline comes
    # from the prompt and the QA pass
    response = client.messages.create(
        model=settings["anthropic_model"],
        max_tokens=8000,
        system=SCRIPTWRITER_PROMPT.read_text(),
        messages=[{"role": "user", "content": user_message}],
    )
    script = parse_script_json(response.content[0].text)
    return sanitize_script(script)
