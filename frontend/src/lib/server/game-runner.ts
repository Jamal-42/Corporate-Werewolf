import { mkdir, open, stat } from "node:fs/promises";
import { spawn } from "node:child_process";
import { join, resolve } from "node:path";

export type GameRunRequest = {
  players?: unknown;
  promptVersion?: unknown;
  skillsVersion?: unknown;
  skillsTargets?: unknown;
  humanSeat?: unknown;
};

export type NormalizedGameRunRequest = {
  players: 6 | 9 | 12;
  promptVersion: string;
  skillsVersion?: string;
  skillsTargets: string;
  humanSeat?: number;
};

export type GameRunCommand = {
  command: string;
  args: string[];
};

export type StartedGameRun = {
  runId: string;
  pid: number;
  logBase: string;
  stdoutLog: string;
};

export type GameRunStatus = {
  runId: string;
  state: "missing" | "starting" | "ready";
  fileId: string;
  logBase: string;
  jsonlExists: boolean;
  processLogExists: boolean;
  size: number;
  updatedAt?: string;
};

const allowedPlayerCounts = new Set([6, 9, 12]);

export const projectRoot = resolve(process.env.WEREWOLF_PROJECT_ROOT ?? resolve(process.cwd(), ".."));
export const runsRoot = resolve(projectRoot, "exports", "runs");
export const humanInputRoot = resolve(projectRoot, "exports", "human_inputs");

export function normalizeRunRequest(input: GameRunRequest): NormalizedGameRunRequest {
  const players = Number(input.players ?? 6);
  if (!allowedPlayerCounts.has(players)) {
    throw new Error("玩家数只支持 6、9、12");
  }

  const humanSeatRaw = input.humanSeat === undefined || input.humanSeat === "" ? undefined : Number(input.humanSeat);
  if (humanSeatRaw !== undefined && (!Number.isInteger(humanSeatRaw) || humanSeatRaw < 1 || humanSeatRaw > players)) {
    throw new Error(`真人座位必须在 1 到 ${players} 之间`);
  }

  const promptVersion = sanitizeToken(String(input.promptVersion ?? "v2"), "promptVersion");
  const skillsVersionRaw = input.skillsVersion === undefined || input.skillsVersion === "" ? undefined : String(input.skillsVersion);
  const skillsVersion = skillsVersionRaw ? sanitizeToken(skillsVersionRaw, "skillsVersion") : undefined;
  const skillsTargets = String(input.skillsTargets ?? "all").trim() || "all";
  if (!/^[\w:,\-\u4e00-\u9fa5]+$/.test(skillsTargets)) {
    throw new Error("Skills 注入目标包含非法字符");
  }

  return {
    players: players as 6 | 9 | 12,
    promptVersion,
    skillsVersion,
    skillsTargets,
    humanSeat: humanSeatRaw
  };
}

export function buildGameRunCommand(request: NormalizedGameRunRequest, logBase: string): GameRunCommand {
  const args = [
    "main_cn.py",
    "--players",
    String(request.players),
    "--prompt-version",
    request.promptVersion,
    "--log",
    logBase
  ];

  if (request.skillsVersion) {
    args.push("--skills-version", request.skillsVersion, "--skills-targets", request.skillsTargets);
  }
  if (request.humanSeat !== undefined) {
    args.push("--human-seat", String(request.humanSeat));
  }

  return {
    command: "python",
    args
  };
}

export function buildGameRunEnv(
  request: NormalizedGameRunRequest,
  runId: string,
  baseEnv: NodeJS.ProcessEnv | Record<string, string | undefined> = process.env
): Record<string, string | undefined> {
  const env: Record<string, string | undefined> = { ...baseEnv };
  if (request.humanSeat !== undefined) {
    env.HUMAN_INPUT_RUN_ID = runId;
    env.HUMAN_INPUT_DIR = humanInputRoot;
    env.GAME_JSONL_PATH = join(projectRoot, `exports/runs/${runId}.jsonl`);
  }
  return env;
}

export async function startGameRun(input: GameRunRequest): Promise<StartedGameRun> {
  const request = normalizeRunRequest(input);
  await mkdir(runsRoot, { recursive: true });

  const timestamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+$/, "").replace("T", "_");
  const runId = `game_${request.players}p_${timestamp}`;
  const logBase = `exports/runs/${runId}`;
  const stdoutLog = join(runsRoot, `${runId}.process.log`);
  const handle = await open(stdoutLog, "a");

  const command = buildGameRunCommand(request, logBase);
  const isWin = process.platform === "win32";
  const child = spawn(command.command, command.args, {
    cwd: projectRoot,
    env: buildGameRunEnv(request, runId) as NodeJS.ProcessEnv,
    detached: !isWin,
    stdio: ["ignore", handle.fd, handle.fd],
    shell: false,
    windowsHide: true
  });

  child.unref();

  child.on("spawn", () => {
    handle.close().catch(() => {});
  });
  child.on("error", () => {
    handle.close().catch(() => {});
  });

  return {
    runId,
    pid: child.pid ?? 0,
    logBase,
    stdoutLog
  };
}

export async function getRunStatus(runId: string, root = runsRoot): Promise<GameRunStatus> {
  const safeRunId = sanitizeToken(runId, "runId");
  const jsonlPath = join(root, `${safeRunId}.jsonl`);
  const processLogPath = join(root, `${safeRunId}.process.log`);
  const [jsonlInfo, processLogInfo] = await Promise.all([
    stat(jsonlPath).catch(() => null),
    stat(processLogPath).catch(() => null)
  ]);

  return {
    runId: safeRunId,
    state: jsonlInfo ? "ready" : processLogInfo ? "starting" : "missing",
    fileId: `runs/${safeRunId}.jsonl`,
    logBase: `exports/runs/${safeRunId}`,
    jsonlExists: Boolean(jsonlInfo),
    processLogExists: Boolean(processLogInfo),
    size: jsonlInfo?.size ?? 0,
    updatedAt: jsonlInfo?.mtime.toISOString()
  };
}

function sanitizeToken(value: string, field: string): string {
  const trimmed = value.trim();
  if (!/^[A-Za-z0-9_.-]+$/.test(trimmed)) {
    throw new Error(`${field} 包含非法字符`);
  }
  return trimmed;
}
