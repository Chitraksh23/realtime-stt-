"""Tests the Gemini Live path end-to-end with a fake Gemini client (no network needed)."""
import asyncio
from types import SimpleNamespace as NS

import numpy as np
import pytest

from app import gemini_live
from app.config import settings
from app.engine import GeminiEngine
import app.engine as engine_mod
import app.main as main_mod


class FakeSession:
    """Mimics google-genai's AsyncSession: yields interim/final transcripts as audio arrives."""

    def __init__(self):
        self.audio_chunks = 0
        self.stream_end = False
        self.q: asyncio.Queue = asyncio.Queue()

    async def send_realtime_input(self, **kw):
        if "audio" in kw:
            self.audio_chunks += 1
            if self.audio_chunks == 3:
                await self.q.put(NS(server_content=NS(interim_input_transcription=NS(text="नमस्ते"), input_transcription=None)))
            if self.audio_chunks == 6:
                await self.q.put(NS(server_content=NS(interim_input_transcription=NS(text="नमस्ते how are you"), input_transcription=None)))
                await self.q.put(NS(server_content=NS(interim_input_transcription=None, input_transcription=NS(text="नमस्ते, how are you?"))))
        if kw.get("audio_stream_end"):
            self.stream_end = True
            await self.q.put(NS(server_content=NS(interim_input_transcription=None, input_transcription=NS(text="Final words."))))

    async def receive(self):
        while True:
            item = await self.q.get()
            yield item


class FakeCM:
    def __init__(self, session): self.session = session
    async def __aenter__(self): return self.session
    async def __aexit__(self, *a): return False


class FakeClient:
    def __init__(self):
        self.session = FakeSession()
        self.aio = NS(live=NS(connect=lambda model, config: FakeCM(self.session)))


@pytest.fixture()
def gemini_mode(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "stt_engine", "gemini")
    monkeypatch.setattr(gemini_live, "_default_client_factory", lambda: fake)
    eng = GeminiEngine()
    eng.load()
    monkeypatch.setattr(engine_mod, "_engine", eng)
    monkeypatch.setattr(main_mod, "get_engine", lambda: eng)
    return fake


def _chunk():
    return (np.ones(3200) * 3000).astype("<i2").tobytes()


def test_gemini_ws_flow(client, gemini_mode):
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_json({"type": "start", "language": "auto", "title": "gemini test"})
        assert ws.receive_json()["type"] == "ready"
        for _ in range(8):
            ws.send_bytes(_chunk())
        ws.send_json({"type": "stop"})
        events = []
        while True:
            m = ws.receive_json()
            events.append(m)
            if m["type"] == "saved":
                break

    types_ = [e["type"] for e in events]
    assert types_.count("partial") >= 2
    finals = [e["text"] for e in events if e["type"] == "final"]
    assert finals == ["नमस्ते, how are you?", "Final words."]
    saved = events[-1]["transcription"]
    assert saved["text"] == "नमस्ते, how are you? Final words."
    assert saved["source"] == "live" and len(saved["segments"]) == 2
    assert gemini_mode.session.stream_end is True
    # persisted
    assert client.get(f"/api/transcriptions/{saved['id']}").json()["text"] == saved["text"]


def test_health_reports_missing_key(client, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    eng = GeminiEngine(); eng.load()
    monkeypatch.setattr(main_mod, "get_engine", lambda: eng)
    h = client.get("/api/health").json()
    assert h["engine"] == "gemini" and h["model_ready"] is False and "GEMINI_API_KEY" in h["detail"]
