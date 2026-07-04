"""Stage 3 — QA pass: the editorial firewall. It is load-bearing and may
never be bypassed with a flag; there is no --skip-qa.

Programmatic checks run first (schema, forbidden vocabulary, number
provenance, quote limits, disclaimer, $589 framing) — the code check is
suspenders. An independent Anthropic call is the belt. A script renders only
if both pass; one regeneration retry is allowed, then the run aborts.
"""

import json
import os
import re
from pathlib import Path

from script import extract_json_object

ROOT = Path(__file__).resolve().parent.parent
QA_PROMPT = ROOT / "prompts" / "qa_reviewer.md"

DISCLAIMER = "Research, not investment advice."

FORBIDDEN_WORDS = [
    "moon", "pump", "dump", "ape", "wagmi", "ngmi", "100x", "1000x",
    "trust me", "guaranteed", "about to explode", "last chance",
    "financial freedom",
]

# $589 must never be framed as a certainty. "derived anchor" must be present.
BAD_589_PATTERNS = [
    r"will (?:hit|reach|be worth|go to|trade at)[^.]{0,40}589",
    r"589[^.]{0,40}(?:price target|guaranteed|prediction)",
    r"(?:target|predict\w*)[^.]{0,40}\$?589",
]

SCENE_KEYS = {
    "hook_typewriter", "stat_counter", "declaration", "chart_sqrt",
    "chart_bar", "chart_line", "quote_card", "list_reveal", "cta_card",
}

_NUM_NORM = re.compile(r"[,$\s]")

# Voiceover numbers are spelled out for TTS ("eighty-two billion dollars");
# sources carry digits ("$82 billion"). Parse word-numbers so provenance
# matching compares like with like.
_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
          "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
          "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
          "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
          "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90}


def words_to_values(text):
    """Extract every numeric quantity in `text` as a float mantissa.
    Scale words (billion, percent, basis points, dollars) end a number but
    do not scale it — matching is done on mantissas, which is what the
    digit form in a source carries ("$82 billion" → 82)."""
    tokens = re.findall(r"[a-z]+|\d+(?:\.\d+)?", text.lower().replace("-", " "))
    values = []
    total, cur, active, dec, div = 0.0, 0.0, False, False, 0.1

    def flush():
        nonlocal total, cur, active, dec, div
        if active:
            values.append(total + cur)
        total, cur, active, dec, div = 0.0, 0.0, False, False, 0.1

    for tok in tokens:
        if re.fullmatch(r"\d+(?:\.\d+)?", tok):
            flush()
            values.append(float(tok))
        elif tok == "point" and active:
            dec = True
        elif dec and tok in _UNITS and _UNITS[tok] <= 9:
            cur += _UNITS[tok] * div
            div /= 10
        elif not dec and tok in _UNITS:
            cur += _UNITS[tok]
            active = True
        elif not dec and tok in _TENS:
            cur += _TENS[tok]
            active = True
        elif not dec and tok == "hundred" and active:
            cur *= 100
        elif not dec and tok == "thousand" and active:
            total += cur * 1000  # "two thousand nine hundred..." keeps going
            cur = 0.0
        elif tok == "and" and active and not dec:
            continue  # "one hundred and eighty" is one number
        else:
            flush()
    flush()
    return values


def _script_spoken_text(script):
    parts = [seg.get("voiceover", "") for seg in script.get("segments", [])]
    parts.append(script.get("cta_voiceover", ""))
    return " ".join(parts)


def _script_all_text(script):
    parts = [_script_spoken_text(script), script.get("caption_text", ""),
             script.get("hook", "")]
    for seg in script.get("segments", []):
        parts.append(json.dumps(seg.get("display", {})))
    return " ".join(parts)


def validate_schema(script):
    violations = []
    for field in ("title", "hook", "segments", "cta_voiceover", "caption_text",
                  "spoken_numbers"):
        if field not in script:
            violations.append({"rule": "6 schema", "detail": f"missing field: {field}"})
    segments = script.get("segments", [])
    if not segments:
        violations.append({"rule": "6 schema", "detail": "no segments"})
        return violations
    for i, seg in enumerate(segments):
        if seg.get("scene") not in SCENE_KEYS:
            violations.append({"rule": "6 schema",
                               "detail": f"segment {i}: unknown scene {seg.get('scene')!r}"})
        if not isinstance(seg.get("voiceover"), str) or not seg.get("voiceover").strip():
            violations.append({"rule": "6 schema", "detail": f"segment {i}: empty voiceover"})
        if not isinstance(seg.get("display"), dict):
            violations.append({"rule": "6 schema", "detail": f"segment {i}: missing display"})
    if segments and segments[0].get("scene") != "hook_typewriter":
        violations.append({"rule": "6 schema", "detail": "first segment must be hook_typewriter"})
    if segments and segments[-1].get("scene") != "cta_card":
        violations.append({"rule": "6 schema", "detail": "last segment must be cta_card"})
    return violations


def normalize_number(s):
    return _NUM_NORM.sub("", s).lower()


