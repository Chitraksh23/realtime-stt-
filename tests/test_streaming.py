import numpy as np

SR = 16000
CHUNK = 3200  # 200 ms, same as the browser worklet


def _pcm(samples: np.ndarray) -> bytes:
    return (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()


def _tone(seconds: float, amp=0.3) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    return amp * np.sin(2 * np.pi * 220 * t)


def _chunks(audio: np.ndarray):
    for i in range(0, len(audio), CHUNK):
        yield _pcm(audio[i:i + CHUNK])


def _drain_until(ws, wanted_type):
    seen = []
    while True:
        m = ws.receive_json()
        seen.append(m)
        if m["type"] == wanted_type:
            return seen


def test_live_session_is_streamed_and_saved(client):
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_json({"type": "start", "language": "auto", "title": "ws test"})
        assert ws.receive_json()["type"] == "ready"

        # speak 2.5 s, pause 1.2 s, speak 1.5 s, then stop
        audio = np.concatenate([_tone(2.5), np.zeros(int(SR * 1.2)), _tone(1.5)])
        for c in _chunks(audio):
            ws.send_bytes(c)
        ws.send_json({"type": "stop"})

        events = _drain_until(ws, "saved")

    types = [e["type"] for e in events]
    assert "partial" in types, "expected live partial results while speaking"
    assert types.count("final") == 2, "pause should split into two final segments"
    saved = events[-1]["transcription"]
    assert saved["title"] == "ws test" and saved["source"] == "live"
    assert len(saved["segments"]) == 2 and saved["text"]
    assert saved["duration_seconds"] > 4

    # persisted + visible via the REST dashboard API
    got = client.get(f"/api/transcriptions/{saved['id']}").json()
    assert got["text"] == saved["text"]


def test_silence_only_saves_nothing(client):
    before = client.get("/api/transcriptions").json()["total"]
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_json({"type": "start", "language": "en"})
        assert ws.receive_json()["type"] == "ready"
        for c in _chunks(np.zeros(SR * 2)):
            ws.send_bytes(c)
        ws.send_json({"type": "stop"})
        assert ws.receive_json()["type"] == "empty"
    assert client.get("/api/transcriptions").json()["total"] == before
