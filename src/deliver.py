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


def create_release(run_date, mp4_path, caption_path, script, format_key,
                   source_url, duration):
    """Create GitHub Release video-YYYY-MM-DD and attach MP4 + caption txt."""
    repo = os.environ["GITHUB_REPOSITORY"]
    tag = f"video-{run_date.isoformat()}"
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
