import json
from datetime import date
from pathlib import Path

import pytest

import content
from content import check_external_domain, merge_feeds, select_topic
from main import pick_format

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = json.loads((ROOT / "config" / "settings.json").read_text())
FORMATS = json.loads((ROOT / "config" / "formats.json").read_text())

QUEUE = {
    "queue": [
        {"type": "feature", "key": "terminal", "title": "Terminal",
         "format_hint": "terminal_reading"},
        {"type": "external", "key": "bis-agora",
         "title": "BIS on Project Agora", "url": "https://www.bis.org/agora"},
        {"type": "evergreen", "key": "dvp", "title": "DvP"},
    ],
    "used": [],
}


def test_merge_feeds_dedupes_by_slug_first_feed_wins():
    blog = [{"slug": "a", "title": "A-blog"}, {"slug": "b"}]
    notes = [{"slug": "a", "title": "A-notes"}, {"slug": "c"}]
    merged = merge_feeds([blog, notes])
    assert [p["slug"] for p in merged] == ["a", "b", "c"]
    assert merged[0]["title"] == "A-blog"


def test_fresh_posts_jump_queue():
    topic = select_topic(QUEUE, [{"slug": "new-post"}], today=date(2026, 7, 5))
    assert topic == {"type": "post", "slug": "new-post", "title": "new-post"}


def test_queue_serves_features_and_externals_in_order():
    t1 = select_topic(QUEUE, [], today=date(2026, 7, 5))
    assert t1["type"] == "feature" and t1["key"] == "terminal"
    t2 = select_topic(QUEUE, [], today=date(2026, 7, 5), exclude={"terminal"})
    assert t2["type"] == "external" and t2["key"] == "bis-agora"


def test_override_matches_queue_entry():
    topic = select_topic(QUEUE, [], today=date(2026, 7, 5), override="bis-agora")
    assert topic["type"] == "external"
    assert topic["url"] == "https://www.bis.org/agora"


def test_external_domain_allowlist():
    check_external_domain("https://www.bis.org/x", SETTINGS)
    check_external_domain("https://imf.org/report", SETTINGS)
    with pytest.raises(ValueError, match="not allowlisted"):
        check_external_domain("https://random-crypto-blog.com/xrp", SETTINGS)
    with pytest.raises(ValueError, match="not allowlisted"):
        # suffix spoofing must not pass: evilbis.org is not bis.org
        check_external_domain("https://evilbis.org/x", SETTINGS)


def test_external_gather_fetches_and_labels(monkeypatch):
    monkeypatch.setattr(content, "fetch_page_text",
                        lambda url: "The BIS reports 7 central banks joined.")
    topic = {"type": "external", "key": "bis-agora",
             "url": "https://www.bis.org/agora"}
    text, url, kind = content.gather_source_material(topic, SETTINGS)
    assert kind == "external"
    assert url == "https://www.bis.org/agora"
    assert "7 central banks" in text


def test_feature_topic_requires_configured_url():
    topic = {"type": "feature", "key": "nonexistent-feature"}
    with pytest.raises(ValueError, match="no URL configured"):
        content.gather_source_material(topic, SETTINGS)


def test_exhausted_queue_recycles_stalest_evergreen_instead_of_failing():
    # at 2 videos/day the queue outruns the 14-day rule; never miss a video
    topics = {
        "queue": [],
        "used": [
            {"type": "evergreen", "key": "dvp", "title": "DvP", "date": "2026-07-03"},
            {"type": "evergreen", "key": "odl", "title": "ODL", "date": "2026-07-01"},
            {"type": "post", "key": "old-post", "title": "x", "date": "2026-06-30"},
        ],
    }
    topic = select_topic(topics, [], today=date(2026, 7, 5))
    assert topic["key"] == "odl"  # stalest evergreen, despite 14-day rule


def test_format_hint_steers_rotation():
    topic = {"type": "feature", "key": "terminal", "format_hint": "terminal_reading"}
    for probe in range(7):
        day = date.fromordinal(date(2026, 7, 1).toordinal() + probe)
        assert pick_format(FORMATS, topic, day) == "terminal_reading"


def test_format_hint_yields_to_duration_contract():
    # terminal_reading is 90-150s; a 60s request must beat the hint
    topic = {"type": "feature", "key": "terminal", "format_hint": "terminal_reading"}
    key = pick_format(FORMATS, topic, date(2026, 7, 5), duration_target=60)
    lo, hi = FORMATS["formats"][key]["duration_range"]
    assert lo <= 60 <= hi
