import { readdir, readFile, stat } from "node:fs/promises";
import { isAbsolute, join, relative, resolve } from "node:path";
import { deriveGameSummary, normalizeRawEvent, sampleEvents, samplePlayers } from "@/lib/game-data";
import type { ArenaEvent, PlayerSeat, RawGameEvent } from "@/types/game";

export type ReplayFile = {
  id: string;
  name: string;
  size: number;
  updatedAt: string;
};

export type ReplayPayload = {
  id: string;
  name: string;
  players: PlayerSeat[];
  events: ArenaEvent[];
  summary: ReturnType<typeof deriveGameSummary>;
};

type InitPlayer = {
  seat_num?: number;
  character_name?: string;
  role?: string;
  model_name?: string;
  model?: string;
};

type ParsedRawEvent = RawGameEvent & {
  character_role_map?: InitPlayer[];
  survivors?: Array<{ seat?: string; name?: string; role?: string }>;
};

const projectRoot = resolve(process.env.WEREWOLF_PROJECT_ROOT ?? resolve(process.cwd(), ".."));
export const exportsRoot = resolve(projectRoot, "exports");

export async function discoverReplayFiles(root = exportsRoot): Promise<ReplayFile[]> {
  const safeRoot = resolve(root);
  let names: string[];
  try {
    names = await readdir(safeRoot);
  } catch {
    return [];
  }

  let runNames: string[] = [];
  try {
    runNames = await readdir(join(safeRoot, "runs"));
  } catch {
    runNames = [];
  }

  const files = await Promise.all([
    ...names.filter(isReplayJsonl).map((name) => toReplayFile(name, safeRoot)),
    ...runNames.filter(isReplayJsonl).map((name) => toReplayFile(`runs/${name}`, safeRoot))
  ]);

  return files.sort((left, right) => Date.parse(right.updatedAt) - Date.parse(left.updatedAt));
}

export async function readReplayFile(fileId: string, root = exportsRoot): Promise<ReplayPayload> {
  const { id, filePath } = resolveReplayFile(fileId, root);
  const text = await readFile(filePath, "utf-8");
  return parseReplayJsonl(id, text);
}

export function resolveReplayFile(fileId: string, root = exportsRoot): { id: string; filePath: string } {
  const normalized = fileId.replace(/\\/g, "/");
  const parts = normalized.split("/");
  const safeRoot = resolve(root);

  if (
    isAbsolute(normalized)
    || !isReplayJsonl(normalized)
    || parts.some((part) => !part || part === "." || part === "..")
    || parts.length > 2
    || (parts.length === 2 && parts[0] !== "runs")
  ) {
    throw new Error("invalid replay file");
  }

  const filePath = resolve(safeRoot, ...parts);
  const relativePath = relative(safeRoot, filePath);
  if (relativePath.startsWith("..") || isAbsolute(relativePath)) {
    throw new Error("invalid replay file");
  }

  return {
    id: parts.join("/"),
    filePath
  };
}

async function toReplayFile(id: string, root: string): Promise<ReplayFile> {
  const { filePath } = resolveReplayFile(id, root);
  const info = await stat(filePath);
  return {
    id,
    name: id,
    size: info.size,
    updatedAt: info.mtime.toISOString()
  };
}

function isReplayJsonl(name: string): boolean {
  return name.endsWith(".jsonl") && !name.endsWith(".trace.jsonl");
}

export function parseReplayJsonl(name: string, text: string): ReplayPayload {
  const rawEvents = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => safeParse(line))
    .filter((event): event is ParsedRawEvent => Boolean(event));

  const players = buildPlayers(rawEvents);
  const wolfSeats = players.filter((p) => p.faction === "间谍").map((p) => p.seat);
  const events = rawEvents.map((event, idx) => normalizeBackendEvent(event, wolfSeats, idx));
  const finalPlayers = applyAliveState(players.length ? players : samplePlayers, events);
  const finalEvents = events.length ? events : sampleEvents;

  return {
    id: name,
    name,
    players: finalPlayers,
    events: finalEvents,
    summary: deriveGameSummary(finalEvents)
  };
}

function safeParse(line: string): ParsedRawEvent | null {
  try {
    return JSON.parse(line) as ParsedRawEvent;
  } catch {
    return null;
  }
}

function buildPlayers(events: ParsedRawEvent[]): PlayerSeat[] {
  const init = events.find((event) => event.event_type === "game_init");
  const map = init?.character_role_map ?? [];

  return map.map((entry, index) => {
    const seat = Number(entry.seat_num ?? index + 1);
    const role = normalizeRole(entry.role ?? "未知");
    return {
      seat,
      name: `${seat}号`,
      role,
      faction: role === "间谍" || role === "狼人" ? "间谍" : role === "未知" ? "未知" : "公司",
      alive: true,
      model: entry.model_name ?? entry.model ?? "unknown",
      suspicion: suspicionSeed(seat, role)
    };
  });
}

