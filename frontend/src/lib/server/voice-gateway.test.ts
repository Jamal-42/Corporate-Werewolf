import { describe, expect, it, vi } from "vitest";
import { extractDashScopeTranscript, normalizeAsrRequest, normalizeTtsRequest, synthesizeTts } from "./voice-gateway";

describe("voice gateway", () => {
  it("normalizes TTS requests with provider defaults", () => {
    expect(normalizeTtsRequest({
      text: "  5号发言：我不同意这个票型  ",
      provider: "dashscope"
    })).toEqual({
      text: "5号发言：我不同意这个票型",
      provider: "dashscope",
      model: "sambert-zhichu-v1",
      voice: "",
      format: "wav"
    });
  });

  it("rejects empty text and unknown providers before network calls", () => {
    expect(() => normalizeTtsRequest({ text: " " })).toThrow("TTS text is required");
    expect(() => normalizeTtsRequest({ text: "hello", provider: "browser" })).toThrow("Unsupported TTS provider");
  });

  it("calls OpenAI audio speech with the normalized payload", async () => {
    const fetchMock = vi.fn(async () => new Response(new Uint8Array([1, 2, 3]), {
      status: 200,
      headers: { "Content-Type": "audio/mpeg" }
    }));

    const audio = await synthesizeTts({
      text: "开始播报",
      provider: "openai",
      model: "tts-1",
      voice: "alloy",
      format: "mp3"
    }, {
      env: { OPENAI_API_KEY: "sk-test" },
      fetchImpl: fetchMock
    });

    expect(fetchMock).toHaveBeenCalledWith("https://api.openai.com/v1/audio/speech", expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({
        Authorization: "Bearer sk-test",
        "Content-Type": "application/json"
      }),
      body: JSON.stringify({
        model: "tts-1",
        voice: "alloy",
        input: "开始播报",
        response_format: "mp3"
      })
    }));
    expect(audio).toEqual({
      bytes: Buffer.from([1, 2, 3]),
      contentType: "audio/mpeg",
      provider: "openai"
    });
  });

  it("normalizes ASR uploads and extracts DashScope sentence text", () => {
    expect(normalizeAsrRequest({
      provider: "dashscope",
      mimeType: "audio/webm;codecs=opus"
    })).toEqual({
      provider: "dashscope",
      model: "paraformer-realtime-v2",
      format: "webm",
      sampleRate: 48000
    });

    expect(normalizeAsrRequest({
      provider: "dashscope",
      mimeType: "audio/wav"
    })).toMatchObject({
      format: "wav",
      sampleRate: 16000
    });

    expect(extractDashScopeTranscript({
      sentence: [
        { text: "我认为五号嫌疑最大。" },
        { text: "今天可以先听四号解释。" }
      ]
    })).toBe("我认为五号嫌疑最大。今天可以先听四号解释。");
  });
});
