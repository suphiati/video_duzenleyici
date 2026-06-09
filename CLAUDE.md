# CLAUDE.md

Guidance for working in this repository. Personal/local single-user app — **no
auth, multi-user, or cloud-deployment concerns**. Optimise for simplicity,
speed, and reliability.

## What this is

A local video editor: FastAPI backend + FFmpeg + a vanilla-JS frontend. Two
workflows:
1. **Manual editor** — projects / timeline (clips, audio, subtitles) → export.
2. **Batch/Pro video generation** (the flagship) — scan a folder → plan content
   → render multiple videos → optional music + YouTube upload.

## Run / dev

```bash
python run.py                      # serves http://127.0.0.1:8000  (run.py:9)
# or:  uvicorn app.main:app --reload

pip install -r requirements.txt        # runtime deps
pip install -r requirements-dev.txt    # + pytest / pytest-asyncio
pip install -r requirements-pro.txt    # optional: librosa (beat-sync)

pytest -m "not slow"   # fast pure-logic unit tests (no ffmpeg)
pytest -m slow         # opt-in smoke tests that actually invoke ffmpeg
```

## External prerequisites

- **ffmpeg + ffprobe on PATH** — required for everything (resolved in
  `app/config.py:23-24`, falls back to the bare names).
- **librosa** (optional) — enables pro-mode beat-synced cutting
  (`app/services/beat_analyzer.py`, lazy-imported; absent → linear cut spacing).
- **AI metadata** (optional) — `app/services/ai_service.py` resolves a backend
  in this order: local **Ollama** (`http://localhost:11434`, free) →
  **Claude** (`ANTHROPIC_API_KEY`) → **OpenAI** (`OPENAI_API_KEY`). Per-batch
  `provider` ("auto"|"ollama"|"claude"|"openai") overrides the order. No backend
  → templated titles. Cloud calls are raw `httpx`, no SDK needed.
- **YouTube upload** (optional) — drop Google OAuth `client_secrets.json` in
  `data/youtube/`. The OAuth redirect is hard-coded to
  `http://localhost:8000/api/batch/youtube/callback` (`youtube_service.py:9`),
  so the **port must stay 8000**.

## Architecture

- `app/main.py` wires 8 routers under `/api/` and serves `app/static/`.
- `app/api/` — routers: media, projects, timeline, subtitles, export, slideshow,
  videomix, batch.
- `app/services/` — logic. `ffmpeg_service` (FFmpeg wrappers + GPU encoder),
  `batch_service` (batch orchestrator), `pro_planner` + `scene_detector` +
  `beat_analyzer` (pro planning), `music_library` + `audio_mixer` (music),
  `ai_service`, `youtube_service`, `folder_scanner`, `ffprobe_service`,
  `project_service`, `thumbnail_service`, `progress_tracker`.
- `app/models/` — Pydantic models. Projects persist as JSON under
  `data/projects/`.

### The content-plan contract (load-bearing)

Both planners produce, and `create_batch_video` consumes, a list of:

```python
{"type": "video", "path": str, "start": float, "end": float}   # a video segment
{"type": "photo", "path": str, "duration": float}              # a still image
```

Produced by `batch_service.plan_content_distribution` (legacy) and
`pro_planner.build_plans` (pro). Keep this shape stable — it's the interface
between planning and rendering.

### Batch pipeline flow

`scan_folder` → (pro: `scene_detector` + optional `beat_analyzer` →
`pro_planner.build_plans`) or (legacy `plan_content_distribution`) → per output:
`_inject_cards` wraps the plan with optional intro/outro title-card stills
(rendered by `thumbnail_service.make_card_image`, no "subscribe" CTA) →
`create_batch_video` → optional music post-mix (`audio_mixer`, `-c:v copy` so no
video re-encode) → optional best-frame thumbnail
(`thumbnail_service.generate_youtube_thumbnail`) → optional
`youtube_service.upload_video` (uploads that thumbnail too).
Everything streams over the `/api/batch/ws` WebSocket via `send_message`
events: `status`, `scan_complete`, `pro_status`, `ai_status`, `started`,
`video_status` (creating/uploading/completed/error, may carry `warning`,
`dropped_segments`, or `thumbnail_path`), `batch_completed`, `cancelled`,
`error`. Cards inject as `photo` plan items, so they reuse the photo encode
path and need no new render code.

## Conventions

- User-facing strings are **Turkish** (often ASCII-folded: "olusturuldu").
- FFmpeg subprocesses always pass `encoding="utf-8", errors="replace"`.
- Temp files go in `TEMP_DIR` with a per-run `uuid` suffix and are removed in a
  `finally` block — never reuse a fixed temp filename (concurrent export + batch
  would collide).
- Batch/segment encoding goes through `ffmpeg_service.segment_encoder_args()`,
  which prefers a **probe-validated** GPU encoder (NVENC/AMF/QSV) and falls back
  to libx264; a failed GPU segment retries on CPU.
- Style presets live in `pro_planner.STYLE_PROFILES` — add/tune a style there.
- Optional features degrade gracefully but should **tell the user** when off
  (see the `pro_status` warning in `batch_service._build_pro_plans`).

## Testing

`tests/` is pytest-based. Pure-logic tests (planners, beat helpers, AI JSON
parse, metadata merge, `compute_xfade_offsets`) run without ffmpeg and
monkeypatch `scene_detector.detect_scenes`. `tests/test_ffmpeg_smoke.py` is
marked `slow` and synthesises tiny `testsrc` media in a tmp dir — it never
writes under `data/`. Don't add tests that hit YouTube or a live Ollama.