def _format_value(v):
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


def _entry_traceable(entry, haystack):
    """True if every numeric quantity in the entry (digit or spelled-out
    form) appears in the normalized haystack."""
    quantities = re.findall(r"\d+(?:\.\d+)?", normalize_number(entry))
    quantities += [_format_value(v) for v in words_to_values(entry)]
    if not quantities:
        return True  # nothing checkable (e.g. "a majority")
    return all(q in haystack for q in set(quantities))


def check_spoken_numbers(script, source_text, canonical):
    """Every spoken number must resolve to source material or canonical.json,
    matched on normalized strings. Spelled-out voiceover forms are converted
    to digits before matching so "eighty-two billion" traces to "$82B"."""
    haystack = normalize_number(source_text + json.dumps(canonical))
    violations = []
    for entry in script.get("spoken_numbers", []):
        if not _entry_traceable(str(entry), haystack):
            violations.append({
                "rule": "1 numbers",
                "detail": f"spoken number not found in source or canonical: {entry!r}",
            })
    return violations


def check_forbidden_vocabulary(script):
    text = _script_all_text(script).lower()
    violations = []
    for word in FORBIDDEN_WORDS:
        if " " in word or word.endswith("x"):
            hit = word in text
        else:
            hit = re.search(rf"\b{re.escape(word)}\b", text) is not None
        if hit:
            violations.append({"rule": "2 forbidden-vocabulary",
                               "detail": f"forbidden term present: {word!r}"})
    return violations


def check_589_framing(script):
    text = _script_all_text(script)
    if "589" not in text:
        return []
    violations = []
    if "derived anchor" not in text.lower():
        violations.append({"rule": "3 589-framing",
                           "detail": "$589 used without 'derived anchor' framing"})
    for pat in BAD_589_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            violations.append({"rule": "3 589-framing",
                               "detail": f"$589 framed as certainty (pattern: {pat})"})
    return violations


def check_quotes(script):
    violations = []
    attributions = {}
    for i, seg in enumerate(script.get("segments", [])):
        if seg.get("scene") != "quote_card":
            continue
        display = seg.get("display", {})
        quote = display.get("quote", "")
        if len(quote.split()) >= 15:
            violations.append({"rule": "4 quotes",
                               "detail": f"segment {i}: quote is {len(quote.split())} words (limit <15)"})
        source = display.get("attribution", "").strip().lower()
        attributions[source] = attributions.get(source, 0) + 1
    for source, count in attributions.items():
        if count > 1:
            violations.append({"rule": "4 quotes",
                               "detail": f"multiple direct quotes from one source: {source!r}"})
    return violations


def check_disclaimer(script):
    if DISCLAIMER not in script.get("caption_text", ""):
        return [{"rule": "5 disclaimer",
                 "detail": f"caption_text missing {DISCLAIMER!r}"}]
    return []


def programmatic_checks(script, source_text, canonical):
    violations = validate_schema(script)
    if violations:
        return violations  # schema first; other checks assume shape
    violations += check_spoken_numbers(script, source_text, canonical)
    violations += check_forbidden_vocabulary(script)
    violations += check_589_framing(script)
    violations += check_quotes(script)
    violations += check_disclaimer(script)
    return violations


def llm_review(script, source_text, canonical, settings):
    """Independent second-model review; returns {"verdict", "violations"}."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    user_message = (
        f"SCRIPT JSON\n{json.dumps(script, indent=2)}\n\n"
        f"SOURCE MATERIAL\n{source_text}\n\n"
        f"CANONICAL DATA\n{json.dumps(canonical, indent=2)}"
    )
    response = client.messages.create(
        model=settings["anthropic_model"],
        max_tokens=2000,
        temperature=0.0,
        system=QA_PROMPT.read_text(),
        messages=[{"role": "user", "content": user_message}],
    )
    return interpret_llm_result(extract_json_object(response.content[0].text))


def interpret_llm_result(result):
    """Derive the verdict from per-rule statuses instead of trusting the
    model's top-level verdict — a live run returned verdict=fail with a
    violations list whose every entry concluded 'no violation'."""
    if "checks" in result:
        failed = [c for c in result["checks"] if c.get("status") != "pass"]
        return {"verdict": "fail" if failed else "pass",
                "violations": [{"rule": c.get("rule", "?"),
                                "detail": c.get("detail", "")} for c in failed]}
    # legacy shape: {"verdict", "violations"}
    return {"verdict": result.get("verdict", "fail"),
            "violations": result.get("violations", [])}


def run_qa(script, source_text, canonical, settings, skip_llm=False):
    """Full QA pass. Returns {"verdict": "pass"|"fail", "violations": [...]}."""
    violations = programmatic_checks(script, source_text, canonical)
    if violations:
        return {"verdict": "fail", "violations": violations}
    if not skip_llm:
        result = llm_review(script, source_text, canonical, settings)
        if result.get("verdict") != "pass":
            return {"verdict": "fail", "violations": result.get("violations", [])}
    return {"verdict": "pass", "violations": []}
