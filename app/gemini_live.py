"""Real-time transcription through the Gemini Live API (model: gemini-3.5-transcribe-live).

Browser PCM16 chunks are forwarded to a Gemini Live session; Gemini streams back
  * interim_input_transcription  -> sent to the browser as "partial"
  * input_transcription          -> sent to the browser as "final" (and stored as a segment)
Language auto-detection (incl. Hindi/English code-switching) is Gemini's default when language_codes=[].
"""
import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .config import settings

log = logging.getLogger("stt.gemini")

SAMPLE_RATE = 16000
LANG_CODES = {"hi": ["hi-IN"], "en": ["en-IN"]}  # "auto" -> [] (automatic detection)

Emit = Callable[[Dict], Awaitable[None]]


def _default_client_factory():
    from google import genai

    return genai.Client(api_key=settings.gemini_api_key)


class GeminiSession:
    def __init__(self, language: Optional[str], emit: Emit, client_factory: Optional[Callable[[], Any]] = None):
        self.language = language or "auto"
        self.emit = emit
        self._client_factory = client_factory or _default_client_factory

        self.segments: List[Dict] = []
        self.total_samples = 0
        self._cm = None
        self._session = None
        self._task: Optional[asyncio.Task] = None
        self._closing = False
        self._failed = False
        self._interim = ""
        self._last_end = 0.0
        self._last_event = 0.0

    # ---- bookkeeping (same surface as StreamingTranscriber) -----------------------
    @property
    def duration(self) -> float:
        return self.total_samples / SAMPLE_RATE

    @property
    def text(self) -> str:
        return " ".join(s["text"] for s in self.segments).strip()

    @property
    def languages(self) -> str:
        return self.language if self.language in LANG_CODES else "auto"

    # ---- lifecycle ----------------------------------------------------------------
    async def start(self) -> None:
        from google.genai import types

        client = self._client_factory()
        config = types.LiveConnectConfig(
            response_modalities=["TEXT"],
            input_audio_transcription=types.AudioTranscriptionConfig(
                language_codes=LANG_CODES.get(self.language, []),
            ),
        )
        self._cm = client.aio.live.connect(model=settings.gemini_model, config=config)
        self._session = await self._cm.__aenter__()
        self._last_event = asyncio.get_running_loop().time()
        self._task = asyncio.create_task(self._receive_loop())

    async def feed(self, pcm: bytes) -> List[Dict]:
        """Forward audio to Gemini. Transcript events are emitted asynchronously via `emit`."""
        if self._failed or self._closing or len(pcm) < 2:
            return []
        from google.genai import types

        self.total_samples += len(pcm) // 2
        try:
            await self._session.send_realtime_input(
                audio=types.Blob(data=pcm, mime_type=f"audio/pcm;rate={SAMPLE_RATE}")
            )
        except Exception as exc:
            await self._fail(exc)
        return []

    async def flush(self) -> List[Dict]:
        """Client pressed stop: tell Gemini the audio ended, wait briefly for the last final, close."""
        if self._session is not None and not self._failed:
            self._closing = True
            try:
                await self._session.send_realtime_input(audio_stream_end=True)
            except Exception as exc:
                log.warning("audio_stream_end failed: %s", exc)
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 6.0
            while loop.time() < deadline and loop.time() - self._last_event < 1.5:
                await asyncio.sleep(0.1)
        # no final arrived for the last interim hypothesis: keep it rather than losing it
        events: List[Dict] = []
        if self._interim.strip():
            events.append(self._commit(self._interim))
            self._interim = ""
        await self.aclose()
        return events

    async def aclose(self) -> None:
        self._closing = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        if self._cm is not None:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._cm = None

    # ---- internals ----------------------------------------------------------------
    def _commit(self, text: str) -> Dict:
        end = round(self.duration, 2)
        seg = {"index": len(self.segments), "text": text.strip(), "language": self.languages,
               "start": round(self._last_end, 2), "end": end}
        self._last_end = end
        self.segments.append(seg)
        return {"type": "final", **seg}

    async def _fail(self, exc: Exception) -> None:
        if self._failed:
            return
        self._failed = True
        log.error("Gemini Live error: %s", exc)
        await self.emit({"type": "error", "message": f"Transcription service error: {exc}"})

    async def _receive_loop(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            while not self._closing:
                got_any = False
                async for resp in self._session.receive():
                    got_any = True
                    sc = getattr(resp, "server_content", None)
                    if not sc:
                        continue
                    interim = getattr(sc, "interim_input_transcription", None)
                    if interim is not None and getattr(interim, "text", None):
                        self._last_event = loop.time()
                        if settings.gemini_interim_mode == "append":
                            self._interim += interim.text
                        else:
                            self._interim = interim.text
                        await self.emit({"type": "partial", "text": self._interim, "language": self.languages})
                    final = getattr(sc, "input_transcription", None)
                    if final is not None and getattr(final, "text", None) and final.text.strip():
                        self._last_event = loop.time()
                        self._interim = ""
                        await self.emit(self._commit(final.text))
                if not got_any:  # receive() ended immediately (e.g. turn boundary): avoid a hot loop
                    await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self._closing:
                await self._fail(exc)
