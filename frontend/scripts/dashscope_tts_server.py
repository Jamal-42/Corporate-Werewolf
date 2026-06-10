"""
Persistent TTS server that avoids Python cold-start on every request.
Run once: python scripts/dashscope_tts_server.py --port 7860
The Next.js voice-gateway will call this instead of spawning a new process each time.
"""
import argparse
import base64
import json
import os
import struct
import re
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

from dotenv import load_dotenv

load_dotenv()

# Pre-import dashscope so first request is fast
try:
    from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat
    DASHSCOPE_READY = True
except ImportError:
    DASHSCOPE_READY = False
    print("WARNING: dashscope not installed, TTS will fail", file=sys.stderr)


def normalize_tts_text(text: str) -> str:
    normalized = text.strip()
    replacements = {
        r"\bAI\b": "人工智能",
        r"\bAgent\b": "智能体",
        r"\bTeam\b": "团队",
    }
    for pattern, value in replacements.items():
        normalized = re.sub(pattern, value, normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", "", normalized)
    if len(normalized) < 8:
        normalized = f"{normalized}，请继续关注对局。"
    return normalized


def split_long_text(text: str, max_len: int = 300) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break
        split_at = -1
        for sep in ("。", "！", "？", "；", "，", "、"):
            idx = remaining.rfind(sep, 0, max_len)
            if idx > 50:
                split_at = idx + 1
                break
        if split_at < 0:
            split_at = max_len
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]
    return chunks


def concat_wav(parts: list[bytes]) -> bytes:
    pcm_data = b""
    for part in parts:
        if len(part) < 44:
            continue
        pcm_data += part[44:]
    data_size = len(pcm_data)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, 1,
        16000, 32000, 2, 16,
        b"data", data_size,
    )
    return header + pcm_data


import concurrent.futures

# Thread pool for running synthesis with timeout
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)


def _do_synth_chunk(model: str, voice: str, audio_fmt, chunk: str) -> bytes | None:
    """Run a single TTS chunk in a thread with timeout."""
    synth = SpeechSynthesizer(model=model, voice=voice, format=audio_fmt)
    return synth.call(chunk)


def synthesize(text: str, voice: str = "longxiaochun", model: str = "cosyvoice-v1", fmt: str = "wav") -> bytes | None:
    if not DASHSCOPE_READY:
        return None
    audio_fmt = AudioFormat.WAV_16000HZ_MONO_16BIT if fmt == "wav" else AudioFormat.MP3_16000HZ_MONO_128KBPS
    normalized = normalize_tts_text(text)
    chunks = split_long_text(normalized)
    parts = []
    for chunk in chunks:
        try:
            future = _executor.submit(_do_synth_chunk, model, voice, audio_fmt, chunk)
            audio = future.result(timeout=15)
            if audio:
                parts.append(audio)
        except concurrent.futures.TimeoutError:
            print(f"[TTS] timeout for voice={voice} chunk={chunk[:20]}", file=sys.stderr)
        except Exception as e:
            print(f"[TTS] error: {e}", file=sys.stderr)
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    if fmt == "wav":
        return concat_wav(parts)
    return b"".join(parts)


class TtsHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        text = body.get("text", "")
        voice = body.get("voice", "longxiaochun")
        model = body.get("model", "cosyvoice-v1")
        fmt = body.get("format", "wav")

        if not text.strip():
            self.send_error(400, "text is required")
            return

        print(f"[TTS] voice={voice} model={model} text={text[:30]}", file=sys.stderr)
        audio = synthesize(text, voice, model, fmt)
        if not audio:
            self.send_error(500, "TTS synthesis failed")
            return

        try:
            self.send_response(200)
            content_type = "audio/wav" if fmt == "wav" else "audio/mpeg"
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(audio)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(audio)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok", "dashscope": DASHSCOPE_READY}).encode())

    def log_message(self, format, *args):
        pass


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    if not os.environ.get("DASHSCOPE_API_KEY"):
        print("ERROR: DASHSCOPE_API_KEY not set", file=sys.stderr)
        return 1

    server = ThreadedHTTPServer((args.host, args.port), TtsHandler)
    print(f"TTS server listening on {args.host}:{args.port} (threaded)", file=sys.stderr)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
