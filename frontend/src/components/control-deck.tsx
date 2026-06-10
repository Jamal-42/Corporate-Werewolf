"use client";

import { useState } from "react";
import { Bot, Eye, Mic, Pause, Play, Radio, RotateCcw, ScanLine, Volume2 } from "lucide-react";
import type { ViewMode } from "@/types/game";
import type { PlayerSeat } from "@/types/game";
import { cn } from "@/lib/utils";

type ControlDeckProps = {
  viewMode: ViewMode;
  selectedSeat: number;
  speaking: boolean;
  liveTracking: boolean;
  autoTts: boolean;
  ttsQueueSize: number;
  replaying: boolean;
  players: PlayerSeat[];
  replayName: string;
  onViewModeChange: (mode: ViewMode) => void;
  onSeatChange: (seat: number) => void;
  onToggleLiveTracking: () => void;
  onToggleAutoTts: () => void;
  onPlayVoice: () => void;
  onStopVoice: () => void;
  onToggleReplay: () => void;
  onToggleDataPanel: () => void;
};

const modes: Array<{ value: ViewMode; label: string; icon: typeof Eye }> = [
  { value: "god", label: "上帝视角", icon: Eye },
  { value: "public", label: "公共视角", icon: Radio },
  { value: "agent", label: "单 Agent 视角", icon: Bot }
];

export function ControlDeck({
  viewMode,
  selectedSeat,
  speaking,
  liveTracking,
  autoTts,
  ttsQueueSize,
  replaying,
  players,
  replayName,
  onViewModeChange,
  onSeatChange,
  onToggleLiveTracking,
  onToggleAutoTts,
  onPlayVoice,
  onStopVoice,
  onToggleReplay,
  onToggleDataPanel
}: ControlDeckProps) {
  const [tab, setTab] = useState<"watch" | "system">("watch");

  return (
    <section className="hud-panel p-4">
      <div className="mb-4 flex items-center justify-between">
        <div className="section-title">控制中枢</div>
        <ScanLine className="h-5 w-5 text-cyan" />
      </div>
      <div className="mb-4 grid grid-cols-2 gap-2 border-b border-cyan/10 pb-3 text-sm">
        <button type="button" onClick={() => setTab("watch")} className={cn("py-2", tab === "watch" ? "border-b border-cyan font-semibold text-cyan" : "text-slate-400")}>观战控制台</button>
        <button type="button" onClick={() => setTab("system")} className={cn("py-2", tab === "system" ? "border-b border-cyan font-semibold text-cyan" : "text-slate-400")}>系统控制台</button>
      </div>

      {tab === "watch" ? (
        <WatchTab
          viewMode={viewMode}
          selectedSeat={selectedSeat}
          speaking={speaking}
          liveTracking={liveTracking}
          autoTts={autoTts}
          ttsQueueSize={ttsQueueSize}
          replaying={replaying}
          onViewModeChange={onViewModeChange}
          onSeatChange={onSeatChange}
          onToggleLiveTracking={onToggleLiveTracking}
          onToggleAutoTts={onToggleAutoTts}
          onPlayVoice={onPlayVoice}
          onStopVoice={onStopVoice}
          onToggleReplay={onToggleReplay}
          onToggleDataPanel={onToggleDataPanel}
        />
      ) : (
        <SystemTab players={players} liveTracking={liveTracking} replayName={replayName} speaking={speaking} viewMode={viewMode} />
      )}
    </section>
  );
}

