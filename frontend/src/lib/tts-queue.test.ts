import { describe, expect, it } from "vitest";
import { dequeueTtsItem, enqueueTtsItem, formatEventSpeech, replaceWithFirstPerson, shouldAutoSpeakEvent } from "./tts-queue";

describe("tts queue", () => {
  it("trims text and skips empty queue items", () => {
    expect(enqueueTtsItem([], { id: "evt-1", text: "  5号开始发言  " })).toEqual([
      { id: "evt-1", text: "5号开始发言" }
    ]);

    expect(enqueueTtsItem([], { id: "evt-2", text: "   " })).toEqual([]);
  });

  it("deduplicates by event id", () => {
    const queue = enqueueTtsItem([], { id: "evt-1", text: "第一句话" });

    expect(enqueueTtsItem(queue, { id: "evt-1", text: "重复文本" })).toEqual(queue);
  });

  it("keeps the newest items when the queue exceeds the cap", () => {
    const queue = [
      { id: "evt-1", text: "1" },
      { id: "evt-2", text: "2" }
    ];

    expect(enqueueTtsItem(queue, { id: "evt-3", text: "3" }, 2)).toEqual([
      { id: "evt-2", text: "2" },
      { id: "evt-3", text: "3" }
    ]);
  });

  it("dequeues in first-in-first-out order", () => {
    expect(dequeueTtsItem([
      { id: "evt-1", text: "第一句" },
      { id: "evt-2", text: "第二句" }
    ])).toEqual({
      next: { id: "evt-1", text: "第一句" },
      rest: [{ id: "evt-2", text: "第二句" }]
    });
  });

  it("formats speech: prepends speaker with 发言 if text doesn't start with it", () => {
    expect(formatEventSpeech({
      id: "evt-1",
      type: "model_call",
      speaker: "5号",
      action: "发言",
      text: "我认为3号身份偏好。",
      visibility: "public",
      visibleToSeats: []
    })).toBe("5号发言，我认为3号身份偏好。");
  });

  it("formats speech: doesn't duplicate speaker when text already starts with it", () => {
    expect(formatEventSpeech({
      id: "evt-2",
      type: "model_call",
      speaker: "1号",
      action: "发言",
      text: "1号投票：6号。",
      visibility: "public",
      visibleToSeats: []
    })).toBe("1号投票：6号。");
  });

  it("formats speech: strips stage directions in parentheses", () => {
    expect(formatEventSpeech({
      id: "evt-3",
      type: "model_call",
      speaker: "2号",
      action: "发言",
      text: "（语气温和诚恳）大家好我是2号。",
      visibility: "public",
      visibleToSeats: []
    })).toBe("2号发言，大家好我是2号。");
  });

  it("formats speech: returns empty for decision events", () => {
    expect(formatEventSpeech({
      id: "evt-4",
      type: "decision",
      speaker: "1号",
      action: "间谍窃取",
      text: "间谍窃取",
      visibility: "seat",
      visibleToSeats: [1]
    })).toBe("");
  });

  it("formats speech: narrator events get descriptive text", () => {
    expect(formatEventSpeech({
      id: "evt-5",
      type: "night_start",
      text: "第1夜开始，所有玩家闭眼。",
      visibility: "public",
      visibleToSeats: []
    })).toBe("夜晚开始。");

    expect(formatEventSpeech({
      id: "evt-6",
      type: "death",
      speaker: "7号",
      text: "death",
      visibility: "public",
      visibleToSeats: []
    })).toBe("7号出局了。");

    expect(formatEventSpeech({
      id: "evt-7",
      type: "day_start",
      text: "day_start",
      visibility: "public",
      visibleToSeats: []
    })).toBe("天亮了，公开讨论开始。");
  });

  it("formats speech: uses first person when speaker is the viewing seat", () => {
    expect(formatEventSpeech({
      id: "evt-8",
      type: "model_call",
      speaker: "2号",
      action: "发言",
      text: "我觉得3号很可疑。",
      visibility: "public",
      visibleToSeats: []
    }, 2)).toBe("我来说说想法，我觉得3号很可疑。");

    // Other seat still uses third person
    expect(formatEventSpeech({
      id: "evt-9",
      type: "model_call",
      speaker: "5号",
      action: "发言",
      text: "我没什么问题。",
      visibility: "public",
      visibleToSeats: []
    }, 2)).toBe("5号发言，我没什么问题。");
  });

  it("replaces seat number with 我 in text content", () => {
    expect(replaceWithFirstPerson("2号觉得3号可疑", 2)).toBe("我觉得3号可疑");
    expect(replaceWithFirstPerson("我觉得2号没问题", 3)).toBe("我觉得2号没问题");
    expect(replaceWithFirstPerson("5号同意2号的观点", 2)).toBe("5号同意我的观点");

    // Content within speech gets seat replaced
    expect(formatEventSpeech({
      id: "evt-10",
      type: "model_call",
      speaker: "3号",
      action: "发言",
      text: "我同意2号的观点，2号分析得很好。",
      visibility: "public",
      visibleToSeats: []
    }, 2)).toBe("3号发言，我同意我的观点，我分析得很好。");
  });

  it("only auto-speaks model_call, vote_result, game_over, night_start, day_start, death", () => {
    const modelCall = { type: "model_call", visibility: "public" as const, visibleToSeats: [] };
    const decision = { type: "decision", visibility: "public" as const, visibleToSeats: [] };
    const voteResult = { type: "vote_result", visibility: "public" as const, visibleToSeats: [] };
    const nightStart = { type: "night_start", visibility: "public" as const, visibleToSeats: [] };
    const dayStart = { type: "day_start", visibility: "public" as const, visibleToSeats: [] };
    const death = { type: "death", visibility: "public" as const, visibleToSeats: [] };

    expect(shouldAutoSpeakEvent(modelCall, "god", 1)).toBe(true);
    expect(shouldAutoSpeakEvent(decision, "god", 1)).toBe(false);
    expect(shouldAutoSpeakEvent(voteResult, "god", 1)).toBe(true);
    expect(shouldAutoSpeakEvent(nightStart, "god", 1)).toBe(true);
    expect(shouldAutoSpeakEvent(dayStart, "god", 1)).toBe(true);
    expect(shouldAutoSpeakEvent(death, "god", 1)).toBe(true);
  });

  it("respects view visibility when auto speaking events", () => {
    const seatOnlyEvent = {
      type: "model_call",
      visibility: "seat" as const,
      visibleToSeats: [2]
    };

    // God mode speaks all events including private ones
    expect(shouldAutoSpeakEvent(seatOnlyEvent, "god", 5)).toBe(true);
    expect(shouldAutoSpeakEvent(seatOnlyEvent, "public", 2)).toBe(false);
    expect(shouldAutoSpeakEvent(seatOnlyEvent, "agent", 2)).toBe(true);
    expect(shouldAutoSpeakEvent(seatOnlyEvent, "agent", 5)).toBe(false);
  });
});
