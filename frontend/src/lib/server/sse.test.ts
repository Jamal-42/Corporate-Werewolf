import { appendFile, mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { formatSseMessage, tailReplayUpdates } from "./sse";

describe("sse helpers", () => {
  it("formats event source messages with id, event, and json data", () => {
    expect(formatSseMessage({
      id: "evt-1",
      event: "arena-event",
      data: { type: "decision", text: "3号发言" }
    })).toBe("id: evt-1\nevent: arena-event\ndata: {\"type\":\"decision\",\"text\":\"3号发言\"}\n\n");
  });

  it("serializes multiline data safely as a single JSON payload", () => {
    const message = formatSseMessage({
      id: "evt-2",
      event: "arena-event",
      data: { text: "第一行\n第二行" }
    });

    expect(message).toContain("data: {\"text\":\"第一行\\n第二行\"}");
    expect(message.endsWith("\n\n")).toBe(true);
  });

  it("tails a replay file as it appears and stops after game over", async () => {
    const root = await mkdtemp(join(tmpdir(), "were-tail-"));
    const runsDir = join(root, "runs");
    await mkdir(runsDir);

    const controller = new AbortController();
    const iterator = tailReplayUpdates("runs/live.jsonl", {
      root,
      intervalMs: 5,
      signal: controller.signal
    });

    const firstUpdate = iterator.next();
    await writeFile(join(runsDir, "live.jsonl"), `${JSON.stringify({ event_type: "game_init", timestamp: "t1" })}\n`, "utf-8");

    await expect(firstUpdate).resolves.toMatchObject({
      value: {
        type: "meta",
        replay: {
          id: "runs/live.jsonl",
          events: [{ type: "game_init" }]
        }
      },
      done: false
    });

    await expect(iterator.next()).resolves.toMatchObject({
      value: {
        type: "event",
        event: { type: "game_init" },
        index: 0
      },
      done: false
    });

    const gameOverUpdate = iterator.next();
    await appendFile(join(runsDir, "live.jsonl"), `${JSON.stringify({ event_type: "game_over", timestamp: "t2", winner: "company" })}\n`, "utf-8");

    await expect(gameOverUpdate).resolves.toMatchObject({
      value: {
        type: "event",
        event: { type: "game_over", winner: "company" },
        index: 1
      },
      done: false
    });
    await expect(iterator.next()).resolves.toMatchObject({
      value: {
        type: "complete",
        totalEvents: 2
      },
      done: false
    });
    await expect(iterator.next()).resolves.toMatchObject({ done: true });
  });
});
