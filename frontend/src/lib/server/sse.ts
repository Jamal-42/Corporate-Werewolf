import { exportsRoot, readReplayFile, type ReplayPayload } from "@/lib/server/replay-files";
import type { ArenaEvent } from "@/types/game";

export type SseMessage = {
  id?: string;
  event: string;
  data: unknown;
};

export type TailReplayUpdate =
  | { type: "meta"; replay: ReplayPayload }
  | { type: "event"; event: ArenaEvent; index: number }
  | { type: "complete"; totalEvents: number }
  | { type: "heartbeat" };

export type TailReplayOptions = {
  root?: string;
  intervalMs?: number;
  signal?: AbortSignal;
};

export function formatSseMessage(message: SseMessage): string {
  const lines: string[] = [];
  if (message.id) {
    lines.push(`id: ${message.id}`);
  }
  lines.push(`event: ${message.event}`);
  lines.push(`data: ${JSON.stringify(message.data)}`);
  return `${lines.join("\n")}\n\n`;
}

export function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function* tailReplayUpdates(fileId: string, options: TailReplayOptions = {}): AsyncGenerator<TailReplayUpdate> {
  const root = options.root ?? exportsRoot;
  const intervalMs = Math.max(5, options.intervalMs ?? 720);
  const signal = options.signal;
  let sentCount = 0;
  let sentMeta = false;

  while (!signal?.aborted) {
    let replay: ReplayPayload;
    try {
      replay = await readReplayFile(fileId, root);
    } catch {
      await delay(intervalMs);
      continue;
    }

    if (!sentMeta) {
      sentMeta = true;
      yield { type: "meta", replay };
    }

    const newEvents = replay.events.slice(sentCount);
    for (const [offset, event] of newEvents.entries()) {
      yield {
        type: "event",
        event,
        index: sentCount + offset
      };
    }
    sentCount = replay.events.length;

    if (newEvents.some((event) => event.type === "game_over")) {
      yield {
        type: "complete",
        totalEvents: replay.events.length
      };
      return;
    }

    // Yield a heartbeat to keep the connection alive when no new events
    if (newEvents.length === 0) {
      yield { type: "heartbeat" };
    }

    await delay(intervalMs);
  }
}
