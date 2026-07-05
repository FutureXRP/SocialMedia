# xrpv-daily-video — pointer for future sessions

The full build framework lives in **`readme.md`** (XRPV_DAILY_VIDEO.md). Read
it before changing anything; its truth rules and the QA firewall (§7/§14) are
non-negotiable. Highlights:

- **What this is:** nightly GitHub Actions pipeline producing one 60–300s
  vertical MP4 (1080×1920, 30fps) with ElevenLabs voiceover and burned-in
  captions, plus a caption `.txt`. Matt uploads to TikTok manually — there is
  NO TikTok API and never will be.
- **Never fabricate a number.** Every spoken figure must trace to
  `data/canonical.json` or the fetched post. Enforced in `src/qa.py`
  (programmatic) + `prompts/qa_reviewer.md` (LLM pass). No `--skip-qa` exists.
- **Pipeline:** `content.py` → `script.py` (Anthropic) → `qa.py` (retry once,
  then abort) → `voice.py` (ElevenLabs with-timestamps) → `render.py` +
  `src/scenes/` (Pillow, 9 scene templates) → `captions.py` → `assemble.py`
  (ffmpeg) → `deliver.py` (Release + optional Resend email + history).
- **Em dashes are stripped from voiceover text** before TTS
  (`script.sanitize_voiceover_text`) — ElevenLabs alignment drift.

## Build status (2026-07-04)

- Phase 1 (render engine): **done** — `python src/main.py --fixture
  tests/fixture_script.json --no-voice` produces a silent MP4.
- Phase 2 (voice + captions): **code complete** — alignment parsing and
  phrase sync implemented and unit-tested against synthetic alignments;
  needs a live ELEVENLABS_API_KEY run and a chosen voice ID in
  `config/settings.json` (pick once, never change).
- Phase 3 (script gen + QA): **code complete** — needs a live
  ANTHROPIC_API_KEY end-to-end run against real posts.json.
- Phase 4 (orchestration + delivery): **code complete** —
  `.github/workflows/daily-video.yml`; needs repo secrets set and a
  `workflow_dispatch` verification run.
- Phase 5 (format library): **done** — all 9 scenes, formats.json rotation,
  evergreen queue seeded.

Tests: `python -m pytest tests/`. Fixture render: see Phase 1 command above.

## Post-launch tuning (2026-07-04, after first live runs)

- **Duration is a contract:** a workflow duration input filters the format
  rotation to formats whose range contains it, the scriptwriter gets a hard
  word budget, and `qa.check_pacing` rejects scripts outside ±20-25% of it.
- **Cost controls:** QA runs on `qa_model` (Haiku), source truncates to
  `source_max_words` (2500), TTS uses `eleven_flash_v2_5` (half credits).
- **Retail-investor voice:** scriptwriter prompt targets 8th-grade reading
  level, jargon banned unless immediately explained, one analogy per video.
- **Look:** narrative text is DejaVu Sans; mono is reserved for chrome,
  numbers, and the URL. Rounded panels + dot grid replaced the crosshatch.

## Source expansion (2026-07-05)

Topic types: `post` (any article from `settings.feeds` — add Observatory /
Field Notes / series feeds there as they get their own posts.json),
`evergreen`, `feature` (terminal, calculator — URLs in `settings.features`),
`external` (BIS/IMF/Fed/etc — MUST be on `settings.external_domains`
allowlist; scriptwriter attributes by name and never implies endorsement).

To queue an external article, add to `data/topics.json` queue:
`{"type": "external", "key": "bis-agora-2026", "title": "...",
  "url": "https://www.bis.org/..."}` — optional `"format_hint"` pins a
format. Unfetchable topics are skipped (up to 4) instead of failing the run.
NOTE: verify `settings.features` URLs match the live site paths — they were
seeded as best guesses (/terminal, /calculator).

## TikTok auto-posting (2026-07-05, owner overrode spec §13)

`src/tiktok.py` direct-posts via the official Content Posting API after the
Release. Gated on `settings.tiktok_post` + `TIKTOK_CLIENT_KEY` secret.
One-time setup: developer app at developers.tiktok.com → run
`scripts/tiktok_auth.py` → add TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET /
TIKTOK_REFRESH_TOKEN secrets. Unaudited apps post SELF_ONLY (private);
after TikTok audit approval set `settings.tiktok_privacy` to
"PUBLIC_TO_EVERYONE". `is_aigc` is always sent (§14). A failed post opens a
notice Issue but does not fail the run. The QA firewall is now the ONLY
editorial gate — never weaken it.
