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


def merge_feeds(feed_lists):
    """Merge multiple posts.json feeds, deduped by slug, first feed wins.
    Order within each feed is preserved (feeds are newest-first)."""
    merged, seen = [], set()
    for posts in feed_lists:
        for p in posts:
            slug = p.get("slug")
            if slug and slug not in seen:
                seen.add(slug)
                merged.append(p)
    return merged


def fetch_posts(settings):
    """Fetch every configured feed (blog, and any Observatory / Field Notes /
    series feeds Matt adds to settings.feeds); a dead feed is not fatal —
    the evergreen queue covers it."""
    feeds = settings.get("feeds") or [settings["posts_json_url"]]
    lists = []
    for url in feeds:
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            posts = resp.json()
            lists.append(posts if isinstance(posts, list) else posts.get("posts", []))
        except Exception:
            continue
    return merge_feeds(lists)


def strip_html(html):
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def fetch_page_text(url):
    """Fetch any page and strip to plain text."""
    resp = requests.get(url, timeout=30,
                        headers={"User-Agent": "xrpv-daily-video/1.0"})
    resp.raise_for_status()
    return strip_html(resp.text)


def fetch_post_text(slug, settings):
    """Fetch a post's HTML and strip to plain text (the site is static HTML)."""
    url = settings["post_url_pattern"].format(slug=slug)
    return fetch_page_text(url), url


def check_external_domain(url, settings):
    """External topics may only cite allowlisted institutions — the brand is
    verifiable accuracy, so sources are curated, never arbitrary."""
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    allowed = settings.get("external_domains", [])
    if not any(host == d or host.endswith("." + d) for d in allowed):
        raise ValueError(
            f"external source domain not allowlisted: {host!r} — add it to "
            f"settings.external_domains if it belongs")


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


def select_topic(topics, posts, today=None, override=None, exclude=()):
    """Apply the selection rules and return the chosen topic dict.

    - New posts in posts.json jump the queue.
    - Never the same topic within 14 days.
    - Never two non-post videos (evergreen/feature/external) back-to-back
      if an unused post exists.
    - `exclude`: topic keys to skip this run (e.g. fetch failed).
    """
    today = today or date.today()

    if override:
        if any(p.get("slug") == override for p in posts):
            return {"type": "post", "slug": override}
        for cand in topics.get("queue", []):
            if _topic_key(cand) == override:
                return cand
        return {"type": "evergreen", "key": override, "title": override}

    used_keys = {e["key"] for e in topics.get("used", [])}
    fresh_posts = [
        {"type": "post", "slug": p["slug"], "title": p.get("title", p["slug"])}
        for p in posts
        if p.get("slug") and p["slug"] not in used_keys and p["slug"] not in exclude
    ]  # posts.json is newest-first; keep that order

    for cand in fresh_posts:
        if not _used_recently(topics, cand["slug"], today):
            return cand

    variety_ok = not (fresh_posts and _last_used_type(topics) != "post")
    if variety_ok:
        for cand in topics.get("queue", []):
            key = _topic_key(cand)
            if key not in exclude and not _used_recently(topics, key, today):
                return cand

    # queue exhausted: recycle the least-recently-used evergreen
    for entry in topics.get("used", []):
        if entry.get("type") == "evergreen" and entry["key"] not in exclude \
                and not _used_recently(topics, entry["key"], today):
            return {"type": "evergreen", "key": entry["key"],
                    "title": entry.get("title", entry["key"])}
    # last resort: a missed daily video is worse than bending the 14-day
    # rotation rule (matters at 2 videos/day) — take the stalest used
    # evergreen even if it ran recently
    stale = sorted((e for e in topics.get("used", [])
                    if e.get("type") == "evergreen" and e["key"] not in exclude),
                   key=lambda e: e.get("date", ""))
    if stale:
        entry = stale[0]
        return {"type": "evergreen", "key": entry["key"],
                "title": entry.get("title", entry["key"])}
    raise RuntimeError("no eligible topic: queue empty and nothing recyclable")


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
    """Return (source_text, source_url, source_kind) for the scriptwriter.

    Kinds: post (site article), evergreen (concept from canonical data),
    feature (the Settlement Terminal or the calculator page), external
    (allowlisted institutional document — BIS, IMF, Fed, etc.).
    """
    canonical = load_canonical()
    kind = topic["type"]

    if kind == "post":
        text, url = fetch_post_text(topic["slug"], settings)
    elif kind == "feature":
        url = settings.get("features", {}).get(topic["key"])
        if not url:
            raise ValueError(f"no URL configured for feature {topic['key']!r} "
                             f"in settings.features")
        page = fetch_page_text(url)
        text = (f"Site feature page ({topic.get('title', topic['key'])}) at "
                f"{url}:\n\n{page}\n\nCANONICAL DATA:\n"
                f"{json.dumps(canonical, indent=2)}")
    elif kind == "external":
        url = topic["url"]
        check_external_domain(url, settings)
        text = fetch_page_text(url)
    else:  # evergreen
        title = topic.get("title", topic.get("key", ""))
        url = f"https://{canonical['site']}"
        text = (
            f"Evergreen concept explainer: {title}. Ground every claim in the "
            f"canonical data below and in the published framework at "
            f"{canonical['site']}. If a number is not in the canonical data, "
            f"write around it.\n\nCANONICAL DATA:\n{json.dumps(canonical, indent=2)}"
        )

    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words])
    return text, url, kind
