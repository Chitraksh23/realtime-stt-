# 🎙️ Realtime Speech-to-Text (Hindi + English)

Speak in Hindi, English, or a mix of both and watch the transcript appear **in real time**.
Every recording is stored in a relational database and managed from a dashboard with full **CRUD**.

**Live demo:** _<add your Render URL>_

## Features
- **Real-time streaming transcription** over WebSocket: interim text while you speak, finalized text when you pause
- **Hindi / English / code-mixed speech**: Google's [Gemini Live API](https://ai.google.dev/gemini-api/docs/live-api/live-transcribe) (`gemini-3.5-transcribe-live`) with automatic language detection; or force Hindi / English
- **Pluggable engine**: `STT_ENGINE=gemini` (default), `whisper` (self-hosted open-source faster-whisper) or `mock`
- **History dashboard with CRUD**: create notes, view, search, edit, copy, delete (paginated)
- **PostgreSQL** in production (Neon), SQLite locally; SQLAlchemy 2.0
- Automated tests for the REST API and both streaming flows; no browser build step (vanilla JS + AudioWorklet)

## Architecture
```
Browser mic ─ AudioWorklet (downsample → 16 kHz PCM16, 200 ms chunks)
     │  WebSocket /ws/transcribe
     ▼
FastAPI ─ GeminiSession ──(Gemini Live API, bidirectional stream)──► interim + final transcripts
     │          └─ every transcript event is relayed to the browser as "partial" / "final"
     └─ SQLAlchemy → PostgreSQL / SQLite   (saved on stop or disconnect)
REST /api/transcriptions  → dashboard CRUD
```
(`whisper` engine: energy VAD + faster-whisper re-transcribes the growing utterance once a second.)

### WebSocket protocol
| Direction | Message |
|---|---|
| client → server | `{"type":"start","language":"auto\|hi\|en","title":"optional"}` |
| client → server | binary frames: 16 kHz mono PCM16 little-endian |
| client → server | `{"type":"stop"}` |
| server → client | `ready`, `partial`, `final`, `saved`, `empty`, `loading`, `error` |

### REST API
`GET /api/transcriptions?q=&limit=&offset=` · `POST /api/transcriptions` · `GET|PUT|DELETE /api/transcriptions/{id}` · `GET /api/health` (docs at `/docs`)

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate      # Windows Git Bash: source .venv/Scripts/activate
pip install -r requirements-dev.txt
export GEMINI_API_KEY=your-key                          # free key: https://aistudio.google.com/apikey
uvicorn app.main:app --reload --port 7860               # open http://localhost:7860
```
Try the UI without any key: `STT_ENGINE=mock uvicorn app.main:app`. Tests: `STT_ENGINE=mock pytest -q`.

## Configuration
| Var | Default | Notes |
|---|---|---|
| `GEMINI_API_KEY` | – | Required for `STT_ENGINE=gemini` |
| `STT_ENGINE` | `gemini` | `gemini` \| `whisper` \| `mock` |
| `GEMINI_MODEL` | `gemini-3.5-transcribe-live` | |
| `GEMINI_INTERIM_MODE` | `replace` | Set `append` if interim messages arrive as fragments |
| `DATABASE_URL` | `sqlite:///./data/app.db` | Use a Postgres URL in production |
| `MAX_SESSION_SECONDS` | `570` | Gemini Live sessions are capped at 10 minutes |

## Deploy (free): Render + Neon Postgres + Gemini free key
1. **Gemini key:** https://aistudio.google.com/apikey → Create API key.
2. **Database:** [neon.tech](https://neon.tech) → new project → copy the `postgresql://…` connection string (drop `&channel_binding=require` if present).
3. **Render:** dashboard.render.com → New → Web Service → connect this GitHub repo → Runtime *Python 3*, Build `pip install -r requirements.txt`, Start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, Instance *Free*.
   Environment variables: `GEMINI_API_KEY`, `DATABASE_URL`, `PYTHON_VERSION=3.11.11`, `STT_ENGINE=gemini`. (A `render.yaml` blueprint is included.)
4. Open the `https://<name>.onrender.com` URL. Free instances sleep after ~15 min idle, so the first load can take ~30–60 s.

## Self-hosted open-source variant
`pip install -r requirements-whisper.txt && STT_ENGINE=whisper uvicorn app.main:app` (≥2 GB RAM; model `WHISPER_MODEL=small`). A `Dockerfile` is provided for it.

## Known limitations
- Gemini Live transcription sessions are limited to 10 minutes; free-tier rate limits apply and free-tier data may be used by Google to improve products.
- No authentication (assignment scope): anyone with the link can use and edit the dashboard.
