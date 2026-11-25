"""Real-time streaming transcription over raw 16 kHz mono PCM16 audio.

Strategy (works with any non-streaming model such as Whisper):
  * energy-based voice activity detection finds utterance boundaries
  * while the user is speaking, the growing utterance is re-transcribed about once a second
    and sent to the client as a *partial* (live-updating text)
  * when the user pauses (or the utterance gets too long) the utterance is transcribed once more
    and sent as a *final* segment, which is what gets stored in the database
"""
import asyncio
import math
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .config import settings
from .engine import INFERENCE_POOL, BaseEngine

SAMPLE_RATE = 16000


class StreamingTranscriber:
    def __init__(self, engine: BaseEngine, language: Optional[str] = "auto"):
        self.engine = engine
        self.language = language or "auto"

        self._buf: List[np.ndarray] = []
        self._buf_samples = 0
        self._preroll: deque = deque(maxlen=2)  # keep ~0.4s of audio before speech onset
        self._in_speech = False
        self._silence_s = 0.0
        self._since_partial = 0
        self._noise_floor = 0.004

        self.total_samples = 0
        self._utt_start_sample = 0
        self.segments: List[Dict] = []

    # ---- helpers -----------------------------------------------------------------
    @property
    def duration(self) -> float:
        return self.total_samples / SAMPLE_RATE

    @property
    def text(self) -> str:
        return " ".join(s["text"] for s in self.segments).strip()

    @property
    def languages(self) -> str:
        seen: List[str] = []
        for s in self.segments:
            lang = s.get("language")
            if lang and lang not in seen:
                seen.append(lang)
        return ",".join(seen)

    async def _run(self, audio: np.ndarray, partial: bool):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            INFERENCE_POOL, self.engine.transcribe, audio, self.language, partial
        )

    def _threshold(self) -> float:
        return max(settings.min_speech_rms, self._noise_floor * 3.0)

    # ---- public API --------------------------------------------------------------
    async def feed(self, pcm: bytes) -> List[Dict]:
        """Feed a chunk of little-endian int16 PCM; returns events to send to the client."""
        if len(pcm) < 2:
            return []
        audio = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
        n = len(audio)
        dur = n / SAMPLE_RATE
        rms = float(math.sqrt(float(np.mean(audio * audio)))) if n else 0.0
        is_speech = rms > self._threshold()
        events: List[Dict] = []

        if not self._in_speech:
            if is_speech:
                self._in_speech = True
                self._buf = list(self._preroll) + [audio]
                self._buf_samples = sum(len(a) for a in self._buf)
                self._utt_start_sample = max(0, self.total_samples - sum(len(a) for a in self._preroll))
                self._preroll.clear()
                self._silence_s = 0.0
                self._since_partial = self._buf_samples
            else:
                self._preroll.append(audio)
                self._noise_floor = 0.95 * self._noise_floor + 0.05 * rms
            self.total_samples += n
            return events

        # currently inside an utterance
        self._buf.append(audio)
        self._buf_samples += n
        self._since_partial += n
        self.total_samples += n
        self._silence_s = 0.0 if is_speech else self._silence_s + dur

        utt_seconds = self._buf_samples / SAMPLE_RATE
        if self._silence_s >= settings.silence_end_seconds or utt_seconds >= settings.max_utterance_seconds:
            events += await self._finalize()
        elif self._since_partial / SAMPLE_RATE >= settings.partial_every_seconds:
            self._since_partial = 0
            text, lang = await self._run(np.concatenate(self._buf), partial=True)
            if text:
                events.append({"type": "partial", "text": text, "language": lang})
        return events

    async def flush(self) -> List[Dict]:
        """Called when the client stops: finalize whatever is still buffered."""
        if self._in_speech and self._buf_samples > 0:
            return await self._finalize()
        return []

    async def _finalize(self) -> List[Dict]:
        audio = np.concatenate(self._buf) if self._buf else np.zeros(0, dtype=np.float32)
        start = self._utt_start_sample / SAMPLE_RATE
        end = self.total_samples / SAMPLE_RATE
        self._buf, self._buf_samples = [], 0
        self._in_speech = False
        self._silence_s = 0.0
        self._since_partial = 0
        if len(audio) < int(0.3 * SAMPLE_RATE):
            return []
        text, lang = await self._run(audio, partial=False)
        if not text:
            return [{"type": "partial", "text": "", "language": lang}]  # clears stale partial
        seg = {"index": len(self.segments), "text": text, "language": lang,
               "start": round(start, 2), "end": round(end, 2)}
        self.segments.append(seg)
        return [{"type": "final", **seg}]
