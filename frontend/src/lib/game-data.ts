import type { ArenaEvent, GameSummary, PlayerSeat, RawGameEvent, ViewMode } from "@/types/game";

const phaseLabels: Record<string, string> = {
  day_vote: "白天投票",
  day_discussion: "白天讨论",
  day_vote_discussion: "归票发言",
  night: "夜晚",
  werewolf: "夜晚",
  seer: "夜晚",
  guard: "夜晚",
  witch: "夜晚",
  hunter: "白天讨论"
};

const privatePhases = new Set(["werewolf", "seer", "guard", "witch"]);

export const samplePlayers: PlayerSeat[] = [
  { seat: 1, name: "1号", role: "间谍", faction: "间谍", alive: true, model: "qwen-max", suspicion: 34 },
  { seat: 2, name: "2号", role: "普通员工", faction: "公司", alive: true, model: "qwen-plus", suspicion: 52 },
  { seat: 3, name: "3号", role: "HR总监", faction: "公司", alive: true, model: "qwen-max", suspicion: 18 },
  { seat: 4, name: "4号", role: "CEO", faction: "公司", alive: true, model: "qwen-plus", suspicion: 25 },
  { seat: 5, name: "5号", role: "间谍", faction: "间谍", alive: true, model: "qwen-max", suspicion: 66 },
  { seat: 6, name: "6号", role: "安保主管", faction: "公司", alive: false, model: "qwen-plus", suspicion: 41 },
  { seat: 7, name: "7号", role: "法务总监", faction: "公司", alive: true, model: "qwen-max", suspicion: 30 },
  { seat: 8, name: "8号", role: "普通员工", faction: "公司", alive: true, model: "qwen-plus", suspicion: 57 },
  { seat: 9, name: "9号", role: "普通员工", faction: "公司", alive: true, model: "qwen-plus", suspicion: 47 }
];

export const sampleEvents: ArenaEvent[] = [
  {
    id: "init-1",
    type: "game_init",
    round: 0,
    phase: "入场",
    text: "9 名 Agent 入场，系统完成角色分配与信息隔离。",
    visibility: "god",
    visibleToSeats: [],
    timestamp: "2026-06-07T20:00:00"
  },
  {
    id: "night-1",
    type: "night_start",
    round: 1,
    phase: "夜晚",
    text: "第 1 夜开始，主持人要求所有玩家闭眼。",
    visibility: "public",
    visibleToSeats: [],
    timestamp: "2026-06-07T20:00:05"
  },
  {
    id: "wolf-1",
    type: "skill_resolution",
    round: 1,
    phase: "夜晚",
    speaker: "1号",
    role: "间谍",
    action: "窃取目标",
    target: "6号",
    text: "间谍团队选择 6 号作为夜间目标，理由是其发言像关键神职。",
    visibility: "seat",
    visibleToSeats: [1, 5],
    timestamp: "2026-06-07T20:00:18",
    reasoningSteps: ["排除低价值目标", "优先打击疑似安保主管"]
  },
  {
    id: "seer-1",
    type: "decision",
    round: 1,
    phase: "夜晚",
    speaker: "3号",
    role: "HR总监",
    action: "背调",
    target: "5号",
    text: "3号背调 5号，结果显示其属于间谍阵营。",
    visibility: "seat",
    visibleToSeats: [3],
    timestamp: "2026-06-07T20:00:27",
    reasoningSteps: ["5号站边摇摆", "优先查验高影响座位"]
  },
  {
    id: "day-1",
    type: "day_start",
    round: 1,
    phase: "白天",
    text: "天亮了，6号出局。公开讨论开始。",
    visibility: "public",
    visibleToSeats: [],
    timestamp: "2026-06-07T20:00:48"
  },
  {
    id: "speech-3",
    type: "decision",
    round: 1,
    phase: "白天讨论",
    speaker: "3号",
    role: "HR总监",
    action: "发言",
    target: "5号",
    text: "我建议今天重点听 5 号的解释，他昨天的投票理由和今天的站边明显冲突。",
    visibility: "public",
    visibleToSeats: [],
    timestamp: "2026-06-07T20:01:04",
    reasoningSteps: ["隐藏查验身份", "用公开矛盾引导票型"]
  },
  {
    id: "vote-1",
    type: "vote_result",
    round: 1,
    phase: "白天投票",
    speaker: "全员",
    action: "投票结算",
    target: "5号",
    text: "5号以 5 票出局。",
    visibility: "public",
    visibleToSeats: [],
    timestamp: "2026-06-07T20:02:10"
  }
];

export function normalizeRawEvent(raw: RawGameEvent): ArenaEvent {
  const timestamp = raw.timestamp ?? "unknown-time";
  const speaker = raw.player ?? "";
  const target = raw.target ?? null;
  const visibility = raw.phase && privatePhases.has(raw.phase) ? "seat" : "public";
  const text = raw.key_evidence || raw.action || deriveNarratorText(raw) || raw.event_type;
  const normalized: ArenaEvent = {
    id: `${raw.event_type}-${timestamp}-${speaker}-${target ?? ""}`,
    type: raw.event_type,
    round: raw.round,
    phase: normalizePhase(raw.phase),
    speaker,
    role: raw.role,
    action: raw.action,
    target,
    text,
    visibility,
    visibleToSeats: visibility === "seat" ? extractSeatNumbers(speaker) : [],
    timestamp,
    reasoningSteps: raw.reasoning_steps ?? []
  };

  if (raw.alive_players) normalized.alivePlayers = raw.alive_players;
  if (raw.winner) normalized.winner = raw.winner;
  if (raw.input_tokens !== undefined || raw.output_tokens !== undefined) {
    normalized.tokens = (raw.input_tokens ?? 0) + (raw.output_tokens ?? 0);
  }
  if (raw.latency_ms !== undefined) normalized.latencyMs = raw.latency_ms;

  return normalized;
}

export function getVisibleEvents<T extends Pick<ArenaEvent, "visibility" | "visibleToSeats" | "id">>(
  events: readonly T[],
  mode: ViewMode,
  seat?: number
): T[] {
  if (mode === "god") return [...events];
  if (mode === "public") return events.filter((event) => event.visibility === "public");
  return events.filter((event) => event.visibility === "public" || event.visibleToSeats.includes(seat ?? -1));
}

export function deriveGameSummary(events: Array<Partial<ArenaEvent>>): GameSummary {
  const latest = events.at(-1);
  const latestSnapshot = [...events].reverse().find((event) => Array.isArray(event.alivePlayers));

  return {
    totalEvents: events.length,
    aliveCount: latestSnapshot?.alivePlayers?.length ?? 0,
    latestPhase: latest?.phase ?? "未知",
    deaths: events.filter((event) => event.type === "death").length
  };
}

function normalizePhase(phase?: string): string {
  if (!phase) return "未知阶段";
  return phaseLabels[phase] ?? phase;
}

function extractSeatNumbers(value: string): number[] {
  const matched = value.match(/\d+/g);
  return matched ? matched.map(Number) : [];
}

function deriveNarratorText(raw: RawGameEvent): string {
  const round = raw.round ?? 1;
  switch (raw.event_type) {
    case "night_start":
      return `第${round}夜开始，所有玩家闭眼。`;
    case "day_start":
      return `天亮了，第${round}轮公开讨论开始。`;
    case "death":
      return raw.player ? `${raw.player}出局了。` : "有玩家出局。";
    case "game_over":
      return raw.winner ? `游戏结束，${raw.winner}获胜！` : "游戏结束。";
    default:
      return "";
  }
}