function WatchTab({
  viewMode, selectedSeat, speaking, liveTracking, autoTts, ttsQueueSize, replaying,
  onViewModeChange, onSeatChange, onToggleLiveTracking, onToggleAutoTts, onPlayVoice, onStopVoice, onToggleReplay, onToggleDataPanel
}: Omit<ControlDeckProps, "players" | "replayName">) {
  const agentDisabled = viewMode !== "agent";
  return (
    <>
      <div className="grid grid-cols-3 gap-2">
        {modes.map((mode) => {
          const Icon = mode.icon;
          return (
            <button
              key={mode.value}
              type="button"
              onClick={() => onViewModeChange(mode.value)}
              className={cn("hud-button flex items-center justify-center gap-2 px-2 py-3 text-sm", viewMode === mode.value && "is-active")}
            >
              <Icon className="h-4 w-4" />
              {mode.label}
            </button>
          );
        })}
      </div>
      <label className={cn("mt-4 grid gap-2 text-sm", agentDisabled ? "text-slate-600" : "text-slate-400")}>
        选择 Agent{agentDisabled && " (仅单Agent视角可用)"}
        <select
          value={selectedSeat}
          onChange={(event) => onSeatChange(Number(event.target.value))}
          disabled={agentDisabled}
          className={cn("hud-select", agentDisabled && "opacity-40")}
        >
          {Array.from({ length: 12 }, (_, index) => index + 1).map((seat) => (
            <option key={seat} value={seat}>
              {seat}号 Agent
            </option>
          ))}
        </select>
      </label>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <button
          type="button"
          onClick={onToggleLiveTracking}
          className={cn("hud-button flex items-center justify-center gap-2 px-2 py-3 text-sm text-cyan", liveTracking && "is-active")}
        >
          <Play className="h-4 w-4" />
          {liveTracking ? "停止跟踪" : "实时跟踪"}
        </button>
        <button
          type="button"
          onClick={onToggleReplay}
          className={cn("hud-button flex items-center justify-center gap-2 px-2 py-3 text-sm", replaying && "is-active text-cyan")}
        >
          <RotateCcw className="h-4 w-4" />
          {replaying ? "停止回放" : "回放分析"}
        </button>
        <button
          type="button"
          onClick={onToggleDataPanel}
          className="hud-button flex items-center justify-center gap-2 px-2 py-3 text-sm"
        >
          <ScanLine className="h-4 w-4" />
          数据面板
        </button>
      </div>
      <div className="mt-4 rounded-md border border-cyan/10 bg-cyan/[0.035] p-3">
        <div className="mb-3 flex items-center justify-between text-sm">
          <span className="text-slate-400">TTS 语音播报</span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              aria-pressed={autoTts}
              onClick={onToggleAutoTts}
              className={cn("hud-button flex h-8 items-center gap-1 px-2 text-xs", autoTts && "is-active")}
              title="切换实时事件自动播报"
            >
              <Radio className="h-3.5 w-3.5" />
              {autoTts ? "自动" : "手动"}
            </button>
            <button
              type="button"
              onClick={speaking ? onStopVoice : onPlayVoice}
              className={cn(
                "grid h-8 w-8 place-items-center rounded-full border",
                speaking ? "border-danger/50 bg-danger/15 text-danger" : "border-cyan/30 bg-cyan/10 text-cyan"
              )}
              title={speaking ? "停止播报" : "播报当前事件"}
            >
              {speaking ? <Pause className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
            </button>
          </div>
        </div>
        <div className="waveform mb-3" />
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <span className={cn("h-2 w-2 rounded-full", speaking ? "bg-cyan shadow-glow" : "bg-slate-600")} />
          {speaking ? "正在播报" : autoTts ? `队列待播 ${ttsQueueSize}` : "自动播报关闭"}
          <Mic className="ml-auto h-4 w-4 text-gold" />
        </div>
      </div>
    </>
  );
}

function SystemTab({ players, liveTracking, replayName, speaking, viewMode }: { players: PlayerSeat[]; liveTracking: boolean; replayName: string; speaking: boolean; viewMode: ViewMode }) {
  const modelSet = new Set(players.map((p) => p.model).filter(Boolean));
  const ttsEngine = speaking ? "DashScope Sambert" : "待机";

  return (
    <div className="space-y-3 text-xs">
      <InfoSection title="模型配置">
        {players.length > 0 ? (
          <div className="space-y-1">
            {players.map((p) => (
              <div key={p.seat} className="flex justify-between">
                <span className="text-slate-400">{p.name} ({viewMode === "god" ? p.role : "?"})</span>
                <span className="font-mono text-slate-300">{p.model || "unknown"}</span>
              </div>
            ))}
          </div>
        ) : (
          <span className="text-slate-500">暂无玩家数据</span>
        )}
      </InfoSection>

      <InfoSection title="连接状态">
        <StatusRow label="后端 API" status="connected" />
        <StatusRow label="SSE 实时流" status={liveTracking ? "connected" : "idle"} />
        <StatusRow label="TTS 引擎" status={speaking ? "active" : "idle"} detail={ttsEngine} />
      </InfoSection>

      <InfoSection title="运行信息">
        <div className="flex justify-between">
          <span className="text-slate-400">当前日志</span>
          <span className="max-w-[180px] truncate font-mono text-slate-300">{replayName || "无"}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-400">模型种类</span>
          <span className="font-mono text-slate-300">{modelSet.size > 0 ? [...modelSet].join(", ") : "—"}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-400">框架</span>
          <span className="font-mono text-slate-300">AgentScope + Next.js 14</span>
        </div>
      </InfoSection>
    </div>
  );
}

function InfoSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-cyan/10 bg-cyan/[0.03] p-3">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-cyan/70">{title}</div>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function StatusRow({ label, status, detail }: { label: string; status: "connected" | "active" | "idle" | "error"; detail?: string }) {
  const colors = { connected: "bg-emerald-400", active: "bg-cyan shadow-glow", idle: "bg-slate-600", error: "bg-danger" };
  const labels = { connected: "已连接", active: "运行中", idle: "待机", error: "异常" };
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-400">{label}</span>
      <div className="flex items-center gap-2">
        {detail && <span className="text-slate-500">{detail}</span>}
        <span className={cn("h-2 w-2 rounded-full", colors[status])} />
        <span className="text-slate-300">{labels[status]}</span>
      </div>
    </div>
  );
}
