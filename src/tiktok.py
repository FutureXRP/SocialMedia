"""TikTok Content Posting API — Direct Post integration.

Owner decision 2026-07-05: automated posting replaces the manual-upload
editorial step from the original spec (§13). The QA firewall (src/qa.py) is
now the only gate between generation and publication — it may never be
weakened, and there is still no --skip-qa.

TikTok constraints:
- Requires a developer app (developers.tiktok.com) with the Content Posting
  API product and a one-time OAuth grant from the channel account
  (scripts/tiktok_auth.py walks through it).
- UNAUDITED apps may only post SELF_ONLY (private). After TikTok approves
  the app audit, set settings.tiktok_privacy to "PUBLIC_TO_EVERYONE".
- The AI-generated disclosure (is_aigc) is always sent — §14 requirement,
  matching the burned-in label on every frame.
"""

import math
import os
import time
from pathlib import Path

import requests

API = "https://open.tiktokapis.com/v2"
MAX_CAPTION = 2200
# single-chunk uploads are allowed up to 64MB; our videos are a few MB
MAX_SINGLE_CHUNK = 64_000_000


def enabled(settings):
    return bool(settings.get("tiktok_post")) and bool(os.environ.get("TIKTOK_CLIENT_KEY"))


def refresh_access_token():
    """Exchange the long-lived refresh token for a 24h access token."""
    resp = requests.post(
        f"{API}/oauth/token/",
        data={
            "client_key": os.environ["TIKTOK_CLIENT_KEY"],
            "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
            "grant_type": "refresh_token",
            "refresh_token": os.environ["TIKTOK_REFRESH_TOKEN"],
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"TikTok token refresh failed: {data}")
    new_refresh = data.get("refresh_token")
    if new_refresh and new_refresh != os.environ["TIKTOK_REFRESH_TOKEN"]:
        rotate_refresh_secret(new_refresh)
    return data["access_token"]


def rotate_refresh_secret(new_refresh):
    """TikTok occasionally issues a new refresh token. Persist it back to the
    repo secret so tomorrow's run still authenticates. Needs a PAT with repo
    admin (ACTIONS_ADMIN_PAT) and PyNaCl; otherwise we log instructions —
    never the token itself, since Actions logs are not secret-safe for it."""
    pat = os.environ.get("ACTIONS_ADMIN_PAT")
    repo = os.environ.get("GITHUB_REPOSITORY")
    try:
        from base64 import b64encode
        from nacl import encoding, public
        if not (pat and repo):
            raise RuntimeError("no ACTIONS_ADMIN_PAT configured")
        headers = {"Authorization": f"Bearer {pat}",
                   "Accept": "application/vnd.github+json"}
        key = requests.get(
            f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
            headers=headers, timeout=30).json()
        sealed = public.SealedBox(
            public.PublicKey(key["key"], encoding.Base64Encoder())
        ).encrypt(new_refresh.encode())
        resp = requests.put(
            f"https://api.github.com/repos/{repo}/actions/secrets/TIKTOK_REFRESH_TOKEN",
            headers=headers,
            json={"encrypted_value": b64encode(sealed).decode(),
                  "key_id": key["key_id"]},
            timeout=30)
        resp.raise_for_status()
        print("[tiktok] refresh token rotated and secret updated")
    except Exception as e:
        print(f"[tiktok] WARNING: TikTok issued a new refresh token but the "
              f"secret could not be auto-updated ({e}). Re-run "
              f"scripts/tiktok_auth.py and update TIKTOK_REFRESH_TOKEN "
              f"before it expires.")


def build_post_payload(caption, video_size, settings):
    chunk_size = min(video_size, MAX_SINGLE_CHUNK)
    return {
        "post_info": {
            "title": caption[:MAX_CAPTION],
            "privacy_level": settings.get("tiktok_privacy", "SELF_ONLY"),
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "is_aigc": True,  # §14: AI-content disclosure, non-configurable
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": chunk_size,
            "total_chunk_count": math.ceil(video_size / chunk_size),
        },
    }


def post_video(mp4_path, caption, settings):
    """Direct-post the MP4. Returns (publish_id, final_status)."""
    token = refresh_access_token()
    auth = {"Authorization": f"Bearer {token}"}
    mp4_path = Path(mp4_path)
    size = mp4_path.stat().st_size

    init = requests.post(
        f"{API}/post/publish/video/init/",
        headers={**auth, "Content-Type": "application/json"},
        json=build_post_payload(caption, size, settings),
        timeout=60,
    )
    init.raise_for_status()
    data = init.json().get("data", {})
    upload_url, publish_id = data.get("upload_url"), data.get("publish_id")
    if not upload_url or not publish_id:
        raise RuntimeError(f"TikTok init failed: {init.json()}")

    up = requests.put(
        upload_url,
        data=mp4_path.read_bytes(),
        headers={"Content-Type": "video/mp4",
                 "Content-Range": f"bytes 0-{size - 1}/{size}"},
        timeout=600,
    )
    up.raise_for_status()

    deadline = time.time() + 600
    while time.time() < deadline:
        st = requests.post(
            f"{API}/post/publish/status/fetch/",
            headers={**auth, "Content-Type": "application/json"},
            json={"publish_id": publish_id},
            timeout=60,
        )
        st.raise_for_status()
        status = st.json().get("data", {}).get("status", "")
        if status == "PUBLISH_COMPLETE":
            return publish_id, status
        if status in ("FAILED", "SEND_TO_USER_INBOX_FAILED"):
            raise RuntimeError(f"TikTok publish failed: {st.json()}")
        time.sleep(10)
    raise RuntimeError(f"TikTok publish timed out; publish_id={publish_id}")
