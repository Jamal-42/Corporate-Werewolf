import { mkdtemp, readFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { enqueueHumanInput, normalizeHumanInput } from "./human-input-queue";

describe("human input queue", () => {
  it("normalizes and appends human input for a run seat", async () => {
    const root = await mkdtemp(join(tmpdir(), "were-human-input-"));

    const item = await enqueueHumanInput({
      runId: "game_6p_20260607_120000",
      seat: 3,
      text: "  我建议今天先投 5 号  ",
      source: "asr"
    }, root);

    const fileText = await readFile(join(root, "game_6p_20260607_120000_seat3.jsonl"), "utf-8");
    const lines = fileText.trim().split(/\r?\n/).map((line) => JSON.parse(line));

    expect(item).toMatchObject({
      runId: "game_6p_20260607_120000",
      seat: 3,
      text: "我建议今天先投 5 号",
      source: "asr"
    });
    expect(lines).toEqual([expect.objectContaining({
      seat: 3,
      text: "我建议今天先投 5 号",
      source: "asr"
    })]);
  });

  it("rejects unsafe run ids and empty text", () => {
    expect(() => normalizeHumanInput({ runId: "../game", seat: 1, text: "hello" })).toThrow("invalid run id");
    expect(() => normalizeHumanInput({ runId: "game_1", seat: 0, text: "hello" })).toThrow("invalid seat");
    expect(() => normalizeHumanInput({ runId: "game_1", seat: 1, text: " " })).toThrow("text is required");
  });
});
