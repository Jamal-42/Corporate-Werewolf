import { appendFile, mkdir } from "node:fs/promises";
import { join, resolve } from "node:path";
import { projectRoot } from "@/lib/server/game-runner";

export type HumanInputRequest = {
  runId?: unknown;
  seat?: unknown;
  text?: unknown;
  source?: unknown;
};

export type HumanInputItem = {
  runId: string;
  seat: number;
  text: string;
  source: "typed" | "asr";
  timestamp: string;
};

export const humanInputRoot = resolve(projectRoot, "exports", "human_inputs");

export function normalizeHumanInput(input: HumanInputRequest): HumanInputItem {
  const runId = String(input.runId ?? "").trim();
  if (!/^[A-Za-z0-9_.-]+$/.test(runId)) {
    throw new Error("invalid run id");
  }

  const seat = Number(input.seat);
  if (!Number.isInteger(seat) || seat < 1 || seat > 12) {
    throw new Error("invalid seat");
  }

  const text = String(input.text ?? "").trim();
  if (!text) {
    throw new Error("text is required");
  }
  if (text.length > 2000) {
    throw new Error("text is too long");
  }

  const source = input.source === "asr" ? "asr" : "typed";
  return {
    runId,
    seat,
    text,
    source,
    timestamp: new Date().toISOString()
  };
}

export async function enqueueHumanInput(input: HumanInputRequest, root = humanInputRoot): Promise<HumanInputItem> {
  const item = normalizeHumanInput(input);
  await mkdir(root, { recursive: true });
  await appendFile(join(root, `${item.runId}_seat${item.seat}.jsonl`), `${JSON.stringify(item)}\n`, "utf-8");
  return item;
}
