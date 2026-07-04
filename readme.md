# XRPV_DAILY_VIDEO.md — Build Framework for Claude Code

**Project:** Automated daily short-form video generator for xrpvaluation.info
**Owner:** Matt Blair (GitHub: FutureXRP)
**Deliverable per run:** One 60–300 second vertical MP4 (1080×1920, 30fps, H.264 + AAC) with synced voiceover and burned-in captions, plus a ready-to-paste caption/hashtag text file. Human uploads to TikTok manually — there is NO TikTok API integration in this project. Do not build one.

---

## 1. PURPOSE AND PHILOSOPHY

This repo turns published xrpvaluation.info analysis into a daily vertical video, fully unattended. The pipeline runs nightly on GitHub Actions. Every morning Matt receives a finished video, watches it once as editorial review, and posts it himself from the TikTok app.

Non-negotiable principles, in priority order:

1. **Never fabricate a number.** Every statistic, price, or figure spoken in a video must originate from a data file in this repo or from published xrpvaluation.info content. The script generator is forbidden from inventing data. If a needed number is unavailable, the script must omit it, not estimate it.
2. **Research, not investment advice.** Every video ends with the disclaimer. No price predictions framed as certainty. The $589 figure, when used, is always described as "a derived anchor from published inputs" or similar — never "XRP will hit $589."
3. **Falsifiability is the brand.** The channel's differentiator is "every input is published — check the math." Scripts should invite scrutiny, not discourage it.
4. **Voice discipline.** Short declarative bursts. Rhetorical questions as scalpel, not filler. Confession before accusation. Register shifts between clinical and pastoral. No crypto-bro hype vocabulary (no "moon," "pump," "1000x," "WAGMI," "don't miss out").
5. **Copyright discipline.** Maximum one short direct quote (<15 words) per external source per script. Paraphrase everything else. Never reproduce chart images or text from BIS, Ripple, or news sources — describe and attribute.

---

## 2. REPO STRUCTURE

```
xrpv-daily-video/
├── .github/
│   └── workflows/
│       └── daily-video.yml          # nightly cron
├── config/
│   ├── brand.json                   # colors, fonts, layout tokens
│   ├── formats.json                 # format rotation schedule + weights
│   └── settings.json                # video length target, voice ID, delivery mode
├── data/
│   ├── canonical.json               # framework constants (see §5.3)
│   ├── topics.json                  # topic queue + used-topic ledger
│   └── history/                     # one JSON record per produced video
├── prompts/
│   ├── scriptwriter.md              # system prompt for Anthropic API (see §6)
│   └── qa_reviewer.md               # second-pass validation prompt (see §7)
├── src/
│   ├── main.py                      # orchestrator, entry point
│   ├── content.py                   # fetch + select source material
│   ├── script.py                    # Anthropic API script generation
│   ├── qa.py                        # script validation pass
│   ├── voice.py                     # ElevenLabs TTS with timestamps
│   ├── render.py                    # frame renderer (Pillow)
│   ├── scenes/                      # one module per scene template
│   │   ├── __init__.py
│   │   ├── hook_typewriter.py
│   │   ├── stat_counter.py
│   │   ├── declaration.py
│   │   ├── chart_sqrt.py
│   │   ├── chart_bar.py
│   │   ├── chart_line.py
│   │   ├── quote_card.py
│   │   ├── list_reveal.py
│   │   └── cta_card.py
│   ├── captions.py                  # timestamp → phrase caption mapping
│   ├── assemble.py                  # ffmpeg frame+audio mux
│   └── deliver.py                   # GitHub Release + email delivery
├── assets/
│   ├── fonts/                       # bundled DejaVu Sans Mono (regular + bold)
│   └── audio/                       # optional ambient bed loops (royalty-free only)
├── output/                          # gitignored; per-run artifacts land here
├── tests/
│   ├── test_qa.py
│   ├── test_captions.py
│   └── test_render_smoke.py
├── requirements.txt
├── README.md
└── CLAUDE.md                        # condensed pointer to this file for future sessions
```

---

## 3. TECH STACK