const wolfPhases = ["werewolf", "werewolf_discussion", "werewolf_vote"];
const privatePhases = [...wolfPhases, "seer", "guard", "witch"];

function normalizeBackendEvent(event: ParsedRawEvent, wolfSeats: number[] = [], idx: number = 0): ArenaEvent {
  if (event.event_type === "model_call") {
    const outputContent = (event as ParsedRawEvent & { output_content?: { content?: string; metadata?: Record<string, unknown> } }).output_content;
    const text = outputContent?.content ?? event.key_evidence ?? event.action ?? "模型调用";
    const seat = (event as ParsedRawEvent & { seat?: string }).seat ?? event.player ?? "";
    const isPrivate = event.phase != null && privatePhases.includes(event.phase);
    const isWolfPhase = event.phase != null && wolfPhases.includes(event.phase);
    return {
      id: `model_call-${event.timestamp ?? ""}-${seat}-${idx}`,
      type: "model_call",
      round: event.round,
      phase: normalizePhase(event.phase),
      speaker: seat,
      role: event.role,
      action: event.action ?? "发言",
      target: event.target ?? null,
      text,
      visibility: isPrivate ? "seat" : "public",
      visibleToSeats: isPrivate
        ? (isWolfPhase ? wolfSeats : extractSeatNumbersFromString(seat))
        : [],
      timestamp: event.timestamp,
      reasoningSteps: event.reasoning_steps ?? [],
      tokens: (event.input_tokens ?? 0) + (event.output_tokens ?? 0),
      latencyMs: event.latency_ms
    };
  }

  if (event.event_type === "decision") {
    const fullOutput = (event as ParsedRawEvent & { full_output?: Record<string, unknown> }).full_output;
    const seat = (event as ParsedRawEvent & { seat?: string }).seat ?? event.player ?? "";
    const text = event.key_evidence ?? (fullOutput?.reason as string | undefined) ?? event.action ?? "决策";
    const isPrivate = event.phase != null && privatePhases.includes(event.phase);
    const isWolfPhase = event.phase != null && wolfPhases.includes(event.phase);
    return {
      id: `decision-${event.timestamp ?? ""}-${seat}-${event.phase ?? ""}-${idx}`,
      type: "decision",
      round: event.round,
      phase: normalizePhase(event.phase),
      speaker: seat,
      role: event.role,
      action: event.action,
      target: event.target ?? null,
      text,
      visibility: isPrivate ? "seat" : "public",
      visibleToSeats: isPrivate
        ? (isWolfPhase ? wolfSeats : extractSeatNumbersFromString(seat))
        : [],
      timestamp: event.timestamp,
      reasoningSteps: event.reasoning_steps ?? []
    };
  }

  if (event.event_type === "state_snapshot") {
    return {
      id: `state_snapshot-${idx}`,
      type: "state_snapshot",
      round: event.round,
      phase: normalizePhase(event.phase),
      text: `存活玩家：${event.alive_players?.join("、") ?? "未知"}`,
      visibility: "god",
      visibleToSeats: [],
      timestamp: event.timestamp,
      alivePlayers: event.alive_players ?? []
    };
  }

  if (event.event_type === "game_init") {
    return {
      id: `game_init-${idx}`,
      type: "game_init",
      round: 0,
      phase: "入场",
      text: `对局初始化完成，共 ${event.character_role_map?.length ?? 0} 名玩家。`,
      visibility: "god",
      visibleToSeats: [],
      timestamp: event.timestamp
    };
  }

  if (event.event_type === "skill_resolution") {
    const source = (event as ParsedRawEvent & { source_seat?: string; source_player?: string }).source_seat
      ?? (event as ParsedRawEvent & { source_player?: string }).source_player
      ?? event.player
      ?? "";
    const target = (event as ParsedRawEvent & { target_seat?: string; target_player?: string }).target_seat
      ?? (event as ParsedRawEvent & { target_player?: string }).target_player
      ?? event.target
      ?? null;
    const normalized = normalizeRawEvent({
      ...event,
      player: source,
      target,
      action: event.action ?? skillAction((event as ParsedRawEvent & { skill_type?: string }).skill_type),
      key_evidence: (event as ParsedRawEvent & { result?: string }).result ?? event.key_evidence,
      phase: "night"
    });
    normalized.id = `${normalized.id}-${idx}`;
    return normalized;
  }

  if (event.event_type === "death") {
    const cause = (event as ParsedRawEvent & { cause?: string }).cause ?? "出局";
    return {
      id: `death-${idx}`,
      type: "death",
      round: event.round,
      phase: "死亡结算",
      speaker: event.player,
      role: event.role,
      text: `${event.player ?? "玩家"} ${cause}出局。`,
      visibility: "public",
      visibleToSeats: [],
      timestamp: event.timestamp
    };
  }

  if (event.event_type === "vote_result") {
    const votes = (event as ParsedRawEvent & { votes?: Record<string, string | null>; voted_out?: string; vote_count?: number }).votes ?? {};
    const votedOut = (event as ParsedRawEvent & { voted_out?: string }).voted_out;
    const voteCount = (event as ParsedRawEvent & { vote_count?: number }).vote_count ?? 0;
    const voteDetails = Object.entries(votes).map(([voter, target]) => `${voter}→${target ?? "弃权"}`).join("，");
    return {
      id: `vote_result-${idx}`,
      type: "vote_result",
      round: event.round,
      phase: "白天投票",
      speaker: "全员",
      action: "投票结算",
      target: votedOut ?? null,
      text: votedOut ? `${votedOut} 以 ${voteCount} 票出局。（${voteDetails}）` : `本轮投票无人出局。（${voteDetails}）`,
      visibility: "public",
      visibleToSeats: [],
      timestamp: event.timestamp
    };
  }

  if (event.event_type === "night_start") {
    return {
      id: `night_start-${idx}`,
      type: "night_start",
      round: event.round,
      phase: "夜晚",
      text: `第 ${event.round ?? "?"} 夜开始，所有玩家闭眼。`,
      visibility: "public",
      visibleToSeats: [],
      timestamp: event.timestamp
    };
  }

  if (event.event_type === "day_start") {
    return {
      id: `day_start-${idx}`,
      type: "day_start",
      round: event.round,
      phase: "白天讨论",
      text: `第 ${event.round ?? "?"} 天白天开始，公开讨论。`,
      visibility: "public",
      visibleToSeats: [],
      timestamp: event.timestamp
    };
  }

  if (event.event_type === "human_waiting") {
    const seat = (event as ParsedRawEvent & { seat?: number }).seat ?? 0;
    const prompt = (event as ParsedRawEvent & { prompt?: string }).prompt ?? "";
    return {
      id: `human_waiting-${idx}`,
      type: "human_waiting",
      round: event.round,
      phase: "等待真人",
      speaker: event.player,
      text: prompt || `轮到 ${event.player ?? seat + "号"} 发言，等待真人输入...`,
      visibility: "public",
      visibleToSeats: [],
      timestamp: event.timestamp
    };
  }

  if (event.event_type === "game_over") {
    const survivors = (event as ParsedRawEvent & { total_rounds?: number }).survivors ?? [];
    const totalRounds = (event as ParsedRawEvent & { total_rounds?: number }).total_rounds ?? 0;
    return {
      id: `game_over-${idx}`,
      type: "game_over",
      round: totalRounds,
      phase: "游戏结束",
      text: `游戏结束！${event.winner ?? "未知"} 阵营获胜。存活者：${survivors.map((s) => s.name ?? s.seat).join("、") || "无"}`,
      visibility: "public",
      visibleToSeats: [],
      timestamp: event.timestamp,
      winner: event.winner
    };
  }

  const fallback = normalizeRawEvent(event);
  fallback.id = `${fallback.id}-${idx}`;
  return fallback;
}

