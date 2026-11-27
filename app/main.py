import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import SessionLocal, init_db
from .engine import get_engine
from .gemini_live import GeminiSession
from .models import Transcription
from .routes import router
from .schemas import TranscriptionOut
from .streaming import StreamingTranscriber

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("stt")

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    engine = get_engine()
    # load the model in the background so the server starts (and passes health checks) immediately
    loop = asyncio.get_running_loop()
    task = loop.run_in_executor(None, engine.load)
    app.state.model_task = task
    yield


app = FastAPI(title="Realtime Speech-to-Text (Hindi + English)", lifespan=lifespan)
app.include_router(router)


@app.get("/api/health")
def health():
    eng = get_engine()
    model = {"whisper": settings.whisper_model, "gemini": settings.gemini_model}.get(eng.name)
    out = {"status": "ok", "engine": eng.name, "model": model, "model_ready": eng.ready}
    if eng.name == "gemini" and not settings.gemini_api_key:
        out["detail"] = "GEMINI_API_KEY is not configured on the server"
    return out


def _save_session(st: StreamingTranscriber, title: str | None) -> dict:
    with SessionLocal() as db:
        obj = Transcription(
            title=(title or "").strip() or f"Recording {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC",
            text=st.text,
            language=st.languages or None,
            source="live",
            duration_seconds=round(st.duration, 2),
            segments=st.segments,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return json.loads(TranscriptionOut.model_validate(obj).model_dump_json())


@app.websocket("/ws/transcribe")
async def ws_transcribe(ws: WebSocket):
    """Protocol
    client -> {"type":"start","language":"auto|hi|en","title":"optional"}
    client -> binary frames: 16 kHz mono PCM16 little-endian
    client -> {"type":"stop"}
    server -> {"type":"ready"} | {"type":"partial",...} | {"type":"final",...} | {"type":"saved","transcription":{...}}
    """
    await ws.accept()
    engine = get_engine()
    st = None  # StreamingTranscriber (whisper/mock) or GeminiSession
    title = None
    started = time.monotonic()
    send_lock = asyncio.Lock()

    async def emit(ev: dict):
        async with send_lock:
            await ws.send_json(ev)

    try:
        if engine.name == "gemini" and not settings.gemini_api_key:
            await emit({"type": "error", "message": "Server is missing GEMINI_API_KEY"})
            await ws.close()
            return
        if not engine.ready:
            await emit({"type": "loading", "message": "Speech model is still loading, please wait..."})
            while not engine.ready:
                await asyncio.sleep(0.5)

        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break

            if msg.get("text") is not None:
                data = json.loads(msg["text"])
                if data.get("type") == "start":
                    lang = data.get("language", "auto")
                    if engine.name == "gemini":
                        st = GeminiSession(lang, emit)
                        await st.start()
                    else:
                        st = StreamingTranscriber(engine, lang)
                    title = data.get("title")
                    await emit({"type": "ready"})
                elif data.get("type") == "stop":
                    break
            elif msg.get("bytes") is not None and st is not None:
                if time.monotonic() - started > settings.max_session_seconds:
                    await emit({"type": "error", "message": "Maximum session length reached"})
                    break
                for ev in await st.feed(msg["bytes"]):
                    await emit(ev)

        if st is not None:
            for ev in await st.flush():
                await emit(ev)
            if st.text:
                saved = await asyncio.to_thread(_save_session, st, title)
                await emit({"type": "saved", "transcription": saved})
            else:
                await emit({"type": "empty", "message": "No speech detected, nothing saved."})
        await ws.close()
    except WebSocketDisconnect:
        # abrupt disconnect (tab closed): still persist what we have
        if st is not None:
            if hasattr(st, "aclose"):
                await st.aclose()
            if st.text:
                await asyncio.to_thread(_save_session, st, title)
    except Exception as exc:  # pragma: no cover
        log.exception("ws error: %s", exc)
        if st is not None and hasattr(st, "aclose"):
            await st.aclose()
        try:
            await emit({"type": "error", "message": str(exc)})
            await ws.close()
        except Exception:
            pass


# ---- frontend ------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")