- **Python 3.11+.** Dependencies: `Pillow`, `requests`, `anthropic`, `numpy` (chart math only). No moviepy. No heavy frameworks.
- **ffmpeg** (available on ubuntu-latest runners) for encoding and audio mux.
- **GitHub Actions** ubuntu-latest, nightly cron.
- **Anthropic API** — model `claude-sonnet-4-6` for both scriptwriter and QA passes.
- **ElevenLabs API** — `POST /v1/text-to-speech/{voice_id}/with-timestamps` to get MP3 + character-level alignment in one call.
- **No database.** State lives in JSON files committed back to the repo by the workflow (topics ledger, history).

---

## 4. GITHUB ACTIONS WORKFLOW

File: `.github/workflows/daily-video.yml`

- **Trigger:** `schedule: cron "0 7 * * *"` (07:00 UTC = 1–2 AM Tulsa) plus `workflow_dispatch` with optional inputs: `topic_override` (string), `duration_target` (60/120/180/300), `format_override` (scene format key).
- **Steps:**
  1. Checkout with a PAT or `GITHUB_TOKEN` that permits pushing (topics ledger + history get committed back).
  2. Setup Python 3.11, `pip install -r requirements.txt`, `sudo apt-get install -y ffmpeg` (or verify preinstalled).
  3. Run `python src/main.py`.
  4. On success: create a GitHub Release tagged `video-YYYY-MM-DD` with the MP4 and caption `.txt` attached; commit the updated `data/topics.json` and `data/history/YYYY-MM-DD.json`.
  5. If `settings.json` has `"email_delivery": true`, `deliver.py` also sends the release link (NOT the file — too large) via Resend to the configured address with the caption text inline.
  6. On failure at any stage: open a GitHub Issue titled `Video run failed YYYY-MM-DD` containing the stage name and error, so nothing fails silently.
- **Secrets required:** `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `RESEND_API_KEY` (optional), `DELIVERY_EMAIL` (optional).
- **Timeout:** 30 minutes. Concurrency group `daily-video` with cancel-in-progress false.

---

## 5. STAGE 1 — CONTENT SELECTION (`content.py`)

### 5.1 Sources, in priority order
1. `https://xrpvaluation.info/blog/posts.json` — the live feed. Fetch fresh each run.
2. Individual post HTML at `https://xrpvaluation.info/blog/<slug>` — fetch the selected post, strip to plain text (simple tag removal is fine; the site is static HTML).
3. `data/canonical.json` — framework constants (below).
4. `data/topics.json` — evergreen topic queue.

All site links referenced in captions or scripts use `/blog/` paths. Never `/field-notes/`.

### 5.2 Selection logic
- Maintain `data/topics.json` with two arrays: `queue` (unused topic objects) and `used` (topic key + date used).
- A topic is one of: `{"type": "post", "slug": ...}` (drawn from posts.json, newest unused first) or `{"type": "evergreen", "key": ...}` (concept explainers: DvP, nostro/vostro, atomic settlement, bridge asset mechanics, square-root impact law, stablecoin insufficiency, collateral migration, the inter-bloc seam, Project Agorá, ODL corridors, escrow mechanics, the settlement problem itself).
- Rotation rule: never the same topic within 14 days; never two evergreen concept videos back-to-back if an unused post exists.
- New posts in posts.json jump the queue — a fresh Field Note or Observatory piece always becomes the next video.

### 5.3 `data/canonical.json` — seed with these values (Matt updates over time)
```json
{
  "sqrt_anchor": {
    "value_usd": 589,
    "inputs": { "Q_daily_usd": "2000000000", "sigma": "0.005",
                "slippage_bps": 5, "turnover": "0.0136", "float": "25000000000" },
    "framing_rule": "Always 'derived anchor from published inputs', never a prediction."
  },
  "rlusd_market_cap_usd": "1.26B (Ripple Impact Report 2025)",
  "xrpl_cumulative_volume_usd": "1.5T (Ripple Impact Report 2025)",
  "rwa_tokenization_growth": "24.7M to 568M (Ripple Impact Report 2025)",
  "agora_central_banks": 7,
  "nostro_parked_estimate": "4T+ (industry estimates; verify before use in scripts)",
  "site": "xrpvaluation.info",
  "handle": "@the5blairs"
}
```
Every number a script may speak MUST resolve to a key in this file or to text in the fetched post. This is enforced in the QA stage.

---

## 6. STAGE 2 — SCRIPT GENERATION (`script.py` + `prompts/scriptwriter.md`)

