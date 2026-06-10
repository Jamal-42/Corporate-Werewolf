import type { ArenaEvent, PlayerSeat } from "@/types/game";

export type RelationType = "trust" | "suspicion" | "interaction";

export type Relationship = {
  from: string;
  to: string;
  type: RelationType;
  weight: number;
};

const TRUST_KEYWORDS = ["相信", "信任", "支持", "同意", "清白", "好人", "没问题", "保"];
const SUSPICION_KEYWORDS = ["怀疑", "质疑", "可疑", "有问题", "投", "间谍", "狼", "不信", "骗"];

export function extractRelationships(events: ArenaEvent[], playerNames: string[], players?: PlayerSeat[]): Relationship[] {
  const edges = new Map<string, { trust: number; suspicion: number; interaction: number }>();

  const spyNames = new Set(
    (players ?? []).filter((p) => p.faction === "间谍").map((p) => p.name)
  );

  function key(from: string, to: string) {
    return `${from}→${to}`;
  }

  function getOrCreate(from: string, to: string) {
    const k = key(from, to);
    if (!edges.has(k)) edges.set(k, { trust: 0, suspicion: 0, interaction: 0 });
    return edges.get(k)!;
  }

  for (const event of events) {
    if (!event.speaker) continue;

    if (event.type === "vote_result" && event.target && event.target !== event.speaker) {
      getOrCreate(event.speaker, event.target).suspicion += 3;
      getOrCreate(event.speaker, event.target).interaction += 1;
      continue;
    }

    if ((event.type === "model_call" || event.type === "decision") && event.text) {
      const text = event.text;
      for (const name of playerNames) {
        if (name === event.speaker) continue;
        if (!text.includes(name)) continue;

        const edge = getOrCreate(event.speaker, name);
        edge.interaction += 1;

        const hasTrust = TRUST_KEYWORDS.some((kw) => text.includes(kw) && textNear(text, kw, name));
        const hasSuspicion = SUSPICION_KEYWORDS.some((kw) => text.includes(kw) && textNear(text, kw, name));

        if (hasTrust) edge.trust += 2;
        if (hasSuspicion) edge.suspicion += 2;
      }
    }
  }

  const results: Relationship[] = [];
  for (const [k, counts] of edges) {
    const [from, to] = k.split("→");
    const bothSpies = spyNames.has(from) && spyNames.has(to);
    const dominant = bothSpies
      ? "trust"
      : counts.suspicion > counts.trust
        ? "suspicion"
        : counts.trust > 0
          ? "trust"
          : "interaction";
    const weight = bothSpies
      ? Math.max(5, counts.trust + counts.interaction)
      : Math.max(counts.trust, counts.suspicion, counts.interaction);
    if (weight > 0) {
      results.push({ from, to, type: dominant, weight });
    }
  }

  return dedup(results);
}

function dedup(rels: Relationship[]): Relationship[] {
  const seen = new Map<string, Relationship>();
  for (const r of rels) {
    const biKey = [r.from, r.to].sort().join("|") + r.type;
    const existing = seen.get(biKey);
    if (!existing || r.weight > existing.weight) {
      seen.set(biKey, r);
    }
  }
  return Array.from(seen.values());
}

function textNear(text: string, keyword: string, name: string): boolean {
  const ki = text.indexOf(keyword);
  const ni = text.indexOf(name);
  if (ki < 0 || ni < 0) return false;
  return Math.abs(ki - ni) < 30;
}
