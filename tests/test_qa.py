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


def test_spelled_out_numbers_trace_to_digit_sources():
    # regression: the first live run flagged all of these as fabricated
    # because the voiceover spells numbers out while sources carry digits
    source = ("XRP's current market cap of roughly $82 billion. Slippage of "
              "47 basis points on a $2B payment. 10–25 basis points. "
              "3% volatility and 1% daily turnover. The $180 scenario. "
              "~9bp. 8 to 10 percent annual return.")
    script = copy.deepcopy(FIXTURE)
    script["spoken_numbers"] = [
        "eighty-two billion dollars",
        "approximately forty-seven basis points",
        "ten to twenty-five basis points",
        "three percent volatility",
        "one percent daily turnover",
        "two-billion-dollar transaction",
        "one-hundred-eighty-dollar scenario",
        "roughly nine basis points",
        "eight to ten percent annual return",
        "eighty-two billion dollars ($82B)",
        "one point five trillion dollars",
    ]
    assert check_spoken_numbers(script, source, CANONICAL) == []


def test_and_and_thousand_forms_trace():
    # regression: run 2 flagged both of these against a source with the digits
    source = "The $180 scenario. A required price of $2,951 per XRP."
    script = copy.deepcopy(FIXTURE)
    script["spoken_numbers"] = [
        "one hundred and eighty dollars ($180)",
        "two thousand nine hundred and fifty-one dollars ($2,951)",
    ]
    assert check_spoken_numbers(script, source, CANONICAL) == []


def test_llm_response_with_trailing_commentary_parses():
    # regression: run 2 crashed on "Extra data" when the QA model appended
    # prose after its JSON verdict
    from script import extract_json_object
    raw = ('{"verdict": "pass", "violations": []}\n\n'
           "Overall this script is well grounded in the source material.")
    assert extract_json_object(raw) == {"verdict": "pass", "violations": []}
    fenced = '```json\n{"verdict": "fail", "violations": []}\n```\ntrailing'
    assert extract_json_object(fenced)["verdict"] == "fail"
    prose_first = 'Here is my verdict:\n{"verdict": "pass", "violations": []}'
    assert extract_json_object(prose_first)["verdict"] == "pass"


def test_llm_verdict_derived_from_check_statuses():
    # regression: run 3 returned verdict=fail while every "violation"
    # concluded "no violation" — the verdict must come from the statuses
    from qa import interpret_llm_result
    all_pass = {"verdict": "fail", "checks": [
        {"rule": "1 numbers", "status": "pass", "detail": ""},
        {"rule": "5 disclaimer", "status": "pass", "detail": ""},
    ]}
    assert interpret_llm_result(all_pass) == {"verdict": "pass", "violations": []}

    one_fail = {"verdict": "pass", "checks": [
        {"rule": "1 numbers", "status": "pass", "detail": ""},
        {"rule": "2 vocabulary", "status": "fail", "detail": "says 'moon'"},
    ]}
    result = interpret_llm_result(one_fail)
    assert result["verdict"] == "fail"
    assert result["violations"] == [{"rule": "2 vocabulary", "detail": "says 'moon'"}]

    legacy = {"verdict": "pass", "violations": []}
    assert interpret_llm_result(legacy)["verdict"] == "pass"


def test_spelled_out_fabricated_number_still_fails():
    script = copy.deepcopy(FIXTURE)
    script["spoken_numbers"] = ["ninety-nine trillion dollars"]
    violations = check_spoken_numbers(script, SOURCE, CANONICAL)
    assert any("ninety-nine" in v["detail"] for v in violations)


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


def test_overlong_script_fails_pacing():
    # regression: a 60s request produced a 265s video
    from qa import check_pacing
    long_script = {"segments": [{"voiceover": " ".join(["word"] * 660)}]}
    violations = check_pacing(long_script, 60)
    assert violations and "60s target" in violations[0]["detail"]

    fits = {"segments": [{"voiceover": " ".join(["word"] * 150)}]}
    assert check_pacing(fits, 60) == []
    assert check_pacing(long_script, None) == []  # no target, no contract


def test_duration_target_constrains_format_choice():
    import json as _json
    from datetime import date as _date
    from main import pick_format
    formats_cfg = _json.loads((ROOT / "config" / "formats.json").read_text())
    topic = {"type": "post", "slug": "x"}
    for weekday_probe in range(14):  # every weekday, both weight tables
        day = _date(2026, 7, 1).fromordinal(_date(2026, 7, 1).toordinal() + weekday_probe)
        key = pick_format(formats_cfg, topic, day, duration_target=60)
        lo, hi = formats_cfg["formats"][key]["duration_range"]
        assert lo <= 60 <= hi, f"{key} cannot deliver a 60s video"


def test_flow_rejects_consecutive_same_scene():
    # regression: the derivatives video was three declaration cards in a row
    from qa import check_flow
    poisoned = copy.deepcopy(FIXTURE)
    poisoned["segments"][2]["scene"] = "declaration"
    poisoned["segments"][3]["scene"] = "declaration"
    violations = check_flow(poisoned)
    assert any("vary the visual" in v["detail"] for v in violations)


def test_flow_requires_a_data_scene():
    from qa import check_flow
    poisoned = copy.deepcopy(FIXTURE)
    for seg in poisoned["segments"][1:-1]:
        seg["scene"] = "declaration"
    violations = check_flow(poisoned)
    assert any("no stat_counter or chart" in v["detail"] for v in violations)


def test_flow_rejects_insider_hook():
    # regression: "Someone said our model ignores..." means nothing cold
    from qa import check_flow
    poisoned = copy.deepcopy(FIXTURE)
    poisoned["segments"][0]["voiceover"] = \
        "Someone said our model ignores the derivatives market."
    violations = check_flow(poisoned)
    assert any("cold viewer" in v["detail"] for v in violations)


def test_fixture_passes_flow():
    from qa import check_flow
    assert check_flow(FIXTURE) == []


def test_missing_disclaimer_fails():
    poisoned = copy.deepcopy(FIXTURE)
    poisoned["caption_text"] = "No disclaimer here #XRP"
    assert check_disclaimer(poisoned)