One Anthropic API call. Temperature 1.0 is fine; discipline comes from the prompt and the QA pass, not sampling.

### 6.1 The scriptwriter system prompt (write `prompts/scriptwriter.md` with this content, verbatim intent)

```
You are the scriptwriter for the xrpvaluation.info daily video. You write
voiceover scripts for 60–300 second vertical videos about cross-border
settlement, bridge-asset economics, and the published XRP valuation framework.

VOICE
- Short declarative bursts. Vary sentence length, but let short win.
- Rhetorical questions are a scalpel. One or two per script, maximum.
- Confession before accusation: acknowledge what skeptics get right
  before making the framework's case.
- Register shifts: clinical when handling numbers, plain and human when
  handling stakes.
- Plain English. Every technical term gets a one-clause explanation on
  first use. Write for a smart person who knows nothing about crypto.
- Deliberate repetition is allowed as a rhetorical device.
- FORBIDDEN vocabulary: moon, pump, dump, ape, WAGMI, NGMI, 100x, 1000x,
  "trust me", "guaranteed", "about to explode", "last chance", "financial
  freedom", any urgency-to-buy framing.

TRUTH RULES (violations are build failures, not style notes)
- Use ONLY numbers present in the SOURCE MATERIAL or CANONICAL DATA blocks
  provided in the user message. If you need a number you don't have, write
  around it.
- The $589 figure, if used, is always "a derived anchor from published
  inputs" — never a prediction, target, or promise.
- Maximum one direct quote per external source, under 15 words. Prefer
  paraphrase with attribution ("the BIS's 2026 annual report describes...").
- The script must be consistent with the source post. Do not extend its
  claims beyond what it argues.
- Never give buying, selling, or timing advice.

STRUCTURE
Return ONLY valid JSON, no markdown fences, matching this schema:
{
  "title": "internal slug, kebab-case",
  "hook": "first 1–2 sentences; must earn the next 3 seconds",
  "segments": [
    { "scene": "<scene template key>", "voiceover": "...",
      "display": { ...scene-specific fields, see SCENE CONTRACTS... } }
  ],
  "cta_voiceover": "closing lines directing to xrpvaluation.info",
  "caption_text": "TikTok caption, <=150 words, 3–5 hashtags, includes
                   'Research, not investment advice.'",
  "spoken_numbers": ["every numeric claim in the script, verbatim, one per entry"]
}

SCENE CONTRACTS (the "display" object per scene key)
- hook_typewriter: { "line": string }
- stat_counter:    { "label": string, "value": string, "beats": [up to 3 short lines] }
- declaration:     { "lines": [1–3 short lines], "emphasis_index": int }
- chart_sqrt:      { "annotation": string, "sub_lines": [up to 2] }
- chart_bar:       { "title": string, "bars": [{"label","value_display","value_norm 0–1"}] (2–5) }
- chart_line:      { "title": string, "points": [{"label","value_norm 0–1"}] (4–10), "annotation": string }
- quote_card:      { "quote": string (<15 words), "attribution": string }
- list_reveal:     { "title": string, "items": [2–5 short strings] }
- cta_card:        { "headline": string, "site": "xrpvaluation.info" }

PACING
- Voiceover totals must fit the DURATION TARGET at ~150 words/minute.
- First segment is always hook_typewriter. Last is always cta_card.
- 4–8 segments for 60–120s; 8–14 for 180–300s.
- Every segment's voiceover must stand alone if someone scrolls in mid-video.
```

