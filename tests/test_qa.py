import copy
import json
from pathlib import Path

from qa import (
    check_589_framing,
    check_disclaimer,
    check_forbidden_vocabulary,
    check_quotes,
    check_spoken_numbers,
    programmatic_checks,
    validate_schema,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = json.loads((ROOT / "tests" / "fixture_script.json").read_text())
CANONICAL = json.loads((ROOT / "data" / "canonical.json").read_text())
SOURCE = "The XRP Ledger settled 1.5T cumulative. RWA grew 24.7M to 568M."


def test_fixture_passes_programmatic_checks():
    assert programmatic_checks(FIXTURE, SOURCE, CANONICAL) == []


def test_schema_rejects_missing_fields():
    bad = {k: v for k, v in FIXTURE.items() if k != "spoken_numbers"}
    assert any("spoken_numbers" in v["detail"] for v in validate_schema(bad))


def test_schema_requires_hook_first_cta_last():
    bad = copy.deepcopy(FIXTURE)
    bad["segments"] = bad["segments"][::-1]
    details = [v["detail"] for v in validate_schema(bad)]
    assert any("hook_typewriter" in d for d in details)
    assert any("cta_card" in d for d in details)


def test_fabricated_number_fails_qa():
    poisoned = copy.deepcopy(FIXTURE)
    poisoned["spoken_numbers"].append("$9,999,999")  # appears nowhere
    violations = check_spoken_numbers(poisoned, SOURCE, CANONICAL)
    assert any("9,999,999" in v["detail"] for v in violations)


def test_forbidden_word_fails_qa():
    poisoned = copy.deepcopy(FIXTURE)
    poisoned["segments"][1]["voiceover"] += " This is about to explode, trust me."
    violations = check_forbidden_vocabulary(poisoned)
    rules = {v["detail"] for v in violations}
    assert any("about to explode" in d for d in rules)
    assert any("trust me" in d for d in rules)


def test_forbidden_word_not_triggered_by_substrings():
    # "pumpkin" must not trip "pump"; "moonlight" must not trip "moon"
    script = copy.deepcopy(FIXTURE)
    script["segments"][2]["voiceover"] += " A pumpkin in the moonlight."
    assert check_forbidden_vocabulary(script) == []


def test_589_prediction_framing_fails():
    poisoned = copy.deepcopy(FIXTURE)
    poisoned["segments"][3]["voiceover"] = "XRP will hit $589 soon."
    violations = check_589_framing(poisoned)
    assert any("certainty" in v["detail"] for v in violations)


def test_589_without_derived_anchor_fails():
    poisoned = copy.deepcopy(FIXTURE)
    for seg in poisoned["segments"]:
        seg["voiceover"] = seg["voiceover"].replace("derived anchor", "figure")
        if "annotation" in seg.get("display", {}):
            seg["display"]["annotation"] = seg["display"]["annotation"].replace(
                "derived anchor", "figure")
    poisoned["caption_text"] = poisoned["caption_text"].replace("derived anchor", "figure")
    violations = check_589_framing(poisoned)
    assert any("derived anchor" in v["detail"] for v in violations)


def test_long_quote_fails():
    poisoned = copy.deepcopy(FIXTURE)
    poisoned["segments"][6]["display"]["quote"] = " ".join(["word"] * 15)
    violations = check_quotes(poisoned)
    assert any("15" in v["detail"] for v in violations)


def test_missing_disclaimer_fails():
    poisoned = copy.deepcopy(FIXTURE)
    poisoned["caption_text"] = "No disclaimer here #XRP"
    assert check_disclaimer(poisoned)
