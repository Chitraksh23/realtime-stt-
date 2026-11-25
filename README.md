---
title: Realtime Speech to Text
emoji: 🎙️
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# 🎙️ Realtime Speech-to-Text (Hindi + English)

Speak in Hindi, English, or a mix of both and watch the transcript appear **in real time**.
Every recording is stored in a relational database and managed from a dashboard with full **CRUD**.

**Live demo:** _<add your Hugging Face Space URL>_

## Features
- **Real-time transcription** over WebSocket: live partial text while you speak, finalized text when you pause
- **Multilingual / code-mixed**: auto mode picks Hindi or English per utterance (prompt-biased for Hinglish: Devanagari + Latin); or force Hindi / English
- **Open-source model**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (Whisper via CTranslate2), self-hosted, no paid API
- **History dashboard with CRUD**: create notes, view, search, edit, copy, delete (paginated)
- **PostgreSQL** in production (Neon/Supabase), SQLite locally; SQLAlchemy 2.0
- Tests for the REST API and the full streaming flow; Dockerized

## Architecture
```
Browser mic ─ AudioWorklet (downsample → 16 kHz PCM16, 200 ms chunks)
     │  WebSocket /ws/transcribe
     ▼
FastAPI ─ StreamingTranscriber
            ├─ energy VAD (adaptive noise floor) → utterance boundaries
            ├─ every ~1 s: re-transcribe growing utterance → "partial"
            └─ on pause: transcribe utterance once → "final"  (segments)
     │
     ├─ faster-whisper (single inference worker, CPU int8)
     └─ SQLAlchemy → PostgreSQL / SQLite   (saved on stop or disconnect)
REST /api/transcriptions  → dashboard CRUD
```

### WebSocket protocol
| Direction | Message |
|---|---|
| client → server | `{"type":"start","language":"auto\|hi\|en","title":"optional"}` |
| client → server | binary frames: 16 kHz mono PCM16 little-endian |
| client → server | `{"type":"stop"}` |
| server → client | `ready`, `partial`, `final`, `saved`, `empty`, `loading`, `error` |

### REST API
`GET /api/transcriptions?q=&limit=&offset=` · `POST /api/transcriptions` · `GET|PUT|DELETE /api/transcriptions/{id}` · `GET /api/health`
(Interactive docs at `/docs`.)

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # optional
uvicorn app.main:app --reload --port 7860
# open http://localhost:7860  (microphone works on localhost)
```
First start downloads the Whisper model (~460 MB for `small`). To try the UI without a model: `STT_ENGINE=mock uvicorn app.main:app`.

Tests: `STT_ENGINE=mock pytest -q`
File smoke test: `python scripts/stream_wav.py sample.wav` (16 kHz mono WAV)

## Configuration (env vars)
| Var | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/app.db` | Use a Postgres URL in production |
| `WHISPER_MODEL` | `small` | `base` = faster/less accurate, `medium`/`large-v3` = better Hindi (needs more CPU/GPU) |
| `WHISPER_COMPUTE_TYPE` | `int8` | |
| `ALLOWED_LANGUAGES` | `hi,en` | Languages auto-detect chooses between |
| `STT_ENGINE` | `whisper` | `mock` for tests/demo |
| `SILENCE_END_SECONDS` / `PARTIAL_EVERY_SECONDS` | `0.8` / `1.0` | Endpointing & partial cadence |

## Deploy (free): Hugging Face Spaces + Neon Postgres
1. **Database:** create a free project on [neon.tech](https://neon.tech), copy the connection string (`postgresql://…?sslmode=require`).
2. **Space:** huggingface.co → New Space → SDK **Docker** → Blank → Public.
3. In the Space → *Settings → Variables and secrets* → add secret `DATABASE_URL` = your Neon string.
4. Push this repo to the Space:
   ```bash
   git remote add space https://huggingface.co/spaces/<user>/<space-name>
   git push space main      # use a HF access token (write) as the password
   ```
5. Wait for the build (~5–10 min). Open `https://<user>-<space-name>.hf.space`.

Free Spaces sleep after inactivity; open the URL once before sharing it.

## Known limitations
- Whisper is not a true streaming model; latency comes from re-transcribing the current utterance (~1–2 s on 2 vCPUs with `small`).
- Code-mixed accuracy depends on model size; use a larger model if you have the compute.
- No authentication (assignment scope): anyone with the link can use and edit the dashboard.
