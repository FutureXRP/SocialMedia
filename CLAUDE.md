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
