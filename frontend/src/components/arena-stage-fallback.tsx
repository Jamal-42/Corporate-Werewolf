"use client";

import { useMemo } from "react";
import type { ArenaEvent, PlayerSeat, ViewMode } from "@/types/game";
import { replaceWithFirstPerson } from "@/lib/tts-queue";
import { extractRelationships } from "@/lib/relationships";
import { cn } from "@/lib/utils";

type ArenaStageFallbackProps = {
  players: PlayerSeat[];
  currentEvent: ArenaEvent;
  viewMode: ViewMode;
  selectedSeat: number;
  events?: ArenaEvent[];
  reason?: "loading" | "webgl" | "error";
};

const fallbackColors: Record<string, string> = {
  间谍: "#f05cff",
  狼人: "#f05cff",
  HR总监: "#4dc7ff",
  预言家: "#f8c47a",
  CEO: "#4dc7ff",
  安保主管: "#8b5cf6",
  法务总监: "#4de7db",
  普通员工: "#56e3ff"
};

export function ArenaStageFallback({ players, currentEvent, viewMode, selectedSeat, events = [], reason = "loading" }: ArenaStageFallbackProps) {
  const center = 400;
  const seatRadius = 262;
  const actor = players.find((player) => player.name === currentEvent.speaker);
  const target = players.find((player) => player.name === currentEvent.target);
  const actorPosition = actor ? getSeatPosition(actor, players, center, seatRadius) : null;
  const targetPosition = target ? getSeatPosition(target, players, center, seatRadius) : null;
  const relationships = useMemo(() => extractRelationships(events, players.map((p) => p.name), players), [events, players]);
  const teammates = useMemo(() => {
    const me = players.find((p) => p.seat === selectedSeat);
    if (!me || me.faction !== "间谍") return [] as number[];
    return players.filter((p) => p.faction === "间谍" && p.seat !== selectedSeat).map((p) => p.seat);
  }, [players, selectedSeat]);

  return (
    <div className="hud-stage relative h-full min-h-[560px] w-full overflow-hidden bg-[#020813]">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(31,182,255,.20),transparent_48%),linear-gradient(180deg,rgba(5,18,31,.1),rgba(2,8,19,.94))]" />
      <svg viewBox="0 0 800 620" className="absolute inset-0 h-full w-full" role="img" aria-label="2D 战术圆桌">
        <defs>
          <filter id="fallback-glow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <linearGradient id="fallback-core" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0%" stopColor="#4dc7ff" stopOpacity="0.65" />
            <stop offset="100%" stopColor="#8f5cff" stopOpacity="0.35" />
          </linearGradient>
        </defs>

        <ellipse cx={center} cy="330" rx="350" ry="234" fill="rgba(2,8,19,.62)" stroke="rgba(77,199,255,.34)" />
        {[82, 142, 204, 266, 324].map((radius) => (
          <ellipse key={radius} cx={center} cy="330" rx={radius} ry={radius * 0.64} fill="none" stroke="rgba(77,199,255,.20)" />
        ))}
        {players.map((player) => {
          const position = getSeatPosition(player, players, center, seatRadius);
          return (
            <line
              key={`link-${player.seat}`}
              x1={center}
              y1="330"
              x2={position.x}
              y2={position.y}
              stroke="rgba(77,199,255,.18)"
              strokeDasharray="5 8"
            />
          );
        })}
        {relationships.map((rel) => {
          const fromPlayer = players.find((p) => p.name === rel.from);
          const toPlayer = players.find((p) => p.name === rel.to);
          if (!fromPlayer || !toPlayer) return null;
          const fromPos = getSeatPosition(fromPlayer, players, center, seatRadius);
          const toPos = getSeatPosition(toPlayer, players, center, seatRadius);
          const color = rel.type === "trust" ? "#4dc7ff" : rel.type === "suspicion" ? "#ff4f87" : "#f8c47a";
          const dash = rel.type === "interaction" ? "6 4" : undefined;
          const opacity = Math.min(0.7, 0.25 + rel.weight * 0.08);
          return (
            <line
              key={`rel-${rel.from}-${rel.to}-${rel.type}`}
              x1={fromPos.x}
              y1={fromPos.y}
              x2={toPos.x}
              y2={toPos.y}
              stroke={color}
              strokeWidth="1.5"
              strokeDasharray={dash}
              opacity={opacity}
            />
          );
        })}
        {actorPosition && targetPosition ? (
          <line
            x1={actorPosition.x}
            y1={actorPosition.y}
            x2={targetPosition.x}
            y2={targetPosition.y}
            stroke="#ff4f87"
            strokeWidth="2"
            strokeDasharray="10 8"
            filter="url(#fallback-glow)"
          />
        ) : null}
        <circle cx={center} cy="330" r="58" fill="url(#fallback-core)" stroke="rgba(77,199,255,.7)" filter="url(#fallback-glow)" />
        <circle cx={center} cy="330" r="8" fill="#bdf4ff" />

        {players.map((player) => {
          const position = getSeatPosition(player, players, center, seatRadius);
          const showRole = viewMode === "god" || (viewMode === "agent" && (player.seat === selectedSeat || teammates.includes(player.seat)));
          const color = showRole ? (fallbackColors[player.role] ?? "#56e3ff") : "#56e3ff";
          const isSpeaker = player.name === currentEvent.speaker;
          const active = isSpeaker || player.name === currentEvent.target || (viewMode === "agent" && selectedSeat === player.seat);

          return (
            <g key={player.seat} data-testid="fallback-seat" transform={`translate(${position.x} ${position.y})`}>
              <ellipse rx="54" ry="28" fill={color} opacity={player.alive ? "0.28" : "0.09"} filter={active ? "url(#fallback-glow)" : undefined} />
              <circle r={active ? 34 : 28} fill="rgba(2,8,19,.82)" stroke={active ? "#ffffff" : color} strokeWidth={active ? "2.5" : "1.5"} />
              <circle r="18" fill={player.alive ? color : "#546178"} opacity={player.alive ? "0.92" : "0.55"} />
              <text y="-48" fill="#ffffff" fontSize="18" fontWeight="700" textAnchor="middle">
                {player.name}
              </text>
              <text y="-29" fill={color} fontSize="11" fontWeight="700" textAnchor="middle">
                {showRole ? player.role : (player.alive ? "存活" : "出局")}
              </text>
              {isSpeaker && hasSpeechContent(currentEvent) && (
                <foreignObject x="-130" y="-110" width="260" height="80" overflow="visible">
                  <div className="speech-bubble" style={{ minWidth: 140, maxWidth: 260 }}>
                    <div className="bubble-header">
                      <span>{player.name} · {currentEvent.action ?? "发言"}</span>
                    </div>
                    <div className="bubble-body">
                      {truncateBubble(replaceWithFirstPerson(currentEvent.text ?? "", selectedSeat), 60)}
                    </div>
                  </div>
                </foreignObject>
              )}
            </g>
          );
        })}
      </svg>

      <div className="absolute left-5 top-5 rounded-md border border-cyan/25 bg-slate-950/70 px-4 py-3">
        <div className="text-sm font-semibold text-cyan">2D 战术圆桌</div>
        <div className="mt-1 text-xs text-slate-400">{reasonText[reason]}</div>
      </div>
      <div className="absolute right-5 top-5 rounded-md border border-cyan/20 bg-slate-950/70 p-3 text-xs text-slate-300">
        <LegendLine color="bg-cyan" label="信任关系" />
        <LegendLine color="bg-danger" label="怀疑关系" />
        <div className="flex items-center gap-2"><span className="h-px w-8 border-t border-dashed border-gold" />信息交互</div>
      </div>
      <div className="absolute bottom-5 left-1/2 w-[min(620px,calc(100%-40px))] -translate-x-1/2 rounded-md border border-cyan/20 bg-slate-950/85 p-4">
        <div className="mb-2 flex items-center gap-3">
          <span className={cn("rounded border border-cyan/25 px-3 py-1 text-sm text-cyan", !currentEvent.speaker && "text-slate-500")}>{currentEvent.speaker || "系统"}</span>
          <span className="text-xs text-gold">{currentEvent.action ?? currentEvent.type}</span>
          {currentEvent.target && <span className="rounded border border-danger/25 px-2 py-0.5 text-xs text-danger">→ {currentEvent.target}</span>}
        </div>
        {hasSpeechContent(currentEvent) && (
          <p className="max-h-[80px] overflow-y-auto whitespace-pre-wrap text-sm leading-6 text-slate-200">{replaceWithFirstPerson(currentEvent.text ?? "", selectedSeat)}</p>
        )}
      </div>
    </div>
  );
}

