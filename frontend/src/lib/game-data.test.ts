import { describe, expect, it } from "vitest";
import { deriveGameSummary, getVisibleEvents, normalizeRawEvent } from "./game-data";
import type { RawGameEvent } from "@/types/game";

describe("game data helpers", () => {
  it("normalizes backend-style events into arena events", () => {
    const raw: RawGameEvent = {
      event_type: "decision",
      timestamp: "2026-06-07T20:00:00",
      round: 2,
      phase: "day_vote",
      player: "3号",
      role: "预言家",
      action: "投票",
      target: "5号",
      key_evidence: "5号发言前后矛盾",
      reasoning_steps: ["复盘发言", "比较票型"]
    };

    expect(normalizeRawEvent(raw)).toEqual({
      id: "decision-2026-06-07T20:00:00-3号-5号",
      type: "decision",
      round: 2,
      phase: "白天投票",
      speaker: "3号",
      role: "预言家",
      action: "投票",
      target: "5号",
      text: "5号发言前后矛盾",
      visibility: "public",
      visibleToSeats: [],
      timestamp: "2026-06-07T20:00:00",
      reasoningSteps: ["复盘发言", "比较票型"]
    });
  });

  it("filters private events for a single agent view", () => {
    const events = [
      { id: "1", type: "decision", visibility: "public", visibleToSeats: [], text: "公开发言" },
      { id: "2", type: "decision", visibility: "seat", visibleToSeats: [3], text: "3号私有信息" },
      { id: "3", type: "decision", visibility: "seat", visibleToSeats: [4], text: "4号私有信息" }
    ] as const;

    expect(getVisibleEvents(events, "agent", 3).map((event) => event.id)).toEqual(["1", "2"]);
    expect(getVisibleEvents(events, "public", 3).map((event) => event.id)).toEqual(["1"]);
    expect(getVisibleEvents(events, "god", 3).map((event) => event.id)).toEqual(["1", "2", "3"]);
  });

  it("derives alive counts and latest phase", () => {
    const summary = deriveGameSummary([
      { id: "1", type: "state_snapshot", phase: "夜晚", alivePlayers: ["1号", "2号", "3号"] },
      { id: "2", type: "death", phase: "夜晚", speaker: "2号" },
      { id: "3", type: "day_start", phase: "白天" }
    ]);

    expect(summary).toEqual({
      totalEvents: 3,
      aliveCount: 3,
      latestPhase: "白天",
      deaths: 1
    });
  });
});