function applyAliveState(players: PlayerSeat[], events: ArenaEvent[]): PlayerSeat[] {
  const latestSnapshot = [...events].reverse().find((event) => event.alivePlayers?.length);
  if (!latestSnapshot?.alivePlayers?.length) {
    const deadNames = new Set(events.filter((event) => event.type === "death").map((event) => event.speaker).filter(Boolean));
    return players.map((player) => ({ ...player, alive: !deadNames.has(player.name) }));
  }
  const aliveSet = new Set(latestSnapshot.alivePlayers);
  return players.map((player) => ({ ...player, alive: aliveSet.has(player.name) }));
}

function normalizeRole(role: string): string {
  const roleMap: Record<string, string> = {
    狼人: "间谍",
    预言家: "HR总监",
    女巫: "CEO",
    守护者: "安保主管",
    猎人: "法务总监",
    村民: "普通员工"
  };
  return roleMap[role] ?? role;
}

function normalizePhase(phase?: string): string {
  if (!phase) return "未知阶段";
  if (phase.includes("night")) return "夜晚";
  if (phase.includes("vote")) return "白天投票";
  if (phase.includes("day")) return "白天讨论";
  return phase;
}

function skillAction(skillType?: string): string {
  const map: Record<string, string> = {
    spy_steal: "窃取目标",
    werewolf_kill: "夜间击杀",
    seer_check: "背调",
    guard_protect: "保护",
    witch_antidote: "挽留",
    witch_poison: "辞退",
    hunter_shoot: "诉讼"
  };
  return skillType ? map[skillType] ?? skillType : "技能结算";
}

function extractSeatNumbersFromString(value: string): number[] {
  const matched = value.match(/\d+/g);
  return matched ? matched.map(Number) : [];
}

function suspicionSeed(seat: number, role: string): number {
  if (role === "间谍" || role === "狼人") return Math.min(82, 55 + seat * 7);
  return Math.min(72, 5 + seat * 17);
}