### 6.2 The user message assembled by `script.py`
Contains labeled blocks: `DURATION TARGET`, `FORMAT` (today's rotation pick from `formats.json`), `SOURCE MATERIAL` (the fetched post text, truncated to ~6,000 words), `CANONICAL DATA` (contents of canonical.json), and `RECENT VIDEO TITLES` (last 14 from history, to avoid repetition).

### 6.3 Format rotation (`config/formats.json`)
Four formats with weekday weighting Matt can tune:
- `field_note_explainer` — walk one post's core argument (longer, 180–300s)
- `one_chart_one_claim` — single data moment, tight (60–90s)
- `term_of_the_day` — one concept from the evergreen list (60–120s)
- `terminal_reading` — "what the Settlement Terminal shows this week" style (90–150s)

---

## 7. STAGE 3 — QA PASS (`qa.py` + `prompts/qa_reviewer.md`)

A second, independent Anthropic API call. The QA prompt receives the script JSON, the source material, and canonical.json, and returns `{"verdict": "pass" | "fail", "violations": [...]}` checking:

1. Every entry in `spoken_numbers` appears in source material or canonical.json (also verify programmatically in Python with normalized string matching — the LLM check is belt, the code check is suspenders).
2. No forbidden vocabulary (also checked programmatically against a word list in `qa.py`).
3. $589 framing rule respected if the number appears.
4. No more than one direct quote per source; no quote ≥15 words.
5. Disclaimer present in caption_text.
6. Schema validity (programmatic, before the LLM pass).

**On fail:** one retry — regenerate the script with the violations appended to the user message. If the retry fails QA, abort the run and open the failure Issue with both violation lists. Never render a script that failed QA. This is the editorial firewall and it is load-bearing.

---

## 8. STAGE 4 — VOICEOVER (`voice.py`)

- Concatenate segment voiceovers with `\n\n` between segments (ElevenLabs treats these as natural pauses). Keep a char-offset map of where each segment starts in the concatenated string.
- Call `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps` with `model_id: "eleven_multilingual_v2"` (or current best; make it a settings.json field), `output_format: "mp3_44100_128"`.
- Response contains base64 audio + `alignment` with `characters`, `character_start_times_seconds`, `character_end_times_seconds`. Persist both raw response and decoded MP3 to `output/`.
- **No em dashes in voiceover text** — same ElevenLabs alignment-drift issue discovered on Footsteps. `script.py` sanitizes: em/en dashes in voiceover fields become commas or periods before TTS. (Display fields may keep them.)
- Derive per-segment start/end times from the char-offset map + alignment. These drive scene durations in the render.
- Voice ID lives in `config/settings.json`. Pick one voice and never change it — it becomes the channel's identity.

---

## 9. STAGE 5 — RENDER (`render.py` + `src/scenes/`)

### 9.1 Brand tokens (`config/brand.json`) — the approved sample aesthetic
```json
{
  "canvas": [1080, 1920], "fps": 30,
  "colors": {
    "bg": [8, 11, 17], "panel": [13, 18, 27], "grid": [24, 32, 44],
    "ink": [222, 230, 238], "dim": [110, 124, 140],
    "green": [61, 220, 132], "amber": [255, 184, 76], "red": [255, 99, 92]
  },
  "font": "DejaVuSansMono",
  "chrome": {
    "header": "XRPVALUATION.INFO // OBSERVATORY",
    "subheader_pattern": "{SERIES} — DAILY BRIEF",
    "ai_label": "AI-GENERATED",
    "progress_bar": true
  },
  "safe_zones": { "top_px": 260, "bottom_px": 400, "sides_px": 60 }
}
```
Every frame carries: header chrome bar with green status dot, the AI-GENERATED label top-right (TikTok's AI-content disclosure — always on, non-configurable), a bottom progress bar keyed to global time, and the caption panel in the lower third. Respect safe zones — TikTok UI overlays the right edge and bottom.

### 9.2 Scene modules
Each scene module exposes `render(draw, t_local, duration, display, ctx)` and draws one frame. Implement the nine templates from the scene contracts (§6.1). The five from the approved sample (hook_typewriter, stat_counter, declaration, chart_sqrt, cta_card) match the sample render's look; add chart_bar, chart_line, quote_card, list_reveal in the same visual language. Animation rules:
- Smoothstep easing everywhere; nothing pops in.
- Text reveals: typewriter for hooks, fade+settle for everything else.
- Charts draw on over ~2.4s.
- Blinking cursor at 2Hz on typewriter scenes.
- Emphasis color: green for thesis lines, amber for data, red used at most once per video.

### 9.3 Captions (`captions.py`)
- Split each segment's voiceover into phrases of 3–7 words at natural boundaries (punctuation first, then length).
- Map each phrase to start/end times via the ElevenLabs character alignment (binary search over character_start_times — port the Footsteps approach).
- The active phrase renders in the caption panel; it should change exactly when the voice reaches it. This burned-in sync is the single biggest watchability lever — get it right before polishing anything else.

### 9.4 Performance
- Scene durations come from actual voiceover timing (§8), not fixed lengths.
- Render frames as PNG to a temp dir; a 5-minute video is 9,000 frames — precompute each scene's static background once and paste per frame, drawing only animated elements. Target: full render under 15 minutes on a GitHub runner. If it can't hit that, drop to drawing JPEG frames at quality 92.

---

## 10. STAGE 6 — ASSEMBLE (`assemble.py`)

```
ffmpeg -y -framerate 30 -i frames/f%06d.png -i voiceover.mp3
  -c:v libx264 -pix_fmt yuv420p -crf 21 -preset medium
  -c:a aac -b:a 160k -shortest -movflags +faststart output/xrpv_YYYY-MM-DD.mp4
```
- If `assets/audio/` contains an ambient bed and settings enable it, duck it under the voice at -22dB with `amix`. Only royalty-free/owned audio ever ships in this repo — no exceptions, no "probably fine" clips.
- Also write `output/xrpv_YYYY-MM-DD_caption.txt` containing the caption_text from the script.

---

## 11. STAGE 7 — DELIVER (`deliver.py`) + HISTORY

- Create GitHub Release `video-YYYY-MM-DD`, attach MP4 + caption txt. Release body: the hook, duration, format used, source post link.
- Optional Resend email with the release link and caption text inline.
- Write `data/history/YYYY-MM-DD.json`: topic, format, script JSON, QA verdicts, durations, word count, render time. Move the topic from queue → used in topics.json. Commit both.

---

## 12. BUILD ORDER FOR CLAUDE CODE

Build and verify in this sequence; each phase has a runnable acceptance test.

1. **Phase 1 — Render engine.** Scene modules + brand tokens + a hardcoded fixture script JSON. Acceptance: `python src/main.py --fixture tests/fixture_script.json --no-voice` produces a silent MP4 visually matching the approved sample aesthetic.
2. **Phase 2 — Voice + captions.** ElevenLabs integration, alignment parsing, phrase caption sync, em-dash sanitization. Acceptance: fixture script renders WITH voice and captions change within ±100ms of the spoken phrase (spot-check 5 phrases against the alignment data in a unit test).
3. **Phase 3 — Script generation + QA.** content.py, script.py, qa.py, both prompts. Acceptance: end-to-end run with `--topic-override` produces a QA-passing script from a real posts.json entry; a deliberately poisoned fixture (fabricated number, forbidden word) fails QA in tests.
4. **Phase 4 — Orchestration + delivery.** main.py wiring, workflow YAML, Release creation, failure Issues, history commits. Acceptance: `workflow_dispatch` run on GitHub completes and attaches artifacts to a Release.
5. **Phase 5 — Format library.** Remaining scene templates, formats.json rotation, evergreen topic queue seeded with the concepts in §5.2.

Conventions: complete file replacements over surgical patches when revising; one batch commit per working session; ship-first then iterate. Keep CLAUDE.md updated as a one-page pointer to this document plus current build status.

---

## 13. EXPLICIT NON-GOALS

- No TikTok API, no OAuth, no third-party posting wrapper. Manual upload is the editorial review step, by design.
- No autoposting to any platform. (The MP4 is 9:16 and equally uploadable to Shorts/Reels by hand.)
- No Higgsfield/generative video in v1. The scene system is deterministic and cheap. A `broll` scene type that overlays a provided MP4 clip may be added in v2 — leave a stub comment in scenes/__init__.py.
- No live price data in v1. Prices go stale between render (2 AM) and post (morning); the framework's content doesn't need them.
- No per-video human configuration. If the pipeline needs Matt's input to run, the build has failed its one requirement.

---

## 14. DISCLOSURE AND SAFETY REQUIREMENTS (verbatim, always enforced)

1. The AI-GENERATED label renders on every frame's header chrome. When posting, Matt should ALSO toggle TikTok's native "AI-generated content" label — put this reminder in every Release body.
2. "Research, not investment advice." appears in every cta_card scene and every caption file.
3. The QA firewall (§7) may never be bypassed with a flag. There is no `--skip-qa`.
4. No script may name individuals negatively or attribute invented quotes to real people. Institutional attribution (BIS, Ripple, DTCC) with paraphrase is the pattern.
