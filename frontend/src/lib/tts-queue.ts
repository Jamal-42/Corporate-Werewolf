import type { ArenaEvent, ViewMode } from "@/types/game";
import type { VoiceRole } from "@/hooks/use-voice";
import { mapGameRoleToVoiceRole } from "@/hooks/use-voice";

export type TtsQueueItem = {
  id: string;
  text: string;
  voiceRole: VoiceRole;
};

export function enqueueTtsItem(queue: TtsQueueItem[], item: TtsQueueItem, maxSize = 99): TtsQueueItem[] {
  const text = item.text.trim();
  if (!item.id || !text) return queue;
  if (queue.some((queued) => queued.id === item.id)) return queue;

  return [...queue, { id: item.id, text, voiceRole: item.voiceRole }].slice(-maxSize);
}

export function dequeueTtsItem(queue: TtsQueueItem[]): { next?: TtsQueueItem; rest: TtsQueueItem[] } {
  const [next, ...rest] = queue;
  return { next, rest };
}

const narratorPhrases: Record<string, string> = {
  night_start: "夜晚开始。",
  day_start: "天亮了，公开讨论开始。",
  death: "有玩家出局。",
};

export function replaceWithFirstPerson(text: string, seatNumber: number): string {
  if (!seatNumber || !text) return text;
  const seatLabel = `${seatNumber}号`;
  return text.replaceAll(seatLabel, "我");
}

export function formatEventSpeech(event: ArenaEvent, viewingSeat?: number): string {
  if (event.type === "decision") {
    return "";
  }

  if (event.type === "vote_result") {
    const target = event.target ?? "未知";
    const speaker = event.speaker ?? "系统";
    const raw = `${speaker}投票给${target}。`;
    return viewingSeat ? replaceWithFirstPerson(raw, viewingSeat) : raw;
  }

  // Narrator events
  if (event.type === "night_start" || event.type === "day_start" || event.type === "death") {
    const customText = (event.text ?? "").trim();
    if (customText && customText !== event.type && !customText.startsWith("第")) {
      return customText.slice(0, 300);
    }
    if (event.type === "death" && event.speaker) {
      return `${event.speaker}出局了。`;
    }
    return narratorPhrases[event.type] ?? "";
  }

  const raw = (event.text ?? "").trim();
  if (!raw) return "";

  // Strip stage directions in parentheses
  let text = raw
    .replace(/[（(][^）)]*[）)]/g, "")
    // Strip sentences with role positioning (冲锋型/倒钩型/深潜型 self-descriptions)
    .replace(/[^。！？；\n]*?(我[的自己]*定位|我[更比较]*适合走|可以走\*{0,2}(?:冲锋|倒钩|深潜|煽动|灵活))[^。！？；\n]*?[。！？；\n]/g, "")
    // Strip bullet-pointed role type assignments
    .replace(/-?\s*\*{0,2}(?:冲锋型|倒钩型|深潜型|煽动型|灵活位|理性分析位)[^。\n]*?[。\n]/g, "")
    // Strip dangling "我的建议分工" headers
    .replace(/我的建议分工[：:]?\s*(?=[。关]|$)/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!text) return "";

  // Replace own seat number with first person in content
  if (viewingSeat) {
    text = replaceWithFirstPerson(text, viewingSeat);
  }

  const speaker = event.speaker ?? "";

  // Narrator / system messages: read content directly without "X发言" prefix
  if (!speaker || speaker === "旁白" || speaker === "系统" || speaker === "全员" || event.role === "主持人") {
    return text;
  }

  // If text already starts with speaker name, don't prepend again
  if (speaker && text.startsWith(speaker)) {
    return text;
  }

  // First person for the player's own seat
  if (viewingSeat && speaker && speaker.includes(String(viewingSeat))) {
    return `我来说说想法，${text}`;
  }

  return `${speaker}发言，${text}`;
}

export function getEventVoiceRole(event: ArenaEvent): VoiceRole {
  if (!event.speaker || event.speaker === "系统" || event.speaker === "全员" || event.speaker === "旁白" || event.role === "主持人") return "narrator";
  if (event.type === "death" || event.type === "night_start" || event.type === "day_start") return "narrator";
  return mapGameRoleToVoiceRole(event.role);
}

const speakableTypes = new Set(["model_call", "vote_result", "game_over", "night_start", "day_start", "death"]);

export function shouldAutoSpeakEvent(event: Pick<ArenaEvent, "type" | "visibility" | "visibleToSeats">, viewMode: ViewMode, selectedSeat: number): boolean {
  if (!speakableTypes.has(event.type)) return false;
  if (event.visibility === "public") return true;
  if (viewMode === "god") return true;
  if (viewMode === "agent" && event.visibleToSeats.includes(selectedSeat)) return true;
  return false;
}
