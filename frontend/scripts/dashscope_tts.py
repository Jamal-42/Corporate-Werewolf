import argparse
import base64
import json
import os
import re
import sys

from dotenv import load_dotenv


def normalize_tts_text(text: str) -> str:
    normalized = text.strip()
    replacements = {
        r"\bAI\b": "人工智能",
        r"\bAgent\b": "智能体",
        r"\bTeam\b": "团队",
        r"\bASR\b": "语音识别",
        r"\bTTS\b": "语音合成",
    }
    for pattern, value in replacements.items():
        normalized = re.sub(pattern, value, normalized, flags=re.IGNORECASE)
    # Collapse whitespace but keep sentence structure
    normalized = re.sub(r"\s+", "", normalized)
    if len(normalized) < 8:
        normalized = f"{normalized}，请继续关注对局。"
    return normalized


def split_long_text(text: str, max_len: int = 300) -> list[str]:
    """Split text into chunks at sentence boundaries for TTS reliability."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break
        # Find a good split point
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


def main() -> int:
    parser = argparse.ArgumentParser(description="DashScope TTS bridge for the Next.js frontend")
    parser.add_argument("--text", required=False, default=None)
    parser.add_argument("--text-b64", required=False, default=None, help="Base64-encoded UTF-8 text (avoids Windows encoding)")
    parser.add_argument("--model", default="cosyvoice-v1")
    parser.add_argument("--voice", default="longxiaochun")
    parser.add_argument("--format", default="wav", choices=("mp3", "wav"))
    parser.add_argument("--rate", type=float, default=1.0)
    parser.add_argument("--pitch", type=int, default=0)
    parser.add_argument("--stdin", action="store_true", help="Read JSON input from stdin")
    args = parser.parse_args()

    load_dotenv()
    if not os.environ.get("DASHSCOPE_API_KEY"):
        print("DASHSCOPE_API_KEY is required for DashScope TTS", file=sys.stderr)
        return 2

    if args.text_b64:
        text_input = base64.b64decode(args.text_b64).decode("utf-8")
        model = args.model
        voice = args.voice
    elif args.stdin:
        raw = sys.stdin.buffer.read().decode("utf-8")
        params = json.loads(raw)
        text_input = params.get("text", "")
        model = params.get("model", args.model)
        voice = params.get("voice", args.voice)
    else:
        text_input = args.text or ""
        model = args.model
        voice = args.voice

    if not text_input.strip():
        print("No text provided", file=sys.stderr)
        return 1

    text = normalize_tts_text(text_input)
    fmt = args.format


    # Split long text into chunks to avoid TTS engine limits
    chunks = split_long_text(text)
    audio_parts = []
    for chunk in chunks:
        if model.startswith("cosy"):
            part = _synthesize_cosyvoice(model, voice, chunk, fmt)
        else:
            part = _synthesize_sambert(model, voice, chunk, fmt)
        if part:
            audio_parts.append(part)

    if not audio_parts:
        print("TTS returned no audio", file=sys.stderr)
        return 3

    if len(audio_parts) == 1:
        audio = audio_parts[0]
    elif fmt == "wav":
        audio = _concat_wav(audio_parts)
    else:
        audio = b"".join(audio_parts)

    print(json.dumps({
        "audioBase64": base64.b64encode(audio).decode("ascii"),
        "contentType": "audio/wav" if args.format == "wav" else "audio/mpeg",
    }))
    return 0


def _synthesize_cosyvoice(model: str, voice: str, text: str, fmt: str) -> bytes | None:
    from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat

    audio_fmt = AudioFormat.WAV_16000HZ_MONO_16BIT if fmt == "wav" else AudioFormat.MP3_16000HZ_MONO_128KBPS
    try:
        synth = SpeechSynthesizer(model=model, voice=voice, format=audio_fmt)
        audio = synth.call(text)
        return audio if audio else None
    except Exception:
        return None


def _synthesize_sambert(model: str, voice: str, text: str, fmt: str) -> bytes | None:
    from dashscope.audio.tts import SpeechSynthesizer

    if voice and "_" in voice:
        model = f"sambert-{voice}-v1"

    result = SpeechSynthesizer.call(model=model, text=text, format=fmt)
    return result.get_audio_data()


def _concat_wav(parts: list[bytes]) -> bytes:
    """Concatenate multiple WAV files by stripping headers and rebuilding."""
    import struct

    pcm_data = b""
    sample_rate = 16000
    bits_per_sample = 16
    num_channels = 1

    for part in parts:
        if len(part) < 44:
            continue
        # Standard WAV header is 44 bytes; skip it to get raw PCM
        pcm_data += part[44:]

    # Build a new WAV header
    data_size = len(pcm_data)
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, num_channels,
        sample_rate, byte_rate, block_align, bits_per_sample,
        b"data", data_size,
    )
    return header + pcm_data


if __name__ == "__main__":
    raise SystemExit(main())
