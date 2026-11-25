"""Stream a WAV file to the running server exactly like the browser does (smoke test).

Usage:  python scripts/stream_wav.py sample.wav [ws://localhost:7860/ws/transcribe] [auto|hi|en]
The WAV is converted to 16 kHz mono PCM16 with ffmpeg if needed:  ffmpeg -i in.mp3 -ar 16000 -ac 1 sample.wav
"""
import asyncio
import json
import sys
import wave

import websockets


async def main(path, url, lang):
    with wave.open(path, "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2, \
            "need 16 kHz mono 16-bit WAV (ffmpeg -i in -ar 16000 -ac 1 out.wav)"
        pcm = w.readframes(w.getnframes())
    pcm += b"\x00\x00" * 16000 * 2  # 2 s of trailing silence so the last utterance is finalized

    async with websockets.connect(url, max_size=None) as ws:
        await ws.send(json.dumps({"type": "start", "language": lang, "title": f"smoke: {path}"}))
        step = 3200 * 2  # 200 ms of int16

        async def reader():
            async for m in ws:
                ev = json.loads(m)
                print(ev["type"].upper(), ev.get("text") or ev.get("message") or "")
                if ev["type"] in ("saved", "empty", "error"):
                    return

        r = asyncio.create_task(reader())
        for i in range(0, len(pcm), step):
            await ws.send(pcm[i:i + step])
            await asyncio.sleep(0.2)  # real-time pacing
        await ws.send(json.dumps({"type": "stop"}))
        await r


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "ws://localhost:7860/ws/transcribe",
                     sys.argv[3] if len(sys.argv) > 3 else "auto"))