function LegendLine({ color, label }: { color: string; label: string }) {
  return (
    <div className="mb-2 flex items-center gap-2">
      <span className={cn("h-px w-8", color)} />
      {label}
    </div>
  );
}

function getSeatPosition(player: PlayerSeat, players: PlayerSeat[], center: number, radius: number) {
  const index = players.findIndex((candidate) => candidate.seat === player.seat);
  const angle = (Math.PI * 2 * Math.max(index, 0)) / Math.max(players.length, 1) - Math.PI / 2;

  return {
    x: center + Math.cos(angle) * radius,
    y: 330 + Math.sin(angle) * radius * 0.66
  };
}

const reasonText: Record<NonNullable<ArenaStageFallbackProps["reason"]>, string> = {
  loading: "3D 圆桌加载中，先展示实时 2D 观战态",
  webgl: "当前环境 WebGL 不可用，已切换稳定观战态",
  error: "3D 渲染异常，已切换稳定观战态"
};

function hasSpeechContent(event: ArenaEvent): boolean {
  return (event.type === "model_call" || event.type === "decision") && Boolean(event.text) && event.text !== "模型调用";
}

function truncateBubble(text: string, max: number): string {
  if (!text) return "";
  return text.length > max ? text.slice(0, max) + "…" : text;
}
