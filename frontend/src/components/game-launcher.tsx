"use client";

import { Rocket, RotateCw } from "lucide-react";
import { useEffect, useState } from "react";

type LaunchStatus =
  | { state: "idle"; message: string }
  | { state: "loading"; message: string }
  | { state: "success"; message: string; runId: string; logBase: string }
  | { state: "error"; message: string };

export type StartedRunPayload = {
  runId: string;
  pid: number;
  logBase: string;
  stdoutLog: string;
  fileId: string;
  humanSeat: number;
};

export function GameLauncher({ onStarted, onHumanSeatChange }: { onStarted?: (run: StartedRunPayload) => void; onHumanSeatChange?: (seat: number) => void }) {
  const [players, setPlayers] = useState(6);
  const [promptVersion, setPromptVersion] = useState("v2");
  const [skillsVersion, setSkillsVersion] = useState("");
  const [skillsVersions, setSkillsVersions] = useState<string[]>([]);
  const [humanSeat, setHumanSeat] = useState("");
  const [status, setStatus] = useState<LaunchStatus>({ state: "idle", message: "配置参数后启动新对局" });

  useEffect(() => {
    fetch("/api/games/skills-versions")
      .then((res) => res.json())
      .then((data) => { if (data.versions) setSkillsVersions(data.versions); })
      .catch(() => {});
  }, []);

  async function launchGame() {
    setStatus({ state: "loading", message: "正在启动 Python 对局进程..." });
    try {
      const response = await fetch("/api/games/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          players,
          promptVersion,
          skillsVersion,
          skillsTargets: "all",
          humanSeat
        })
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error ?? "启动失败");
      }
      const run: StartedRunPayload = {
        runId: payload.runId,
        pid: payload.pid,
        logBase: payload.logBase,
        stdoutLog: payload.stdoutLog,
        fileId: `runs/${payload.runId}.jsonl`,
        humanSeat: humanSeat ? Number(humanSeat) : 0
      };
      setStatus({
        state: "success",
        message: `已启动 PID ${run.pid}，等待 JSONL 接入...`,
        runId: run.runId,
        logBase: run.logBase
      });
      onStarted?.(run);
    } catch (error) {
      setStatus({ state: "error", message: error instanceof Error ? error.message : "启动失败" });
    }
  }

  return (
    <section className="hud-panel p-4">
      <div className="section-title mb-3">新建对局</div>
      <div className="grid grid-cols-2 gap-2">
        <label className="grid gap-1 text-xs text-slate-400">
          玩家数
          <select value={players} onChange={(event) => setPlayers(Number(event.target.value))} className="hud-select">
            {[6, 9, 12].map((count) => (
              <option key={count} value={count}>
                {count} 人局
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-xs text-slate-400">
          Prompt
          <input value={promptVersion} onChange={(event) => setPromptVersion(event.target.value)} className="hud-select" />
        </label>
        <label className="grid gap-1 text-xs text-slate-400">
          Skills 版本
          <select value={skillsVersion} onChange={(event) => setSkillsVersion(event.target.value)} className="hud-select">
            <option value="">默认（不注入）</option>
            {skillsVersions.map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-xs text-slate-400">
          真人座位
          <select value={humanSeat} onChange={(event) => { setHumanSeat(event.target.value); onHumanSeatChange?.(Number(event.target.value) || 0); }} className="hud-select">
            <option value="">无（全 AI）</option>
            {Array.from({ length: players }, (_, i) => i + 1).map((seat) => (
              <option key={seat} value={seat}>{seat} 号位</option>
            ))}
          </select>
        </label>
      </div>
      <button
        type="button"
        onClick={launchGame}
        disabled={status.state === "loading"}
        className="hud-button mt-3 flex w-full items-center justify-center gap-2 px-4 py-3 text-sm text-cyan disabled:cursor-not-allowed disabled:opacity-60"
      >
        {status.state === "loading" ? <RotateCw className="h-4 w-4 animate-spin" /> : <Rocket className="h-4 w-4" />}
        启动对局
      </button>
      <div className="mt-3 rounded-md border border-cyan/10 bg-black/20 p-3 text-xs leading-5 text-slate-400">
        <div className={status.state === "error" ? "text-danger" : status.state === "success" ? "text-cyan" : ""}>{status.message}</div>
        {status.state === "success" ? (
          <div className="mt-1">
            <div>Run：{status.runId}</div>
            <div>日志：{status.logBase}.jsonl</div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
