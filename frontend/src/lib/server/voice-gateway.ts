import { spawn } from "node:child_process";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

export type TtsProvider = "dashscope" | "openai";
export type AsrProvider = "dashscope";

export type TtsRequest = {
  text?: unknown;
  provider?: unknown;
  model?: unknown;
  voice?: unknown;
  format?: unknown;
  rate?: unknown;
  pitch?: unknown;
};

export type NormalizedTtsRequest = {
  text: string;
  provider: TtsProvider;
  model: string;
  voice: string;
  format: "mp3" | "wav";
  rate: number;
  pitch: number;
};

export type SynthesizedAudio = {
  bytes: Buffer;
  contentType: string;
  provider: TtsProvider;
};

export type AsrRequest = {
  provider?: unknown;
  model?: unknown;
  mimeType?: unknown;
  sampleRate?: unknown;
};

export type NormalizedAsrRequest = {
  provider: AsrProvider;
  model: string;
  format: string;
  sampleRate: number;
};

export type TranscriptionResult = {
  text: string;
  provider: AsrProvider;
};

type SynthesizeDeps = {
  env?: Record<string, string | undefined>;
  fetchImpl?: typeof fetch;
};

const providerDefaults: Record<TtsProvider, Pick<NormalizedTtsRequest, "model" | "voice" | "format" | "rate" | "pitch">> = {
  dashscope: {
    model: "cosyvoice-v1",
    voice: "longxiaochun",
    format: "wav",
    rate: 1.0,
    pitch: 0,
  },
  openai: {
    model: "tts-1",
    voice: "alloy",
    format: "mp3",
    rate: 1.0,
    pitch: 0,
  }
};

export function normalizeTtsRequest(input: TtsRequest, env: Record<string, string | undefined> = process.env): NormalizedTtsRequest {
  const text = String(input.text ?? "").trim();
  if (!text) {
    throw new Error("TTS text is required");
  }
  if (text.length > 1800) {
    throw new Error("TTS text is too long");
  }

  const provider = String(input.provider ?? env.VOICE_TTS_PROVIDER ?? "dashscope").trim().toLowerCase();
  if (provider !== "dashscope" && provider !== "openai") {
    throw new Error("Unsupported TTS provider");
  }

  const defaults = providerDefaults[provider];
  const format = String(input.format ?? defaults.format).trim().toLowerCase();
  if (format !== "mp3" && format !== "wav") {
    throw new Error("Unsupported TTS format");
  }

  return {
    text,
    provider,
    model: sanitizeToken(input.model ?? env.VOICE_TTS_MODEL ?? defaults.model, "model"),
    voice: sanitizeToken(input.voice ?? env.VOICE_TTS_VOICE ?? defaults.voice, "voice"),
    format,
    rate: clampNumber(input.rate, 0.5, 2.0, defaults.rate),
    pitch: clampNumber(input.pitch, -100, 100, defaults.pitch),
  };
}

export async function synthesizeTts(input: TtsRequest, deps: SynthesizeDeps = {}): Promise<SynthesizedAudio> {
  const env = deps.env ?? process.env;
  const request = normalizeTtsRequest(input, env);

  if (request.provider === "openai") {
    return synthesizeOpenAi(request, env, deps.fetchImpl ?? fetch);
  }

  return synthesizeDashScope(request, env);
}

export function normalizeAsrRequest(input: AsrRequest, env: Record<string, string | undefined> = process.env): NormalizedAsrRequest {
  const provider = String(input.provider ?? env.VOICE_ASR_PROVIDER ?? "dashscope").trim().toLowerCase();
  if (provider !== "dashscope") {
    throw new Error("Unsupported ASR provider");
  }

  const format = audioFormatFromMime(String(input.mimeType ?? "audio/webm"));
  const defaultSampleRate = format === "webm" || format === "ogg" ? 48000 : 16000;
  const sampleRate = Number(input.sampleRate ?? env.VOICE_ASR_SAMPLE_RATE ?? defaultSampleRate);
  if (!Number.isInteger(sampleRate) || sampleRate < 8000 || sampleRate > 48000) {
    throw new Error("Invalid ASR sample rate");
  }

  return {
    provider,
    model: sanitizeToken(input.model ?? env.VOICE_ASR_MODEL ?? "paraformer-realtime-v2", "model"),
    format,
    sampleRate
  };
}

