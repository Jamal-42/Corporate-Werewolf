"use client";

import { useCallback, useMemo, useReducer, useRef, useState } from "react";

export type SpeechState = {
  transcript: string;
  confirmedText: string;
  isListening: boolean;
};

type SpeechAction =
  | { type: "start" }
  | { type: "stop" }
  | { type: "transcript"; text: string }
  | { type: "confirm" }
  | { type: "reset" };

type SpeechWindow = Pick<Window, "speechSynthesis"> & {
  SpeechRecognition?: new () => SpeechRecognitionLike;
  webkitSpeechRecognition?: new () => SpeechRecognitionLike;
};

type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: { results: ArrayLike<{ 0: { transcript: string } }> }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

export type PlayableAudio = {
  onended: HTMLAudioElement["onended"];
  onerror: HTMLAudioElement["onerror"];
  play: () => Promise<unknown>;
};

export type VoiceRole = "narrator" | "spy" | "seer" | "witch" | "guard" | "hunter" | "villager";

type VoiceProfile = {
  voice: string;
  rate: number;
  pitch: number;
};

const roleVoiceMap: Record<VoiceRole, VoiceProfile> = {
  narrator: { voice: "longxiaochun", rate: 0.92, pitch: 1.0 },
  spy: { voice: "longlaotie", rate: 1.05, pitch: 0.7 },
  seer: { voice: "longyue", rate: 0.88, pitch: 1.3 },
  witch: { voice: "longwan", rate: 0.9, pitch: 1.5 },
  guard: { voice: "longcheng", rate: 0.93, pitch: 0.8 },
  hunter: { voice: "longshu", rate: 1.0, pitch: 0.6 },
  villager: { voice: "longxiaoxia", rate: 0.95, pitch: 1.1 },
};

export function mapGameRoleToVoiceRole(role?: string): VoiceRole {
  if (!role) return "narrator";
  if (role.includes("间谍") || role.includes("狼人")) return "spy";
  if (role.includes("HR") || role.includes("预言家")) return "seer";
  if (role.includes("CEO") || role.includes("女巫")) return "witch";
  if (role.includes("安保") || role.includes("守护")) return "guard";
  if (role.includes("法务") || role.includes("猎人")) return "hunter";
  if (role.includes("员工") || role.includes("村民")) return "villager";
  return "narrator";
}

export function playAudioElement(audio: PlayableAudio, cleanup: () => void): Promise<void> {
  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve();
    };

    audio.onended = finish;
    audio.onerror = finish;
    void audio.play().catch(finish);
  });
}

export function getVoiceCapabilities(targetWindow: SpeechWindow | undefined = typeof window === "undefined" ? undefined : window) {
  if (!targetWindow) {
    return { tts: false, asr: false };
  }

  return {
    tts: Boolean(targetWindow.speechSynthesis),
    asr: Boolean(targetWindow.SpeechRecognition || targetWindow.webkitSpeechRecognition)
  };
}

export function createSpeechState(): SpeechState {
  return {
    transcript: "",
    confirmedText: "",
    isListening: false
  };
}

export function reduceSpeechState(state: SpeechState, action: SpeechAction): SpeechState {
  switch (action.type) {
    case "start":
      return { ...state, isListening: true };
    case "stop":
      return { ...state, isListening: false };
    case "transcript":
      return { ...state, transcript: action.text, isListening: false };
    case "confirm":
      return { ...state, confirmedText: state.transcript };
    case "reset":
      return createSpeechState();
    default:
      return state;
  }
}

