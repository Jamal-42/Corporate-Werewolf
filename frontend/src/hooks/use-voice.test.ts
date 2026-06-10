import { describe, expect, it, vi } from "vitest";
import { createSpeechState, getVoiceCapabilities, playAudioElement, reduceSpeechState } from "./use-voice";

describe("voice helpers", () => {
  it("detects speech capabilities without throwing on the server", () => {
    expect(getVoiceCapabilities(undefined)).toEqual({
      tts: false,
      asr: false
    });
  });

  it("tracks ASR transcript confirmation", () => {
    const initial = createSpeechState();
    const recorded = reduceSpeechState(initial, { type: "transcript", text: "我投5号" });
    const confirmed = reduceSpeechState(recorded, { type: "confirm" });

    expect(recorded).toMatchObject({
      transcript: "我投5号",
      confirmedText: "",
      isListening: false
    });
    expect(confirmed).toMatchObject({
      transcript: "我投5号",
      confirmedText: "我投5号"
    });
  });

  it("waits for cloud TTS audio to finish before resolving", async () => {
    const audio = {
      onended: null as HTMLAudioElement["onended"],
      onerror: null as HTMLAudioElement["onerror"],
      play: vi.fn().mockResolvedValue(undefined)
    };
    const cleanup = vi.fn();
    let resolved = false;

    const playback = playAudioElement(audio, cleanup).then(() => {
      resolved = true;
    });
    await Promise.resolve();

    expect(audio.play).toHaveBeenCalledOnce();
    expect(resolved).toBe(false);

    audio.onended?.(new Event("ended"));
    await playback;

    expect(resolved).toBe(true);
    expect(cleanup).toHaveBeenCalledOnce();
  });
});