export async function transcribeAsr(
  audio: Buffer,
  input: AsrRequest,
  deps: { env?: Record<string, string | undefined> } = {}
): Promise<TranscriptionResult> {
  if (!audio.length) {
    throw new Error("audio is required");
  }

  const env = deps.env ?? process.env;
  const request = normalizeAsrRequest(input, env);
  const extension = request.format.replace(/[^a-z0-9]/gi, "") || "webm";
  const dir = resolve(tmpdir(), `were-asr-${Date.now()}-${Math.random().toString(16).slice(2)}`);
  await mkdir(dir, { recursive: true });
  const audioPath = resolve(dir, `input.${extension}`);

  try {
    await writeFile(audioPath, audio);
    const output = await runPythonJson(env.VOICE_PYTHON_BIN ?? env.PYTHON_BIN ?? "python", [
      resolve(process.cwd(), "scripts", "dashscope_asr.py"),
      "--file",
      audioPath,
      "--model",
      request.model,
      "--format",
      request.format,
      "--sample-rate",
      String(request.sampleRate)
    ]);
    return {
      text: String(output.text ?? "").trim(),
      provider: "dashscope"
    };
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

export function extractDashScopeTranscript(sentence: unknown): string {
  if (Array.isArray(sentence)) {
    return sentence.map((item) => extractDashScopeTranscript(item)).filter(Boolean).join("");
  }
  if (sentence && typeof sentence === "object" && "sentence" in sentence) {
    return extractDashScopeTranscript((sentence as { sentence?: unknown }).sentence);
  }
  if (sentence && typeof sentence === "object" && "text" in sentence) {
    return String((sentence as { text?: unknown }).text ?? "").trim();
  }
  return "";
}

async function synthesizeOpenAi(
  request: NormalizedTtsRequest,
  env: Record<string, string | undefined>,
  fetchImpl: typeof fetch
): Promise<SynthesizedAudio> {
  const apiKey = env.OPENAI_API_KEY;
  if (!apiKey) {
    throw new Error("OPENAI_API_KEY is required for OpenAI TTS");
  }

  const response = await fetchImpl("https://api.openai.com/v1/audio/speech", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      model: request.model,
      voice: request.voice,
      input: request.text,
      response_format: request.format
    })
  });

  if (!response.ok) {
    throw new Error(`OpenAI TTS failed with status ${response.status}`);
  }

  return {
    bytes: Buffer.from(await response.arrayBuffer()),
    contentType: response.headers.get("Content-Type") ?? contentTypeForFormat(request.format),
    provider: "openai"
  };
}

async function synthesizeDashScope(
  request: NormalizedTtsRequest,
  env: Record<string, string | undefined>
): Promise<SynthesizedAudio> {
  // Try persistent TTS server first (avoids Python cold-start per request)
  const serverUrl = env.TTS_SERVER_URL;
  if (serverUrl) {
    try {
      const response = await fetch(serverUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: request.text,
          voice: request.voice,
          model: request.model,
          format: request.format,
        }),
        signal: AbortSignal.timeout(10000),
      });
      if (response.ok) {
        const buf = Buffer.from(await response.arrayBuffer());
        if (buf.length > 100) {
          return {
            bytes: buf,
            contentType: response.headers.get("Content-Type") ?? contentTypeForFormat(request.format),
            provider: "dashscope",
          };
        }
      }
    } catch {
      // Server not running or timed out, fall through to subprocess
    }
  }

  const pythonBin = env.VOICE_PYTHON_BIN ?? env.PYTHON_BIN ?? "python";
  const scriptPath = resolve(process.cwd(), "scripts", "dashscope_tts.py");

  const textB64 = Buffer.from(request.text, "utf-8").toString("base64");

  const output = await runPythonJson(pythonBin, [
    scriptPath,
    "--text-b64",
    textB64,
    "--model",
    request.model,
    "--voice",
    request.voice,
    "--format",
    request.format,
  ]);

  return {
    bytes: Buffer.from(String(output.audioBase64 ?? ""), "base64"),
    contentType: String(output.contentType ?? contentTypeForFormat(request.format)),
    provider: "dashscope"
  };
}

function runPythonJson(command: string, args: string[], stdinData?: string): Promise<Record<string, unknown>> {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, {
      cwd: resolve(process.cwd(), ".."),
      env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONLEGACYWINDOWSSTDIO: "utf-8" },
      windowsHide: true
    });
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];

    child.stdout.on("data", (chunk) => stdout.push(Buffer.from(chunk)));
    child.stderr.on("data", (chunk) => stderr.push(Buffer.from(chunk)));
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(Buffer.concat(stderr).toString("utf-8") || `Python TTS exited with ${code}`));
        return;
      }
      try {
        resolvePromise(JSON.parse(Buffer.concat(stdout).toString("utf-8")));
      } catch (error) {
        reject(error);
      }
    });

    if (stdinData) {
      child.stdin.write(stdinData, "utf-8");
      child.stdin.end();
    }
  });
}

function sanitizeToken(value: unknown, field: string, options: { allowEmpty?: boolean } = {}): string {
  const text = String(value ?? "").trim();
  if (!text && options.allowEmpty) {
    return "";
  }
  if (!/^[A-Za-z0-9_.:-]+$/.test(text)) {
    throw new Error(`Invalid TTS ${field}`);
  }
  return text;
}

function clampNumber(value: unknown, min: number, max: number, fallback: number): number {
  const num = Number(value ?? fallback);
  if (!Number.isFinite(num)) return fallback;
  return Math.max(min, Math.min(max, num));
}

function contentTypeForFormat(format: "mp3" | "wav") {
  return format === "wav" ? "audio/wav" : "audio/mpeg";
}

function audioFormatFromMime(mimeType: string): string {
  const normalized = mimeType.toLowerCase();
  if (normalized.includes("wav")) return "wav";
  if (normalized.includes("mpeg") || normalized.includes("mp3")) return "mp3";
  if (normalized.includes("mp4") || normalized.includes("m4a")) return "m4a";
  if (normalized.includes("webm")) return "webm";
  if (normalized.includes("ogg")) return "ogg";
  return "webm";
}
