"""Stage 7 — delivery: GitHub Release with artifacts, optional Resend email,
history record, topics ledger update."""

import json
import os
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
HISTORY_DIR = ROOT / "data" / "history"

GITHUB_API = "https://api.github.com"

AI_LABEL_REMINDER = (
    "Reminder: when posting, ALSO toggle TikTok's native "
    '"AI-generated content" label.'
)


def _gh_headers():
    return {
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
    }


def _free_tag(repo, base):
    """First unused tag: video-DATE, then video-DATE-2, -3 ... (two builds
    per day must not collide)."""
    tag, n = base, 1
    while True:
        r = requests.get(f"{GITHUB_API}/repos/{repo}/releases/tags/{tag}",
                         headers=_gh_headers(), timeout=30)
        if r.status_code == 404:
            return tag
        n += 1
        tag = f"{base}-{n}"


def create_release(run_date, mp4_path, caption_path, script, format_key,
                   source_url, duration):
    """Create GitHub Release video-YYYY-MM-DD[-N] and attach MP4 + caption."""
    repo = os.environ["GITHUB_REPOSITORY"]
    tag = _free_tag(repo, f"video-{run_date.isoformat()}")
    body = (
        f"**Hook:** {script.get('hook', '')}\n\n"
        f"**Duration:** {duration:.0f}s\n"
        f"**Format:** {format_key}\n"
        f"**Source:** {source_url}\n\n"
        f"{AI_LABEL_REMINDER}\n"
    )
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo}/releases", headers=_gh_headers(),
        json={"tag_name": tag, "name": tag, "body": body}, timeout=60,
    )
    resp.raise_for_status()
    release = resp.json()

    for path, content_type in ((mp4_path, "video/mp4"), (caption_path, "text/plain")):
        path = Path(path)
        upload_url = release["upload_url"].split("{")[0]
        with path.open("rb") as f:
            up = requests.post(
                upload_url, params={"name": path.name},
                headers={**_gh_headers(), "Content-Type": content_type},
                data=f, timeout=600,
            )
        up.raise_for_status()
    return release["html_url"]


def open_notice_issue(title, body):
    """Non-fatal notice (e.g. TikTok post failed but the video exists) —
    the run continues, but nothing fails silently."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo or not os.environ.get("GITHUB_TOKEN"):
        print(f"[deliver] NOTICE (no GitHub context): {title}\n{body}")
        return
    requests.post(f"{GITHUB_API}/repos/{repo}/issues", headers=_gh_headers(),
                  json={"title": title, "body": body}, timeout=60).raise_for_status()


def send_email(release_url, caption_text, run_date):
    """Send the release link (NOT the file — too large) via Resend."""
    api_key = os.environ.get("RESEND_API_KEY")
    to_addr = os.environ.get("DELIVERY_EMAIL")
    if not api_key or not to_addr:
        return False
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "from": "xrpv-daily-video <onboarding@resend.dev>",
            "to": [to_addr],
            "subject": f"Daily video ready — {run_date.isoformat()}",
            "text": (
                f"Today's video: {release_url}\n\n{AI_LABEL_REMINDER}\n\n"
                f"Caption (paste into TikTok):\n\n{caption_text}\n"
            ),
        },
        timeout=60,
    )
    resp.raise_for_status()
    return True


def write_history(run_date, topic, format_key, script, qa_verdicts, durations,
                  render_seconds):
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "date": run_date.isoformat(),
        "topic": topic,
        "format": format_key,
        "script": script,
        "qa_verdicts": qa_verdicts,
        "durations": durations,
        "word_count": sum(len(s.get("voiceover", "").split())
                          for s in script.get("segments", [])),
        "render_seconds": round(render_seconds, 1),
    }
    path = HISTORY_DIR / f"{run_date.isoformat()}.json"
    n = 1
    while path.exists():  # second build of the day must not overwrite the first
        n += 1
        path = HISTORY_DIR / f"{run_date.isoformat()}-{n}.json"
    path.write_text(json.dumps(record, indent=2) + "\n")
    return str(path)


def recent_titles(limit=14):
    """Last N video titles from history, newest first, for repetition avoidance."""
    records = sorted(HISTORY_DIR.glob("*.json"), reverse=True)[:limit]
    titles = []
    for rec in records:
        try:
            titles.append(json.loads(rec.read_text())["script"]["title"])
        except (KeyError, json.JSONDecodeError):
            continue
    return titles
