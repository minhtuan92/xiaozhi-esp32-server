"""Fake xiaozhi device: speak text (Edge TTS) or play a wav to the server, print the conversation.

  python scripts/sim_client.py --text "Hello, how are you today?" --lang en
  python scripts/sim_client.py --wav sample.wav
Needs ffmpeg on PATH and opus.dll/libopus available. No microphone or speaker required.
"""
import argparse
import asyncio
import json
import subprocess
import tempfile
import os

import edge_tts
import websockets
from opuslib_next import Encoder, APPLICATION_AUDIO

VOICES = {"vi": "vi-VN-HoaiMyNeural", "en": "en-US-JennyNeural", "zh": "zh-CN-XiaoxiaoNeural"}
RATE, FRAME_MS = 16000, 60
FRAME = RATE * FRAME_MS // 1000


def to_pcm16k(path):
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-"],
        capture_output=True, check=True,
    )
    return out.stdout


async def synth(text, lang):
    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    await edge_tts.Communicate(text, VOICES[lang]).save(path)
    try:
        return to_pcm16k(path)
    finally:
        os.remove(path)


async def run(args):
    if args.wav:
        pcm = to_pcm16k(args.wav)
        label = args.wav
    else:
        pcm = await synth(args.text, args.lang)
        label = args.text
    pcm += b"\x00" * (-len(pcm) % (FRAME * 2))
    speech_len = len(pcm)
    pcm += b"\x00" * (FRAME * 2 * 30)  # >1s trailing silence so the VAD closes the utterance (auto mode, no explicit stop)
    enc = Encoder(RATE, 1, APPLICATION_AUDIO)
    headers = {"device-id": "aa:bb:cc:dd:ee:99", "client-id": "sim"}
    async with websockets.connect(args.url, additional_headers=headers) as ws:
        await ws.send(json.dumps({"type": "hello", "version": 1, "transport": "websocket",
                                  "audio_params": {"format": "opus", "sample_rate": RATE,
                                                   "channels": 1, "frame_duration": FRAME_MS}}))
        await asyncio.wait_for(ws.recv(), 10)
        await asyncio.sleep(4)  # first connection after server start initializes ASR/VAD/LLM; audio sent earlier is dropped
        sid = None
        print(f"[PHAT] {label}")
        await ws.send(json.dumps({"type": "listen", "state": "start", "mode": "auto"}))
        for i in range(0, len(pcm), FRAME * 2):
            await ws.send(enc.encode(pcm[i:i + FRAME * 2], FRAME))
            # speech is sent 4x faster than real time; silence at real time (VAD measures silence by wall clock)
            await asyncio.sleep(FRAME_MS / 1000 / (4 if i < speech_len else 1))
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), args.wait)
                if isinstance(msg, bytes):
                    continue  # TTS audio, discarded (no speaker)
                m = json.loads(msg)
                if m.get("type") == "stt":
                    print(f"[NGHE] {m.get('text')}")
                elif m.get("type") == "tts" and m.get("state") == "sentence_start":
                    print(f"[DICH] {m.get('text')}")
                elif m.get("type") == "tts" and m.get("state") == "stop":
                    break
        except asyncio.TimeoutError:
            print("(het thoi gian cho)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--wav")
    ap.add_argument("--lang", default="en", choices=VOICES)
    ap.add_argument("--url", default="ws://127.0.0.1:8000/xiaozhi/v1/")
    ap.add_argument("--wait", type=float, default=30)
    a = ap.parse_args()
    if not (a.text or a.wav):
        ap.error("need --text or --wav")
    asyncio.run(run(a))
