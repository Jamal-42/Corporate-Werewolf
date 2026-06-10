"use client";

import { useState } from "react";
import { Activity, CircleAlert, Lock, Radio, Unlock } from "lucide-react";
import type { ArenaEvent, ViewMode } from "@/types/game";
import { cn } from "@/lib/utils";

type EventStreamProps = {
  events: ArenaEvent[];
  allEvents?: ArenaEvent[];
  currentEventId: string;
  viewMode: ViewMode;
  selectedSeat?: number;
  onSelect: (event: ArenaEvent) => void;
};

const filters = ["全部", "发言", "投票", "系统", "预警"] as const;
type FilterType = (typeof filters)[number];

const filterMatchers: Record<FilterType, (e: ArenaEvent) => boolean> = {
  "全部": () => true,
  "发言": (e) => e.type === "model_call" && !!e.speaker && e.speaker !== "旁白" && e.speaker !== "系统" && e.speaker !== "全员",
  "投票": (e) => e.type === "vote_result" || (e.type === "decision" && (e.phase?.includes("vote") || e.action?.includes("投票") || false)),
  "系统": (e) => ["game_init", "night_start", "day_start", "state_snapshot", "game_over", "skill_resolution"].includes(e.type) || e.type === "decision" || (e.type === "model_call" && (!e.speaker || e.speaker === "旁白" || e.speaker === "系统" || e.speaker === "全员")),
  "预警": (e) => e.type === "error" || e.type === "death",
};

const typeLabels: Record<string, string> = {
  model_call: "发言",
  decision: "决策",
  vote_result: "投票结果",
  skill_resolution: "技能结算",
  death: "出局",
  night_start: "夜晚",
  day_start: "白天",
  game_init: "初始化",
  game_over: "结束",
  state_snapshot: "状态快照",
  error: "异常"
};

export function EventStream({ events, allEvents, currentEventId, viewMode, selectedSeat, onSelect }: EventStreamProps) {
  const [activeFilter, setActiveFilter] = useState<FilterType>("全部");

  const hiddenCount = (allEvents?.length ?? events.length) - events.length;
  const displayEvents = events.filter(filterMatchers[activeFilter]);
  const lastVisibleTs = events.at(-1)?.timestamp;
  const pendingAfter = allEvents && lastVisibleTs
    ? allEvents.filter((e) => !events.includes(e) && (e.timestamp ?? "") > (lastVisibleTs ?? "")).length
    : 0;

  const seatLabel = selectedSeat ? `${selectedSeat}号` : "";
  const toFirstPerson = (s: string) => seatLabel ? s.replaceAll(seatLabel, "我") : s;

  return (
    <section className="hud-panel flex min-h-0 flex-col p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="section-title">
          实时事件流
          <span className="ml-2 text-xs font-normal text-slate-400">({displayEvents.length}/{events.length})</span>
        </div>
        <div className="flex gap-2 text-cyan/70">
          <Activity className="h-4 w-4" />
          <Radio className="h-4 w-4" />
        </div>
      </div>
      <div className="mb-4 grid grid-cols-5 gap-1 rounded-md border border-cyan/10 bg-black/20 p-1 text-xs">
        {filters.map((filter) => (
          <button
            key={filter}
            onClick={() => setActiveFilter(filter)}
            className={cn("rounded-sm px-2 py-2 text-slate-400", activeFilter === filter && "bg-cyan/15 text-cyan")}
          >
            {filter}
          </button>
        ))}
      </div>
      <div className="scrollbar-thin min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
        {displayEvents.map((event) => {
          const active = event.id === currentEventId;
          const warning = event.type === "error" || event.type === "death";
          const expanded = active && (event.type === "model_call" || event.type === "decision");
          return (
            <button
              key={event.id}
              type="button"
              onClick={() => onSelect(event)}
              className={cn(
                "group relative w-full rounded-md border px-3 py-3 text-left transition",
                active ? "border-cyan/60 bg-cyan/12 shadow-glow" : "border-cyan/10 bg-cyan/[0.035] hover:border-cyan/40 hover:bg-cyan/[0.07]"
              )}
            >
              <div className="absolute bottom-0 left-4 top-0 w-px bg-cyan/20" />
              <div className="relative z-10 grid grid-cols-[62px_1fr_48px] gap-3">
                <div className="font-mono text-[11px] text-slate-400">{event.timestamp?.slice(11, 19) ?? "22:15:30"}</div>
                <div>
                  <div className={cn("mb-1 flex items-center gap-2 text-sm font-semibold", warning ? "text-danger" : "text-cyan")}>
                    {warning ? <CircleAlert className="h-3.5 w-3.5" /> : <span className="h-2 w-2 rounded-full bg-cyan shadow-glow" />}
                    {typeLabels[event.type] ?? event.type}
                  </div>
                  <p className={cn("text-xs leading-5 text-slate-300 whitespace-pre-wrap", expanded ? "" : "line-clamp-3")}>{toFirstPerson(event.text ?? "")}</p>
                  {event.target ? <p className="mt-1 text-xs text-slate-500">{`${toFirstPerson(event.speaker ?? "系统")} -> ${toFirstPerson(event.target ?? "")}`}</p> : null}
                </div>
                <div className="text-right text-[11px] text-slate-500">
                  <div>{toFirstPerson(event.speaker ?? "系统")}</div>
                  <div className="mt-2 inline-flex items-center gap-1 rounded bg-white/5 px-1.5 py-1">
                    {event.visibility === "public" ? <Unlock className="h-3 w-3" /> : <Lock className="h-3 w-3" />}
                    {event.visibility === "public" ? "公开" : viewMode === "god" ? "私有" : "权限"}
                  </div>
                </div>
              </div>
            </button>
          );
        })}
        {viewMode === "agent" && pendingAfter > 0 && (
          <div className="flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900/50 px-3 py-2 text-xs text-slate-400">
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-slate-500" />
            其他玩家行动中（{pendingAfter} 条不可见事件）
          </div>
        )}
        {viewMode === "agent" && hiddenCount > 0 && pendingAfter === 0 && displayEvents.length > 0 && (
          <div className="mt-1 text-center text-[11px] text-slate-500">
            共 {hiddenCount} 条事件因视角限制不可见
          </div>
        )}
      </div>
    </section>
  );
}
