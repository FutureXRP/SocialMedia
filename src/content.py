"""Stage 1 — content selection.

Sources in priority order: live posts.json feed, the selected post's HTML,
data/canonical.json, data/topics.json. All site links use /blog/ paths,
never /field-notes/.
"""

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
TOPICS_PATH = ROOT / "data" / "topics.json"
CANONICAL_PATH = ROOT / "data" / "canonical.json"

ROTATION_DAYS = 14


def fetch_posts(settings):
    """Fetch the live feed; a dead feed is not fatal (evergreen queue covers it)."""
    try:
        resp = requests.get(settings["posts_json_url"], timeout=30)
        resp.raise_for_status()
        posts = resp.json()
        return posts if isinstance(posts, list) else posts.get("posts", [])
    except Exception:
        return []


def fetch_post_text(slug, settings):
    """Fetch a post's HTML and strip to plain text (the site is static HTML)."""
    url = settings["post_url_pattern"].format(slug=slug)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    html = resp.text
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text, url


def load_topics():
    return json.loads(TOPICS_PATH.read_text())


def save_topics(topics):
    TOPICS_PATH.write_text(json.dumps(topics, indent=2) + "\n")


def load_canonical():
    return json.loads(CANONICAL_PATH.read_text())


def _topic_key(topic):
    return topic.get("slug") or topic.get("key")


def _used_recently(topics, key, today):
    cutoff = today - timedelta(days=ROTATION_DAYS)
    for entry in topics.get("used", []):
        if entry.get("key") == key:
            when = datetime.strptime(entry["date"], "%Y-%m-%d").date()
            if when > cutoff:
                return True
    return False


def _last_used_type(topics):
    used = topics.get("used", [])
    return used[-1].get("type") if used else None


def select_topic(topics, posts, today=None, override=None):
    """Apply the selection rules and return the chosen topic dict.

    - New posts in posts.json jump the queue.
    - Never the same topic within 14 days.
    - Never two evergreen videos back-to-back if an unused post exists.
    """
    today = today or date.today()

    if override:
        return {"type": "post", "slug": override} if any(
            p.get("slug") == override for p in posts
        ) else {"type": "evergreen", "key": override, "title": override}

    used_keys = {e["key"] for e in topics.get("used", [])}
    fresh_posts = [
        {"type": "post", "slug": p["slug"], "title": p.get("title", p["slug"])}
        for p in posts
        if p.get("slug") and p["slug"] not in used_keys
    ]  # posts.json is newest-first; keep that order

    for cand in fresh_posts:
        if not _used_recently(topics, cand["slug"], today):
            return cand

    evergreen_ok = not (fresh_posts and _last_used_type(topics) == "evergreen")
    if evergreen_ok:
        for cand in topics.get("queue", []):
            if not _used_recently(topics, _topic_key(cand), today):
                return cand

    # queue exhausted: recycle the least-recently-used evergreen
    for entry in topics.get("used", []):
        if entry.get("type") == "evergreen" and not _used_recently(topics, entry["key"], today):
            return {"type": "evergreen", "key": entry["key"], "title": entry.get("title", entry["key"])}
    raise RuntimeError("no eligible topic: queue exhausted and all topics used within 14 days")


def mark_used(topics, topic, today=None):
    """Move the topic from queue → used."""
    today = today or date.today()
    key = _topic_key(topic)
    topics["queue"] = [t for t in topics.get("queue", []) if _topic_key(t) != key]
    topics.setdefault("used", []).append({
        "type": topic["type"], "key": key,
        "title": topic.get("title", key), "date": today.isoformat(),
    })
    return topics


def gather_source_material(topic, settings, max_words=6000):
    """Return (source_text, source_url) for the scriptwriter prompt."""
    if topic["type"] == "post":
        text, url = fetch_post_text(topic["slug"], settings)
        words = text.split()
        if len(words) > max_words:
            text = " ".join(words[:max_words])
        return text, url
    canonical = load_canonical()
    title = topic.get("title", topic.get("key", ""))
    text = (
        f"Evergreen concept explainer: {title}. Ground every claim in the "
        f"canonical data below and in the published framework at "
        f"{canonical['site']}. If a number is not in the canonical data, "
        f"write around it.\n\nCANONICAL DATA:\n{json.dumps(canonical, indent=2)}"
    )
    return text, f"https://{canonical['site']}"
