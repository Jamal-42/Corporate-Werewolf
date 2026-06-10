import type { ArenaEvent, PlayerSeat } from "@/types/game";

export type PlayerSentiment = {
  seat: number;
  name: string;
  positive: number;
  negative: number;
  neutral: number;
  aggression: number; // how much this player attacks others
  heatReceived: number; // how much others target this player
};

const POSITIVE_KEYWORDS = [
  "相信", "信任", "支持", "好人", "清白", "没问题", "同意",
  "认同", "保护", "确认", "验证", "是好人", "站边", "力保",
  "帮", "合作", "一起", "没有嫌疑", "洗清",
];

const NEGATIVE_KEYWORDS = [
  "怀疑", "质疑", "可疑", "有问题", "狼人", "间谍", "不信",
  "投", "淘汰", "出局", "处决", "有嫌疑", "撒谎", "骗",
  "装", "伪装", "跳", "冲突", "矛盾", "反对", "不同意",
  "甩锅", "推", "拉", "踩", "刀",
];

const AGGRESSIVE_KEYWORDS = [
  "我怀疑", "我投", "我觉得你", "你是狼", "你是间谍",
  "必须投", "强烈建议投", "他有问题", "她有问题",
  "不解释", "心虚", "慌了", "洗不了",
];

export function analyzeEventSentiment(events: ArenaEvent[], players: PlayerSeat[]): PlayerSentiment[] {
  const sentiments = new Map<number, PlayerSentiment>();

  for (const player of players) {
    sentiments.set(player.seat, {
      seat: player.seat,
      name: player.name,
      positive: 0,
      negative: 0,
      neutral: 0,
      aggression: 0,
      heatReceived: 0,
    });
  }

  for (const event of events) {
    if (!event.text || !event.speaker) continue;
    const seat = parseSeat(event.speaker);
    if (!seat || !sentiments.has(seat)) continue;

    const entry = sentiments.get(seat)!;
    const text = event.text;

    let posHits = 0;
    let negHits = 0;
    let aggHits = 0;

    for (const kw of POSITIVE_KEYWORDS) {
      if (text.includes(kw)) posHits++;
    }
    for (const kw of NEGATIVE_KEYWORDS) {
      if (text.includes(kw)) negHits++;
    }
    for (const kw of AGGRESSIVE_KEYWORDS) {
      if (text.includes(kw)) aggHits++;
    }

    entry.positive += posHits;
    entry.negative += negHits;
    entry.aggression += aggHits;

    if (posHits === 0 && negHits === 0) {
      entry.neutral++;
    }

    // Track heat received: if someone mentions another player's seat negatively
    for (const target of players) {
      if (target.seat === seat) continue;
      const nameRef = target.name;
      if (text.includes(nameRef) && negHits > 0) {
        sentiments.get(target.seat)!.heatReceived++;
      }
    }
  }

  // Also count vote events targeting each player
  for (const event of events) {
    if (event.type !== "vote" && event.type !== "vote_result") continue;
    if (event.target) {
      const targetSeat = parseSeat(event.target);
      if (targetSeat && sentiments.has(targetSeat)) {
        sentiments.get(targetSeat)!.heatReceived += 2;
      }
    }
  }

  return Array.from(sentiments.values());
}

export function normalizeSentiments(raw: PlayerSentiment[]): {
  seat: number;
  name: string;
  positiveRatio: number;
  negativeRatio: number;
  heat: number;
}[] {
  const maxTotal = Math.max(1, ...raw.map((r) => r.positive + r.negative + r.neutral));
  const maxHeat = Math.max(1, ...raw.map((r) => r.heatReceived + r.aggression));

  return raw.map((r) => {
    const total = r.positive + r.negative + r.neutral || 1;
    return {
      seat: r.seat,
      name: r.name,
      positiveRatio: r.positive / total,
      negativeRatio: r.negative / total,
      heat: (r.heatReceived + r.aggression) / maxHeat,
    };
  });
}

function parseSeat(speaker: string): number | null {
  const match = speaker.match(/(\d+)/);
  return match ? Number(match[1]) : null;
}
