import argparse
import json
import os
import sys

from dotenv import load_dotenv


def extract_text(sentence):
    if isinstance(sentence, list):
        return "".join(extract_text(item) for item in sentence).strip()
    if isinstance(sentence, dict):
        return str(sentence.get("text") or "").strip()
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="DashScope ASR bridge for the Next.js frontend")
    parser.add_argument("--file", required=True)
    parser.add_argument("--model", default="paraformer-realtime-v2")
    parser.add_argument("--format", default="webm")
    parser.add_argument("--sample-rate", type=int, default=16000)
    args = parser.parse_args()

    load_dotenv()
    if not os.environ.get("DASHSCOPE_API_KEY"):
        print("DASHSCOPE_API_KEY is required for DashScope ASR", file=sys.stderr)
        return 2

    from dashscope.audio.asr import Recognition

    recognition = Recognition(
        model=args.model,
        callback=None,
        format=args.format,
        sample_rate=args.sample_rate,
    )
    result = recognition.call(args.file)
    text = extract_text(result.get_sentence())
    if not text:
        print(f"DashScope ASR returned no transcript: {result}", file=sys.stderr)
        return 3

    print(json.dumps({
        "text": text,
        "requestId": result.get_request_id(),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