export function useVoice() {
  const [speechState, dispatch] = useReducer(reduceSpeechState, undefined, createSpeechState);
  const [speakingText, setSpeakingText] = useState("");
  const capabilities = useMemo(() => getVoiceCapabilities(), []);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const prefetchCacheRef = useRef<Map<string, string>>(new Map());
  const prefetchPendingRef = useRef<Map<string, Promise<void>>>(new Map());

  const stopSpeaking = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
      audioRef.current = null;
    }
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    setSpeakingText("");
  }, []);

  const prefetchAudio = useCallback(async (text: string, voiceRole: VoiceRole = "narrator") => {
    const key = `${voiceRole}:${text}`;
    if (prefetchCacheRef.current.has(key)) return;
    if (prefetchPendingRef.current.has(key)) return;
    const profile = roleVoiceMap[voiceRole];
    const task = (async () => {
      try {
        let response: Response | null = null;
        for (let attempt = 0; attempt < 2; attempt++) {
          response = await fetch("/api/voice/tts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, provider: "dashscope", voice: profile.voice }),
          });
          if (response.ok) break;
          if (attempt === 0) await new Promise((r) => setTimeout(r, 800));
        }
        if (!response || !response.ok) return;
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        prefetchCacheRef.current.set(key, url);
        // Keep cache bounded
        if (prefetchCacheRef.current.size > 10) {
          const oldest = prefetchCacheRef.current.keys().next().value!;
          URL.revokeObjectURL(prefetchCacheRef.current.get(oldest)!);
          prefetchCacheRef.current.delete(oldest);
        }
      } catch { /* ignore prefetch failures */ }
    })();
    prefetchPendingRef.current.set(key, task);
    await task;
    prefetchPendingRef.current.delete(key);
  }, []);

  const speak = useCallback(async (text: string, voiceRole: VoiceRole = "narrator", rateOverride?: number) => {
    stopSpeaking();

    const spokenText = text.trim();
    if (!spokenText) return;
    setSpeakingText(spokenText);

    const controller = new AbortController();
    abortRef.current = controller;
    const profile = roleVoiceMap[voiceRole];

    // Check prefetch cache first
    const cacheKey = `${voiceRole}:${spokenText}`;

    // If a prefetch is in-flight for this text, wait for it instead of making a duplicate request
    const pending = prefetchPendingRef.current.get(cacheKey);
    if (pending) {
      await pending;
    }

    const cachedUrl = prefetchCacheRef.current.get(cacheKey);
    if (cachedUrl) {
      prefetchCacheRef.current.delete(cacheKey);
      const audio = new Audio(cachedUrl);
      audioRef.current = audio;
      await new Promise<void>((resolve) => {
        let settled = false;
        const finish = () => {
          if (settled) return;
          settled = true;
          URL.revokeObjectURL(cachedUrl);
          audioRef.current = null;
          setSpeakingText("");
          resolve();
        };
        audio.onended = finish;
        audio.onerror = finish;
        void audio.play().catch(finish);
      });
      return;
    }

    try {
      let response: Response | null = null;
      for (let attempt = 0; attempt < 2; attempt++) {
        if (controller.signal.aborted) return;
        response = await fetch("/api/voice/tts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: spokenText,
            provider: "dashscope",
            voice: profile.voice,
          }),
          signal: controller.signal
        });
        if (response.ok) break;
        if (attempt === 0) await new Promise((r) => setTimeout(r, 1000));
      }

      if (controller.signal.aborted) return;
      if (!response || !response.ok) throw new Error("cloud tts unavailable");

      const blob = await response.blob();
      if (controller.signal.aborted) return;

      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;

      await new Promise<void>((resolve) => {
        let settled = false;
        const finish = () => {
          if (settled) return;
          settled = true;
          URL.revokeObjectURL(url);
          audioRef.current = null;
          setSpeakingText("");
          resolve();
        };
        audio.onended = finish;
        audio.onerror = finish;
        void audio.play().catch(finish);
      });
      return;
    } catch (err) {
      if (controller.signal.aborted) return;
      if (!capabilities.tts) {
        setSpeakingText("");
        return;
      }
    }

    if (controller.signal.aborted) return;

    // Fallback: browser TTS with chunking to avoid Chrome 15s cutoff
    const chunks = splitTextForTts(spokenText);
    for (const chunk of chunks) {
      if (controller.signal.aborted) break;
      await new Promise<void>((resolve) => {
        const utterance = new SpeechSynthesisUtterance(chunk);
        utterance.lang = "zh-CN";
        utterance.rate = profile.rate;
        utterance.pitch = profile.pitch;
        utterance.onend = () => resolve();
        utterance.onerror = () => resolve();
        window.speechSynthesis.speak(utterance);
      });
    }

    if (!controller.signal.aborted) {
      setSpeakingText("");
    }
  }, [capabilities.tts, stopSpeaking]);

  const startListening = useCallback(() => {
    if (!capabilities.asr) return;
    const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) return;
    const recognition = new SpeechRecognitionCtor();
    recognition.lang = "zh-CN";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0]?.transcript ?? "")
        .join("")
        .trim();
      dispatch({ type: "transcript", text: transcript });
    };
    recognition.onend = () => dispatch({ type: "stop" });
    dispatch({ type: "start" });
    recognition.start();
  }, [capabilities.asr]);

  return {
    capabilities,
    speechState,
    speakingText,
    speak,
    prefetchAudio,
    stopSpeaking,
    startListening,
    confirmTranscript: () => dispatch({ type: "confirm" }),
    resetTranscript: () => dispatch({ type: "reset" })
  };
}

function splitTextForTts(text: string, maxLen = 80): string[] {
  if (text.length <= maxLen) return [text];
  const chunks: string[] = [];
  let remaining = text;
  while (remaining.length > 0) {
    if (remaining.length <= maxLen) {
      chunks.push(remaining);
      break;
    }
    let splitAt = remaining.lastIndexOf("。", maxLen);
    if (splitAt < 20) splitAt = remaining.lastIndexOf("，", maxLen);
    if (splitAt < 20) splitAt = remaining.lastIndexOf("、", maxLen);
    if (splitAt < 20) splitAt = maxLen;
    chunks.push(remaining.slice(0, splitAt + 1));
    remaining = remaining.slice(splitAt + 1);
  }
  return chunks;
}

declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  }
}
