export type RawGameEvent = {
  event_type: string;
  timestamp?: string;
  round?: number;
  phase?: string;
  player?: string;
  role?: string;
  action?: string;
  target?: string | null;
  key_evidence?: string | null;
  reasoning_steps?: string[];
  alive_players?: string[];
  winner?: string;
  input_tokens?: number;
  output_tokens?: number;
  latency_ms?: number;
};

export type ViewMode = "public" | "god" | "agent";

export type Visibility = "public" | "god" | "seat";

export type ArenaEvent = {
  id: string;
  type: string;
  round?: number;
  phase?: string;
  speaker?: string;
  role?: string;
  action?: string;
  target?: string | null;
  text?: string;
  visibility: Visibility;
  visibleToSeats: number[];
  timestamp?: string;
  reasoningSteps?: string[];
  alivePlayers?: string[];
  winner?: string;
  tokens?: number;
  latencyMs?: number;
};

export type PlayerSeat = {
  seat: number;
  name: string;
  role: string;
  faction: "公司" | "间谍" | "未知";
  alive: boolean;
  model: string;
  suspicion: number;
};

export type GameSummary = {
  totalEvents: number;
  aliveCount: number;
  latestPhase: string;
  deaths: number;
};

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
  summary: GameSummary;
  files?: ReplayFile[];
};
