#!/usr/bin/env python3
"""One-time TikTok OAuth: obtain the refresh token for the pipeline.

Prerequisites (developers.tiktok.com):
1. Create an app, add the "Content Posting API" product, request the
   video.publish scope (user.info.basic comes along).
2. Register a redirect URI on the app (any https URL you control works —
   you only need to copy the code out of the address bar).
3. Note the Client key and Client secret.

Run:
    python scripts/tiktok_auth.py --client-key KEY --client-secret SECRET \
        --redirect-uri https://your.registered/redirect

Then log in as the CHANNEL account when the browser opens, approve, and
paste the full redirect URL back here. The printed refresh token goes into
the TIKTOK_REFRESH_TOKEN repo secret (with TIKTOK_CLIENT_KEY and
TIKTOK_CLIENT_SECRET).
"""

import argparse
import secrets
import urllib.parse

import requests

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
SCOPES = "user.info.basic,video.publish"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-key", required=True)
    ap.add_argument("--client-secret", required=True)
    ap.add_argument("--redirect-uri", required=True,
                    help="must exactly match a redirect URI registered on the app")
    args = ap.parse_args()

    state = secrets.token_urlsafe(16)
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_key": args.client_key,
        "response_type": "code",
        "scope": SCOPES,
        "redirect_uri": args.redirect_uri,
        "state": state,
    })
    print("\n1. Open this URL in a browser, logged in as the channel account:\n")
    print(url)
    print("\n2. Approve, then copy the FULL URL you were redirected to.\n")
    redirected = input("Paste redirect URL: ").strip()

    q = urllib.parse.parse_qs(urllib.parse.urlparse(redirected).query)
    if q.get("state", [None])[0] != state:
        raise SystemExit("state mismatch — restart the flow")
    code = q["code"][0]

    resp = requests.post(TOKEN_URL, data={
        "client_key": args.client_key,
        "client_secret": args.client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": args.redirect_uri,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=60)
    data = resp.json()
    if "refresh_token" not in data:
        raise SystemExit(f"token exchange failed: {data}")

    print("\nSuccess. Add these GitHub repo secrets (Settings → Secrets → Actions):")
    print(f"  TIKTOK_CLIENT_KEY     = {args.client_key}")
    print("  TIKTOK_CLIENT_SECRET  = (your client secret)")
    print(f"  TIKTOK_REFRESH_TOKEN  = {data['refresh_token']}")
    print(f"\nGranted scopes: {data.get('scope')}")
    print("Then set \"tiktok_post\": true in config/settings.json.")


if __name__ == "__main__":
    main()
