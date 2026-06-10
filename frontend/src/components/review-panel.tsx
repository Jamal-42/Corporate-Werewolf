"use client";

import { BrainCircuit } from "lucide-react";
import { useMemo } from "react";
import type { ArenaEvent, GameSummary, PlayerSeat } from "@/types/game";

type ReviewPanelProps = {
  summary: GameSummary;
  currentEvent: ArenaEvent;
  players: PlayerSeat[];
  events?: ArenaEvent[];
  selectedSeat?: number;
};

type RadarAxis = { label: string; value: number };

function computeAgentRadar(playerName: string, events: ArenaEvent[]): RadarAxis[] {
  const playerEvents = events.filter((e) => e.speaker === playerName);
  const speeches = playerEvents.filter((e) => e.type === "model_call" || (e.type === "decision" && e.action === "发言"));
  const votes = playerEvents.filter((e) => e.type === "decision" && e.action === "投票");
  const skills = playerEvents.filter((e) => e.type === "decision" && e.action !== "投票" && e.action !== "发言");

  const totalEvents = events.length || 1;
  const speechCount = speeches.length;
  const avgTextLen = speeches.reduce((sum, e) => sum + (e.text?.length ?? 0), 0) / (speechCount || 1);

  return [
    { label: "发言活跃", value: Math.min(100, Math.round((speechCount / (totalEvents * 0.15)) * 100)) },
    { label: "投票参与", value: Math.min(100, Math.round((votes.length / Math.max(1, events.filter((e) => e.type === "vote_result").length)) * 100)) },
    { label: "技能使用", value: Math.min(100, skills.length > 0 ? 70 + skills.length * 10 : 20) },
    { label: "表达充分", value: Math.min(100, Math.round(avgTextLen / 2)) },
    { label: "行动频率", value: Math.min(100, Math.round((playerEvents.length / (totalEvents * 0.12)) * 100)) }
  ];
}

export function ReviewPanel({ currentEvent, players, events = [], selectedSeat }: ReviewPanelProps) {
  const selected = players.find((player) => player.seat === selectedSeat) ?? players.find((player) => player.name === currentEvent.speaker) ?? players[0];
  const radarAxes = useMemo(
    () => selected ? computeAgentRadar(selected.name, events) : computeAgentRadar("", []),
    [selected?.name, events.length]
  );

  const polygon = radarAxes.map((axis, index) => {
    const angle = (Math.PI * 2 * index) / radarAxes.length - Math.PI / 2;
    const radius = axis.value * 0.55;
    return `${90 + Math.cos(angle) * radius},${90 + Math.sin(angle) * radius}`;
  });

  return (
    <section className="hud-panel min-h-0 p-4">
      <div className="mb-4 flex items-center justify-between">
        <div className="section-title">Agent 认知雷达</div>
        <BrainCircuit className="h-5 w-5 text-cyan" />
      </div>
      <div className="mb-4 border-b border-cyan/10 pb-3 text-sm">
        <span className="border-b border-cyan py-2 font-semibold text-cyan">{selected?.name ?? "Agent"}</span>
      </div>
      <div className="grid place-items-center">
        <svg viewBox="0 0 180 210" className="h-[280px] w-full max-w-[320px]">
          {[20, 38, 55].map((radius) => (
            <polygon
              key={radius}
              points={radarAxes.map((_, index) => {
                const angle = (Math.PI * 2 * index) / radarAxes.length - Math.PI / 2;
                return `${90 + Math.cos(angle) * radius},${90 + Math.sin(angle) * radius}`;
              }).join(" ")}
              fill="none"
              stroke="rgba(77,199,255,.18)"
            />
          ))}
          {radarAxes.map((axis, index) => {
            const angle = (Math.PI * 2 * index) / radarAxes.length - Math.PI / 2;
            const x = 90 + Math.cos(angle) * 68;
            const y = 90 + Math.sin(angle) * 68;
            return (
              <g key={axis.label}>
                <line x1="90" y1="90" x2={x} y2={y} stroke="rgba(77,199,255,.13)" />
                <text x={x} y={y} fill="#a7b5d8" fontSize="8" textAnchor="middle">
                  {axis.label}
                </text>
                <text x={x} y={y + 10} fill="#e8f0ff" fontSize="8" textAnchor="middle">
                  {axis.value}
                </text>
              </g>
            );
          })}
          <polygon points={polygon.join(" ")} fill="rgba(139,92,246,.38)" stroke="#9f7aea" strokeWidth="2" />
          {polygon.map((point) => {
            const [x, y] = point.split(",").map(Number);
            return <circle key={point} cx={x} cy={y} r="2.4" fill="#d8b4fe" />;
          })}
        </svg>
      </div>
      <div className="mt-2 rounded-md border border-cyan/10 bg-black/20 p-3">
        <div className="mb-2 text-sm font-semibold text-white">当前决策审计</div>
        <p className="max-h-[120px] overflow-y-auto whitespace-pre-wrap text-xs leading-5 text-slate-300">{currentEvent.text}</p>
        {currentEvent.reasoningSteps && currentEvent.reasoningSteps.length > 0 && (
          <div className="mt-2 border-t border-cyan/10 pt-2">
            <div className="mb-1 text-xs text-cyan">推理链路</div>
            <ul className="list-inside list-disc text-xs leading-5 text-slate-400">
              {currentEvent.reasoningSteps.map((step, i) => <li key={i}>{step}</li>)}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
