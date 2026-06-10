"use client";

import { X } from "lucide-react";
import type { ArenaEvent, PlayerSeat } from "@/types/game";

type DataPanelProps = {
  players: PlayerSeat[];
  events: ArenaEvent[];
  onClose: () => void;
};

export function DataPanel({ players, events, onClose }: DataPanelProps) {
  const speechCounts = countBy(events, (e) => e.speaker, (e) => e.type === "model_call" || e.type === "decision");
  const voteCounts = countVoteTargets(events);
  const phases = countBy(events, (e) => e.phase ?? "未知", () => true);

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="hud-panel w-[700px] max-h-[80vh] overflow-y-auto p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold text-cyan">对局数据面板</h2>
          <button type="button" onClick={onClose} className="grid h-8 w-8 place-items-center rounded-full border border-cyan/30 text-slate-400 hover:text-cyan">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mb-4 grid grid-cols-2 gap-3 text-center">
          <StatCard label="总事件数" value={events.length} />
          <StatCard label="参与人数" value={players.length} />
        </div>

        <Section title="发言次数统计">
          <BarChart data={speechCounts} players={players} />
        </Section>

        <Section title="被投票次数">
          <BarChart data={voteCounts} players={players} color="text-rose-400" />
        </Section>

        <Section title="阶段事件分布">
          <div className="grid grid-cols-3 gap-2">
            {Object.entries(phases).sort((a, b) => b[1] - a[1]).map(([phase, count]) => (
              <div key={phase} className="flex justify-between rounded border border-cyan/10 bg-cyan/[0.03] px-3 py-2 text-xs">
                <span className="text-slate-300">{phase}</span>
                <span className="font-mono text-cyan">{count}</span>
              </div>
            ))}
          </div>
        </Section>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-cyan/20 bg-cyan/[0.04] p-3">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="mt-1 font-mono text-2xl font-semibold text-cyan">{String(value)}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <h3 className="mb-2 text-sm font-semibold text-slate-300">{title}</h3>
      {children}
    </div>
  );
}

function BarChart({ data, players, unit, color }: { data: Record<string, number>; players: PlayerSeat[]; unit?: string; color?: string }) {
  const max = Math.max(1, ...Object.values(data));
  const sorted = players
    .map((p) => ({ name: p.name, role: p.role, value: data[p.name] ?? 0 }))
    .sort((a, b) => b.value - a.value);

  return (
    <div className="space-y-1.5">
      {sorted.map((item) => (
        <div key={item.name} className="flex items-center gap-2 text-xs">
          <span className="w-12 text-slate-400">{item.name}</span>
          <span className="w-16 truncate text-slate-500">{item.role ?? ""}</span>
          <div className="relative h-5 flex-1 overflow-hidden rounded bg-cyan/10">
            <div
              className="absolute inset-y-0 left-0 rounded bg-cyan/40"
              style={{ width: `${(item.value / max) * 100}%` }}
            />
          </div>
          <span className={`w-14 text-right font-mono ${color ?? "text-cyan"}`}>
            {item.value}{unit ? ` ${unit}` : ""}
          </span>
        </div>
      ))}
    </div>
  );
}

function countBy(
  events: ArenaEvent[],
  keyFn: (e: ArenaEvent) => string | undefined,
  filterFn: (e: ArenaEvent) => boolean,
  valueFn?: (e: ArenaEvent) => number
): Record<string, number> {
  const result: Record<string, number> = {};
  for (const e of events) {
    if (!filterFn(e)) continue;
    const key = keyFn(e);
    if (!key) continue;
    result[key] = (result[key] ?? 0) + (valueFn ? valueFn(e) : 1);
  }
  return result;
}

function countVoteTargets(events: ArenaEvent[]): Record<string, number> {
  const result: Record<string, number> = {};
  for (const e of events) {
    if (e.type === "vote_result" && e.target) {
      result[e.target] = (result[e.target] ?? 0) + 1;
    }
  }
  return result;
}
