import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { discoverReplayFiles, parseReplayJsonl, readReplayFile } from "./replay-files";

describe("replay file ingestion", () => {
  it("discovers jsonl replays newest first", async () => {
    const root = await mkdtemp(join(tmpdir(), "were-replays-"));
    await writeFile(join(root, "old.jsonl"), "{}\n", "utf-8");
    await new Promise((resolve) => setTimeout(resolve, 5));
    await writeFile(join(root, "new.jsonl"), "{}\n", "utf-8");
    await writeFile(join(root, "trace.trace.jsonl"), "{}\n", "utf-8");

    const files = await discoverReplayFiles(root);

    expect(files.map((file) => file.id)).toEqual(["new.jsonl", "old.jsonl"]);
  });

  it("discovers and reads one-level run jsonl files safely", async () => {
    const root = await mkdtemp(join(tmpdir(), "were-runs-"));
    const runsDir = join(root, "runs");
    await mkdir(runsDir);
    await writeFile(join(root, "root.jsonl"), "{}\n", "utf-8");
    await new Promise((resolve) => setTimeout(resolve, 5));
    await writeFile(join(runsDir, "live.jsonl"), "{}\n", "utf-8");

    const files = await discoverReplayFiles(root);
    const replay = await readReplayFile("runs/live.jsonl", root);

    expect(files.map((file) => file.id)).toEqual(["runs/live.jsonl", "root.jsonl"]);
    expect(replay.id).toBe("runs/live.jsonl");
    await expect(readReplayFile("../root.jsonl", root)).rejects.toThrow("invalid replay file");
    await expect(readReplayFile("runs/../root.jsonl", root)).rejects.toThrow("invalid replay file");
  });

  it("parses backend jsonl into players and arena events", () => {
    const jsonl = [
      JSON.stringify({
        event_type: "game_init",
        timestamp: "2026-06-07T20:00:00",
        player_count: 2,
        character_role_map: [
          { seat_num: 1, character_name: "逻辑怪", role: "间谍", model_name: "qwen-max" },
          { seat_num: 2, character_name: "执行者", role: "普通员工", model_name: "qwen-plus" }
        ]
      }),
      JSON.stringify({
        event_type: "state_snapshot",
        timestamp: "2026-06-07T20:00:05",
        round: 1,
        phase: "night",
        alive_players: ["1号", "2号"]
      }),
      JSON.stringify({
        event_type: "decision",
        timestamp: "2026-06-07T20:00:10",
        round: 1,
        phase: "day_vote",
        player: "1号",
        role: "间谍",
        action: "投票",
        target: "2号",
        key_evidence: "2号站边摇摆",
        reasoning_steps: ["观察发言", "制造票型压力"]
      })
    ].join("\n");

    const replay = parseReplayJsonl("demo.jsonl", jsonl);

    expect(replay.players).toEqual([
      { seat: 1, name: "1号", role: "间谍", faction: "间谍", alive: true, model: "qwen-max", suspicion: 62 },
      { seat: 2, name: "2号", role: "普通员工", faction: "公司", alive: true, model: "qwen-plus", suspicion: 39 }
    ]);
    expect(replay.events.at(-1)).toMatchObject({
      type: "decision",
      phase: "白天投票",
      speaker: "1号",
      target: "2号",
      text: "2号站边摇摆",
      visibility: "public"
    });
    expect(replay.summary).toEqual({
      totalEvents: 3,
      aliveCount: 2,
      latestPhase: "白天投票",
      deaths: 0
    });
  });
});
