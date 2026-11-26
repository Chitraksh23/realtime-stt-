"""Speech-to-text engines.

WhisperEngine : faster-whisper (open source, CTranslate2). Handles Hindi + English.
MockEngine    : deterministic fake used by tests and for demoing the UI without a model.
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Tuple

import numpy as np

from .config import HINGLISH_PROMPT, settings

log = logging.getLogger("stt.engine")

# One inference at a time: CPU inference is the bottleneck, parallel calls only slow everyone down.
INFERENCE_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stt")


class BaseEngine:
    name = "base"
    ready = False

    def load(self) -> None:
        self.ready = True

    def transcribe(self, audio: np.ndarray, language: Optional[str], partial: bool) -> Tuple[str, Optional[str]]:
        raise NotImplementedError


class MockEngine(BaseEngine):
    name = "mock"

    def transcribe(self, audio, language, partial):
        secs = len(audio) / 16000
        kind = "partial" if partial else "final"
        return f"mock {kind} transcript ({secs:.1f}s audio)", language or "en"


class WhisperEngine(BaseEngine):
    name = "whisper"

    def __init__(self):
        self.model = None

    def load(self) -> None:
        from faster_whisper import WhisperModel

        log.info("Loading Whisper model %s (%s)...", settings.whisper_model, settings.whisper_compute_type)
        self.model = WhisperModel(
            settings.whisper_model,
            device=os.getenv("WHISPER_DEVICE", "cpu"),
            compute_type=settings.whisper_compute_type,
        )
        # warm-up so the first real request is fast
        segs, _ = self.model.transcribe(np.zeros(16000, dtype=np.float32), language="en")
        list(segs)
        self.ready = True
        log.info("Whisper model ready")

    def _pick_language(self, audio: np.ndarray) -> Optional[str]:
        """Restrict auto-detection to the allowed languages (default Hindi/English).

        Whisper often confuses Hindi with Urdu etc. on short clips; picking the best of
        {hi, en} is far more reliable for the Hindi+English use case.
        """
        try:
            _, _, probs = self.model.detect_language(audio)
            allowed = [(l, p) for l, p in probs if l in settings.allowed_languages]
            if allowed:
                return max(allowed, key=lambda x: x[1])[0]
        except Exception as exc:  # detection is best-effort
            log.warning("language detection failed: %s", exc)
        return None

    def transcribe(self, audio, language, partial):
        lang = None if language in (None, "", "auto") else language
        if lang is None:
            lang = self._pick_language(audio)

        segments, info = self.model.transcribe(
            audio,
            language=lang,
            task="transcribe",
            beam_size=1 if partial else settings.whisper_beam_size,
            temperature=0.0,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            # bias towards Devanagari Hindi + Latin English code-mixing
            initial_prompt=HINGLISH_PROMPT if lang in (None, "hi") else None,
        )
        parts = []
        for s in segments:
            if s.no_speech_prob > 0.7 and s.avg_logprob < -1.0:
                continue  # likely hallucination on noise
            t = s.text.strip()
            if t:
                parts.append(t)
        return " ".join(parts).strip(), info.language


_engine: Optional[BaseEngine] = None


def get_engine() -> BaseEngine:
    global _engine
    if _engine is None:
        _engine = MockEngine() if settings.stt_engine == "mock" else WhisperEngine()
    return _engine
