import json
from pathlib import Path

from tiktok import MAX_CAPTION, build_post_payload, enabled

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = json.loads((ROOT / "config" / "settings.json").read_text())


def test_payload_always_discloses_ai():
    payload = build_post_payload("caption", 1_500_000, SETTINGS)
    assert payload["post_info"]["is_aigc"] is True  # §14, non-configurable


def test_payload_defaults_private_until_audit():
    payload = build_post_payload("caption", 1_500_000, {})
    assert payload["post_info"]["privacy_level"] == "SELF_ONLY"


def test_payload_single_chunk_for_small_video():
    payload = build_post_payload("caption", 5_000_000, SETTINGS)
    src = payload["source_info"]
    assert src["video_size"] == 5_000_000
    assert src["chunk_size"] == 5_000_000
    assert src["total_chunk_count"] == 1


def test_caption_truncated_to_tiktok_limit():
    payload = build_post_payload("x" * 5000, 1_000, SETTINGS)
    assert len(payload["post_info"]["title"]) == MAX_CAPTION


def test_enabled_requires_both_setting_and_secret(monkeypatch):
    monkeypatch.delenv("TIKTOK_CLIENT_KEY", raising=False)
    assert not enabled({"tiktok_post": True})
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "k")
    assert enabled({"tiktok_post": True})
    assert not enabled({"tiktok_post": False})
