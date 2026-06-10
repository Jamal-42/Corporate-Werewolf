import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { buildGameRunCommand, buildGameRunEnv, getRunStatus, normalizeRunRequest } from "./game-runner";

describe("game runner", () => {
  it("normalizes valid run requests", () => {
    expect(normalizeRunRequest({
      players: 9,
      promptVersion: "v2",
      skillsVersion: "evo_3",
      skillsTargets: "seat:1,3",
      humanSeat: 4
    })).toEqual({
      players: 9,
      promptVersion: "v2",
      skillsVersion: "evo_3",
      skillsTargets: "seat:1,3",
      humanSeat: 4
    });
  });

  it("rejects invalid player counts and human seats", () => {
    expect(() => normalizeRunRequest({ players: 7 })).toThrow("玩家数只支持 6、9、12");
    expect(() => normalizeRunRequest({ players: 6, humanSeat: 9 })).toThrow("真人座位必须在 1 到 6 之间");
  });

  it("builds a python command for main_cn.py", () => {
    const command = buildGameRunCommand({
      players: 6,
      promptVersion: "v2",
      skillsVersion: "evo_3",
      skillsTargets: "all",
      humanSeat: 2
    }, "exports/game_6p_20260607_120000");

    expect(command.args).toEqual([
      "main_cn.py",
      "--players",
      "6",
      "--prompt-version",
      "v2",
      "--log",
      "exports/game_6p_20260607_120000",
      "--skills-version",
      "evo_3",
      "--skills-targets",
      "all",
      "--human-seat",
      "2"
    ]);
  });

  it("injects a web human input queue for human-seat runs", () => {
    const env = buildGameRunEnv({
      players: 6,
      promptVersion: "v2",
      skillsTargets: "all",
      humanSeat: 3
    }, "game_6p_20260607_120000", { PATH: "keep" });

    expect(env).toMatchObject({
      PATH: "keep",
      HUMAN_INPUT_RUN_ID: "game_6p_20260607_120000"
    });
    expect(env.HUMAN_INPUT_DIR).toContain("exports");
    expect(env.HUMAN_INPUT_DIR).toContain("human_inputs");
  });

  it("reports when a launched run has a jsonl file ready for tailing", async () => {
    const root = await mkdtemp(join(tmpdir(), "were-run-status-"));
    await mkdir(root, { recursive: true });
    await writeFile(join(root, "game_6p_20260607_120000.process.log"), "booting\n", "utf-8");

    expect(await getRunStatus("game_6p_20260607_120000", root)).toMatchObject({
      runId: "game_6p_20260607_120000",
      state: "starting",
      fileId: "runs/game_6p_20260607_120000.jsonl",
      jsonlExists: false,
      processLogExists: true
    });

    await writeFile(join(root, "game_6p_20260607_120000.jsonl"), "{}\n", "utf-8");

    expect(await getRunStatus("game_6p_20260607_120000", root)).toMatchObject({
      state: "ready",
      fileId: "runs/game_6p_20260607_120000.jsonl",
      jsonlExists: true,
      processLogExists: true
    });
  });
});
