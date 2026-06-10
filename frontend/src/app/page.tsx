"use client";

import dynamic from "next/dynamic";
import { motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Bell, Bot, Cpu, Database, Network, Settings, Sparkles, UserCircle2 } from "lucide-react";
import { ControlDeck } from "@/components/control-deck";
import { DataPanel } from "@/components/data-panel";
import { EventStream } from "@/components/event-stream";
import { GameLauncher, type StartedRunPayload } from "@/components/game-launcher";
import { HumanConsole } from "@/components/human-console";
import { ReviewPanel } from "@/components/review-panel";
import { deriveGameSummary, getVisibleEvents, sampleEvents, samplePlayers } from "@/lib/game-data";
import { dequeueTtsItem, enqueueTtsItem, formatEventSpeech, getEventVoiceRole, replaceWithFirstPerson, shouldAutoSpeakEvent, type TtsQueueItem } from "@/lib/tts-queue";
import { useVoice } from "@/hooks/use-voice";
import { analyzeEventSentiment, normalizeSentiments } from "@/lib/sentiment";
import type { ArenaEvent, PlayerSeat, ReplayFile, ReplayPayload, ViewMode } from "@/types/game";

const ArenaStage = dynamic(() => import("@/components/arena-stage").then((mod) => mod.ArenaStage), {
  ssr: false,
  loading: () => (
    <div className="hud-panel grid min-h-[560px] place-items-center text-cyan">
      加载战术圆桌...
    </div>
  )
});

export default function Home() {
  const [viewMode, setViewMode] = useState<ViewMode>("god");
  const [selectedSeat, setSelectedSeat] = useState(5);
  const [currentEvent, setCurrentEvent] = useState<ArenaEvent>(sampleEvents[3]);
  const [players, setPlayers] = useState<PlayerSeat[]>(samplePlayers);
  const [events, setEvents] = useState<ArenaEvent[]>(sampleEvents);
  const [files, setFiles] = useState<ReplayFile[]>([]);
  const [activeReplayId, setActiveReplayId] = useState("");
  const [activeReplayName, setActiveReplayName] = useState("demo-agent-arena");
  const [loadState, setLoadState] = useState<"loading" | "ready" | "fallback">("loading");
  const [liveTracking, setLiveTracking] = useState(false);
  const [liveWaiting, setLiveWaiting] = useState(false);
  const [humanWaiting, setHumanWaiting] = useState(false);
  const [pendingRun, setPendingRun] = useState<StartedRunPayload | null>(null);
  const [humanSeat, setHumanSeat] = useState(0);
  const [autoTts, setAutoTts] = useState(false);
  const [ttsQueue, setTtsQueue] = useState<TtsQueueItem[]>([]);
  const [replaying, setReplaying] = useState(false);
  const [showDataPanel, setShowDataPanel] = useState(false);
  const [expandedEvent, setExpandedEvent] = useState<ArenaEvent | null>(null);
  const streamRef = useRef<EventSource | null>(null);
  const processingTtsRef = useRef(false);
  const prefetchingRef = useRef(false);
  const ttsLocksCurrentRef = useRef(false);
  const replayTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingHumanWaitingRef = useRef(false);
  const ttsSettingsRef = useRef({ autoTts, viewMode, selectedSeat });
  const lastEventTimeRef = useRef(0);
  const eventsRef = useRef<ArenaEvent[]>(events);
  const { speak, prefetchAudio, stopSpeaking, speakingText } = useVoice();

  const visibleEvents = useMemo(() => getVisibleEvents(events, viewMode, selectedSeat), [events, viewMode, selectedSeat]);
  const summary = useMemo(() => deriveGameSummary(events), [events]);
  const livePlayers = useMemo(() => {
    if (!players.length) return players;
    const snapshotIdx = [...events].reverse().findIndex((e) => e.alivePlayers?.length);
    const snapshotEvent = snapshotIdx >= 0 ? events[events.length - 1 - snapshotIdx] : undefined;
    if (snapshotEvent?.alivePlayers?.length) {
      const aliveSet = new Set(snapshotEvent.alivePlayers);
      const realIdx = events.length - 1 - snapshotIdx;
      const laterDeaths = events.slice(realIdx + 1).filter((e) => e.type === "death" && e.speaker).map((e) => e.speaker!);
      for (const d of laterDeaths) aliveSet.delete(d);
      return players.map((p) => ({ ...p, alive: aliveSet.has(p.name) }));
    }
    const deadNames = new Set(events.filter((e) => e.type === "death").map((e) => e.speaker).filter(Boolean));
    if (!deadNames.size) return players;
    return players.map((p) => ({ ...p, alive: !deadNames.has(p.name) }));
  }, [players, events]);
  const safeCurrentEvent = visibleEvents.find((event) => event.id === currentEvent.id) ?? visibleEvents.at(-1) ?? sampleEvents[0];
  const aliveCount = livePlayers.filter((player) => player.alive).length;
  const wolfCount = livePlayers.filter((player) => player.faction === "间谍" && player.alive).length;
  const voteProgress = events.filter((event) => event.type === "vote_result").length;
  const gameOver = events.some((event) => event.type === "game_over");
  const activeRunId = deriveRunId(activeReplayId);

  useEffect(() => {
    void loadReplay();

    return () => {
      streamRef.current?.close();
    };
  }, []);

  useEffect(() => {
    ttsSettingsRef.current = { autoTts, viewMode, selectedSeat };
  }, [autoTts, selectedSeat, viewMode]);

  useEffect(() => {
    eventsRef.current = events;
  }, [events]);

  useEffect(() => {
    if (!liveTracking) {
      setLiveWaiting(false);
      return;
    }
    lastEventTimeRef.current = Date.now();
    setLiveWaiting(false);
    const timer = setInterval(() => {
      if (Date.now() - lastEventTimeRef.current > 5000) {
        setLiveWaiting(true);
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [liveTracking, events.length]);

  useEffect(() => {
    if (!autoTts || processingTtsRef.current || ttsQueue.length === 0) {
      // Queue drained and nothing playing — flush pending human prompt
      if (pendingHumanWaitingRef.current && !processingTtsRef.current && ttsQueue.length === 0) {
        pendingHumanWaitingRef.current = false;
        setHumanWaiting(true);
      }
      return;
    }

    const { next } = dequeueTtsItem(ttsQueue);
    if (!next) return;

    processingTtsRef.current = true;
    setTtsQueue((previous) => previous.filter((item) => item.id !== next.id));

    // Sync the highlighted event to what's being spoken
    const matchedEvent = eventsRef.current.find((e) => e.id === next.id);
    if (matchedEvent) {
      ttsLocksCurrentRef.current = true;
      setCurrentEvent(matchedEvent);
    }

    // Prefetch next item's audio while current one plays
    const remaining = ttsQueue.filter((item) => item.id !== next.id);
    if (remaining.length > 0) {
      void prefetchAudio(remaining[0].text, remaining[0].voiceRole);
    }

    void speak(next.text, next.voiceRole)
      .catch(() => { /* prevent unhandled rejection */ })
      .finally(() => {
        processingTtsRef.current = false;
        ttsLocksCurrentRef.current = false;
        if (ttsSettingsRef.current.autoTts) {
          setTtsQueue((previous) => [...previous]);
        }
      });
  }, [autoTts, speak, prefetchAudio, ttsQueue]);

  useEffect(() => {
    const runId = pendingRun?.runId;
    if (!runId) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function pollRunStatus(targetRunId: string) {
      try {
        const response = await fetch(`/api/games/runs?runId=${encodeURIComponent(targetRunId)}`, { cache: "no-store" });
        const status = (await response.json()) as {
          ok?: boolean;
          state?: "missing" | "starting" | "ready";
          fileId?: string;
        };
        if (cancelled) return;

        if (response.ok && status.ok && status.state === "ready" && status.fileId) {
          setPendingRun(null);
          setActiveReplayId(status.fileId);
          setLoadState("ready");
          if (!cancelled) {
            startLiveTracking(status.fileId, { tail: true });
          }
          return;
        }
      } catch {
        // Keep polling; a new Python run may need a few seconds before creating JSONL.
      }

      if (!cancelled) {
        timer = setTimeout(() => void pollRunStatus(targetRunId), 1500);
      }
    }

    timer = setTimeout(() => void pollRunStatus(runId), 800);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [pendingRun?.runId]);

  async function loadReplay(file?: string) {
    stopLiveTracking();
    setLoadState("loading");
    try {
      const response = await fetch(file ? `/api/games?file=${encodeURIComponent(file)}` : "/api/games", { cache: "no-store" });
      const payload = (await response.json()) as ReplayPayload & { error?: string };
      if (!response.ok || payload.error) throw new Error(payload.error ?? "加载失败");
      setPlayers(payload.players.length ? payload.players : samplePlayers);
      setEvents(payload.events.length ? payload.events : sampleEvents);
      setFiles(payload.files ?? files);
      setActiveReplayId(file ?? payload.id);
      setActiveReplayName(payload.name ?? payload.id);
      setCurrentEvent(payload.events.at(-1) ?? sampleEvents[0]);
      setLoadState(payload.files?.length || file ? "ready" : "fallback");
    } catch {
      setPlayers(samplePlayers);
      setEvents(sampleEvents);
      setCurrentEvent(sampleEvents[3]);
      setActiveReplayId("");
      setActiveReplayName("demo-agent-arena");
      setLoadState("fallback");
    }
  }

  function startLiveTracking(fileId = activeReplayId, options: { tail?: boolean; keepEvents?: boolean } = {}) {
    streamRef.current?.close();
    const params = new URLSearchParams({ interval: "800" });
    if (fileId) params.set("file", fileId);
    if (options.tail) params.set("tail", "1");
    const source = new EventSource(`/api/games/stream?${params.toString()}`);
    streamRef.current = source;
    setLiveTracking(true);
    if (!options.keepEvents) {
      setEvents([]);
    }
    setTtsQueue([]);

    source.addEventListener("arena-meta", (message) => {
      const meta = JSON.parse((message as MessageEvent).data) as {
        id: string;
        name?: string;
        players?: PlayerSeat[];
      };
      setActiveReplayId(meta.id);
      setActiveReplayName(meta.name ?? meta.id);
      setLoadState("ready");
      if (meta.players?.length) {
        setPlayers(meta.players);
      }
    });

    source.addEventListener("arena-event", (message) => {
      const event = JSON.parse((message as MessageEvent).data) as ArenaEvent;
      setEvents((previous) => {
        if (previous.some((e) => e.id === event.id)) return previous;
        return [...previous, event];
      });
      if (event.type === "human_waiting") {
        // Delay showing input prompt until TTS finishes playing previous events
        if (ttsSettingsRef.current.autoTts && processingTtsRef.current) {
          pendingHumanWaitingRef.current = true;
        } else {
          setHumanWaiting(true);
        }
      } else {
        setHumanWaiting(false);
        pendingHumanWaitingRef.current = false;
      }
      const settings = ttsSettingsRef.current;
      const speakable = shouldAutoSpeakEvent(event, settings.viewMode, settings.selectedSeat);
      // Skip TTS for events the human player themselves generated
      const isSelf = settings.selectedSeat > 0 && event.speaker === `${settings.selectedSeat}号`;
      if (settings.autoTts && speakable && !isSelf) {
        const speechText = formatEventSpeech(event, settings.selectedSeat);
        const voiceRole = getEventVoiceRole(event);
        setTtsQueue((previous) => enqueueTtsItem(previous, { id: event.id, text: speechText, voiceRole }));
        if (processingTtsRef.current) {
          // Something is playing — this item is likely next, prefetch it now
          void prefetchAudio(speechText, voiceRole);
        } else if (!prefetchingRef.current) {
          prefetchingRef.current = true;
          void prefetchAudio(speechText, voiceRole).finally(() => { prefetchingRef.current = false; });
        }
      }
      // When autoTts is on and TTS is actively speaking, don't override currentEvent.
      // But if nothing is being spoken (no lock), update so the bubble stays current.
      if (!settings.autoTts || !ttsLocksCurrentRef.current) {
        setCurrentEvent(event);
      }
    });

    source.addEventListener("arena-complete", () => {
      source.close();
      if (streamRef.current === source) {
        streamRef.current = null;
      }
      setLiveTracking(false);
      if (fileId) {
        void loadReplay(fileId);
      }
    });

    source.onerror = () => {
      source.close();
      if (streamRef.current === source) {
        streamRef.current = null;
      }
      setLiveTracking(false);
    };
  }

  function stopLiveTracking() {
    streamRef.current?.close();
    streamRef.current = null;
    setLiveTracking(false);
  }

  function toggleLiveTracking() {
    if (liveTracking) {
      stopLiveTracking();
      return;
    }
    startLiveTracking(activeReplayId, { tail: true });
  }

  function toggleAutoTts() {
    if (autoTts) {
      setTtsQueue([]);
      stopSpeaking();
      processingTtsRef.current = false;
      ttsLocksCurrentRef.current = false;
    }
    setAutoTts((value) => !value);
  }

  function toggleReplay() {
    if (replaying) {
      if (replayTimerRef.current) clearTimeout(replayTimerRef.current);
      replayTimerRef.current = null;
      setReplaying(false);
      stopSpeaking();
      return;
    }
    if (visibleEvents.length === 0) return;
    setReplaying(true);
    // If current event is already the last one, start from the beginning
    const currentIndex = visibleEvents.findIndex((e) => e.id === safeCurrentEvent.id);
    let index = currentIndex >= visibleEvents.length - 1 ? -1 : currentIndex;

    async function step() {
      index++;
      if (index >= visibleEvents.length) {
        setReplaying(false);
        replayTimerRef.current = null;
        return;
      }
      const event = visibleEvents[index];
      setCurrentEvent(event);

      const settings = ttsSettingsRef.current;
      if (settings.autoTts && shouldAutoSpeakEvent(event, settings.viewMode, settings.selectedSeat)) {
        const speech = formatEventSpeech(event, settings.selectedSeat);
        const role = getEventVoiceRole(event);
        await speak(speech, role);
        replayTimerRef.current = setTimeout(() => void step(), 800);
      } else {
        replayTimerRef.current = setTimeout(() => void step(), 2500);
      }
    }

    replayTimerRef.current = setTimeout(() => void step(), 200);
  }

  function followStartedRun(run: StartedRunPayload) {
    stopLiveTracking();
    setPendingRun(run);
    setHumanSeat(run.humanSeat);
    if (run.humanSeat > 0) {
      setViewMode("agent");
      setSelectedSeat(run.humanSeat);
    }
    setLoadState("loading");
    setActiveReplayId(run.fileId);
    setActiveReplayName(run.runId);
    setEvents([]);
    setCurrentEvent(sampleEvents[0]);
  }

  return (
    <main className="cockpit-shell min-h-screen overflow-auto p-2 text-white">
      <div className="mx-auto grid h-[calc(100vh-16px)] min-h-[920px] min-w-[1500px] max-w-[1920px] grid-rows-[88px_minmax(0,1fr)] gap-3">
        <TopHud players={livePlayers} liveTracking={liveTracking} replayName={activeReplayName} eventCount={events.length} />

        <section className="grid min-h-0 grid-cols-[350px_minmax(720px,1fr)_390px] gap-3">
          <aside className="grid min-h-0 grid-rows-[minmax(0,1fr)_330px] gap-3">
            <EventStream events={visibleEvents} allEvents={events} currentEventId={safeCurrentEvent.id} viewMode={viewMode} selectedSeat={selectedSeat} onSelect={(evt) => {
              setCurrentEvent(evt);
              // If TTS is idle and has pending items, nudge it to resume
              if (autoTts && !processingTtsRef.current && ttsQueue.length > 0) {
                setTtsQueue((prev) => [...prev]);
              }
            }} />
            {(liveWaiting || humanWaiting) && (
              <div className={`flex items-center gap-2 rounded-md border px-3 py-2 text-xs ${humanWaiting ? "border-gold/40 bg-gold/[0.06] text-gold animate-pulse" : "border-cyan/20 bg-cyan/[0.04] text-cyan"}`}>
                <span className={`inline-block h-2 w-2 rounded-full ${humanWaiting ? "bg-gold" : "animate-pulse bg-cyan"}`} />
                {humanWaiting
                  ? (events.findLast((e) => e.type === "human_waiting")?.text || "轮到你发言了！请在右侧「人机混战输入」提交")
                  : "Agent 阐述观点中，请耐心等待"}
              </div>
            )}
            <EmotionRadar players={livePlayers} events={events} />
          </aside>

          <section className="grid min-h-0 grid-rows-[142px_minmax(0,1fr)_142px] gap-3">
            <TacticalSummary
              eventCount={summary.totalEvents}
              voteProgress={voteProgress}
              aliveCount={aliveCount}
              wolfCount={wolfCount}
              gameOver={gameOver}
              loadState={loadState}
              replayName={activeReplayName}
              files={files}
              activeReplayId={activeReplayId}
              onSelectReplay={(file) => void loadReplay(file)}
            />
            <ArenaStage players={livePlayers} currentEvent={safeCurrentEvent} viewMode={viewMode} selectedSeat={selectedSeat} events={events} onBubbleClick={setExpandedEvent} />
            <Timeline events={events} currentEvent={safeCurrentEvent} onSelect={setCurrentEvent} />
          </section>

          <aside className="scrollbar-thin grid min-h-0 grid-rows-[520px_minmax(320px,1fr)_280px_360px] gap-3 overflow-y-auto pr-1">
            <ControlDeck
              viewMode={viewMode}
              selectedSeat={selectedSeat}
              speaking={Boolean(speakingText)}
              liveTracking={liveTracking}
              autoTts={autoTts}
              ttsQueueSize={ttsQueue.length}
              replaying={replaying}
              players={livePlayers}
              replayName={activeReplayName}
              onViewModeChange={setViewMode}
              onSeatChange={setSelectedSeat}
              onToggleLiveTracking={toggleLiveTracking}
              onToggleAutoTts={toggleAutoTts}
              onPlayVoice={() => void speak(formatEventSpeech(safeCurrentEvent, selectedSeat), getEventVoiceRole(safeCurrentEvent))}
              onStopVoice={() => { stopSpeaking(); setAutoTts(false); setTtsQueue([]); processingTtsRef.current = false; ttsLocksCurrentRef.current = false; }}
              onToggleReplay={toggleReplay}
              onToggleDataPanel={() => setShowDataPanel((v) => !v)}
            />
            <ReviewPanel summary={summary} currentEvent={safeCurrentEvent} players={livePlayers} events={events} selectedSeat={selectedSeat} />
            <GameLauncher onStarted={followStartedRun} onHumanSeatChange={setHumanSeat} />
            <HumanConsole runId={activeRunId} seat={humanSeat} urgent={humanWaiting} onSubmitted={(text) => {
              setHumanWaiting(false);
              if (autoTts && text) {
                void speak(text, "villager");
              }
            }} />
          </aside>
        </section>
      </div>
      {showDataPanel && <DataPanel players={livePlayers} events={events} onClose={() => setShowDataPanel(false)} />}
      {expandedEvent && <BubbleOverlay event={expandedEvent} selectedSeat={selectedSeat} onClose={() => setExpandedEvent(null)} />}
    </main>
  );
}

function deriveRunId(fileId: string): string {
  const matched = fileId.match(/^runs\/(.+)\.jsonl$/);
  return matched?.[1] ?? "";
}

function TopHud({ players, liveTracking, replayName, eventCount }: { players: PlayerSeat[]; liveTracking: boolean; replayName: string; eventCount: number }) {
  const modelChip = useMemo(() => {
    const models = new Set(players.map((p) => p.model).filter(Boolean));
    if (models.size === 0) return "多模型待载入";
    const brands = new Set<string>();
    for (const m of models) {
      if (m.startsWith("qwen") || m.startsWith("Qwen")) brands.add("Qwen");
      else if (m.startsWith("deepseek") || m.startsWith("DeepSeek")) brands.add("DeepSeek");
      else if (m.startsWith("gpt") || m.startsWith("GPT")) brands.add("GPT");
      else if (m.startsWith("claude") || m.startsWith("Claude")) brands.add("Claude");
      else if (m.startsWith("glm") || m.startsWith("chatglm")) brands.add("GLM");
      else if (m.startsWith("ernie") || m.startsWith("ERNIE")) brands.add("文心");
      else brands.add(m.split("-")[0]);
    }
    const label = [...brands].join(" + ");
    return models.size > 1 ? `${label} 多模型` : label;
  }, [players]);

  const dataChip = useMemo(() => {
    if (liveTracking) return `实时对局 · ${eventCount} 事件`;
    if (eventCount > 0) return `回放 · ${eventCount} 事件`;
    return "等待对局";
  }, [liveTracking, eventCount]);

  return (
    <header className="top-hud grid grid-cols-[330px_1fr_590px] items-center gap-3 px-4">
      <div className="flex items-center gap-3">
        <div className="grid h-12 w-12 place-items-center rounded-full border border-cyan/60 bg-cyan/10 shadow-glow">
          <Sparkles className="h-6 w-6 text-cyan" />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-bold tracking-[0.2em]">AGENT</div>
          <div className="text-sm font-bold tracking-[0.2em]">TEAM ARENA</div>
        </div>
      </div>
      <div className="text-center">
        <h1 className="text-[34px] font-black tracking-[0.08em] text-white">
          <span className="mr-4 bg-gradient-to-r from-cyan to-blue-400 bg-clip-text text-transparent">AI</span>
          职场狼人杀智能体博弈驾驶舱
        </h1>
        <div className="mt-1 text-sm tracking-[0.28em] text-slate-400">多模态感知 x 实时推理 x 战术决策</div>
      </div>
      <div className="flex items-center justify-end gap-3">
        <TopChip icon={Bot} label="模式" value="AI 人机混战" />
        <TopChip icon={Cpu} label="模型" value={modelChip} />
        <TopChip icon={Network} label="数据" value={dataChip} />
        <Settings className="h-5 w-5 text-slate-300" />
        <Bell className="h-5 w-5 text-slate-300" />
        <div className="grid h-12 w-12 place-items-center rounded-full border border-cyan/40 bg-cyan/10">
          <UserCircle2 className="h-7 w-7 text-slate-200" />
        </div>
      </div>
    </header>
  );
}

function TopChip({ icon: Icon, label, value }: { icon: typeof Bot; label: string; value: string }) {
  return (
    <div className="hud-chip min-w-[130px] px-4 py-2">
      <div className="flex items-center gap-2 text-xs text-cyan">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div className="mt-1 text-sm font-semibold">{value}</div>
    </div>
  );
}

function TacticalSummary({
  eventCount,
  voteProgress,
  aliveCount,
  wolfCount,
  gameOver,
  loadState,
  replayName,
  files,
  activeReplayId,
  onSelectReplay
}: {
  eventCount: number;
  voteProgress: number;
  aliveCount: number;
  wolfCount: number;
  gameOver: boolean;
  loadState: "loading" | "ready" | "fallback";
  replayName: string;
  files: ReplayFile[];
  activeReplayId: string;
  onSelectReplay: (file: string) => void;
}) {
  const [showPicker, setShowPicker] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const dropRef = useRef<HTMLDivElement>(null);
  const totalRounds = Math.max(1, Math.ceil(eventCount / 10));
  const progress = gameOver ? "100%" : eventCount > 0 ? `${Math.min(99, Math.round((eventCount / Math.max(eventCount + 5, 20)) * 100))}%` : "0%";

  useEffect(() => {
    if (!showPicker) return;
    function handleClick(e: MouseEvent) {
      if (
        btnRef.current?.contains(e.target as Node) ||
        dropRef.current?.contains(e.target as Node)
      ) return;
      setShowPicker(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showPicker]);

  const dropdownPosition = (): React.CSSProperties => {
    if (!btnRef.current) return { display: "none" };
    const rect = btnRef.current.getBoundingClientRect();
    return {
      position: "fixed",
      top: rect.bottom + 8,
      right: window.innerWidth - rect.right,
      zIndex: 9999,
    };
  };

  return (
    <section className="hud-panel p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="section-title">战术态势总览</div>
      </div>
      <div className="grid grid-cols-[repeat(5,minmax(0,1fr))_150px] gap-2">
        <Metric label="发言总数" value={eventCount} delta={gameOver ? "已结束" : "进行中"} />
        <Metric label="投票轮次" value={voteProgress} delta={gameOver ? "已结束" : "当前"} />
        <Metric label="存活人数" value={aliveCount} delta={`共${aliveCount}人`} />
        <Metric label="间谍存活" value={gameOver ? wolfCount : `${wolfCount}?`} delta={gameOver ? (wolfCount === 0 ? "已清除" : "仍存活") : "待确认"} />
        <Metric label="任务进度" value={progress} delta={gameOver ? "已完成" : "推进中"} />
        <div>
          <button
            ref={btnRef}
            type="button"
            onClick={() => setShowPicker(!showPicker)}
            className="hud-card grid h-full w-full cursor-pointer place-items-center text-sm text-cyan transition-colors hover:border-cyan/50 hover:bg-cyan/[0.06]"
          >
            <Database className="mb-1 h-5 w-5" />
            {loadState === "ready" ? "真实日志" : loadState === "loading" ? "加载中" : "演示数据"}
            <span className="mt-1 max-w-[130px] truncate text-[11px] text-slate-400">{replayName}</span>
          </button>
          {showPicker && createPortal(
            <div ref={dropRef} style={dropdownPosition()} className="max-h-[320px] w-[340px] overflow-y-auto rounded-md border border-cyan/30 bg-slate-950/95 p-2 shadow-lg backdrop-blur-md">
              <div className="mb-2 px-2 text-xs text-slate-400">选择对局日志</div>
              {files.length === 0 ? (
                <div className="px-3 py-4 text-center text-sm text-slate-500">暂无日志文件，启动对局后自动生成</div>
              ) : files.map((file) => (
                <button
                  key={file.id}
                  type="button"
                  onClick={() => { onSelectReplay(file.id); setShowPicker(false); }}
                  className={`flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm transition-colors hover:bg-cyan/10 ${file.id === activeReplayId ? "bg-cyan/[0.08] text-cyan" : "text-slate-300"}`}
                >
                  <Database className="h-3.5 w-3.5 shrink-0 text-cyan/60" />
                  <span className="truncate">{file.name}</span>
                  {file.id === activeReplayId && <span className="ml-auto shrink-0 text-[10px] text-cyan">当前</span>}
                </button>
              ))}
            </div>,
            document.body
          )}
        </div>
      </div>
    </section>
  );
}

function Metric({ label, value, delta }: { label: string; value: string | number; delta: string }) {
  return (
    <div className="hud-card p-3">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="mt-2 flex items-end gap-2">
        <span className="font-mono text-3xl font-semibold">{value}</span>
        <span className="mb-1 text-xs text-emerald-300">{delta}</span>
      </div>
    </div>
  );
}

function EmotionRadar({ players, events }: { players: PlayerSeat[]; events: ArenaEvent[] }) {
  const analyzed = useMemo(() => normalizeSentiments(analyzeEventSentiment(events, players)), [events, players]);
  const displayPlayers = analyzed.slice(0, 9);
  const count = displayPlayers.length || 1;

  const positivePoints = displayPlayers.map((p, i) => {
    const angle = (Math.PI * 2 * i) / count - Math.PI / 2;
    const radius = 30 + p.positiveRatio * 60;
    return `${110 + Math.cos(angle) * radius},${110 + Math.sin(angle) * radius}`;
  });

  const negativePoints = displayPlayers.map((p, i) => {
    const angle = (Math.PI * 2 * i) / count - Math.PI / 2;
    const radius = 30 + p.negativeRatio * 60;
    return `${110 + Math.cos(angle) * radius},${110 + Math.sin(angle) * radius}`;
  });

  const heatPoints = displayPlayers.map((p, i) => {
    const angle = (Math.PI * 2 * i) / count - Math.PI / 2;
    const radius = 30 + p.heat * 60;
    return `${110 + Math.cos(angle) * radius},${110 + Math.sin(angle) * radius}`;
  });

  return (
    <section className="hud-panel p-4">
      <div className="section-title mb-3">全局情绪热力图</div>
      <div className="grid place-items-center">
        <svg viewBox="0 0 220 220" className="h-[230px] w-full max-w-[300px]">
          {[30, 55, 80].map((radius) => (
            <circle key={radius} cx="110" cy="110" r={radius} fill="none" stroke="rgba(77,199,255,.16)" />
          ))}
          {displayPlayers.map((p, i) => {
            const angle = (Math.PI * 2 * i) / count - Math.PI / 2;
            const x = 110 + Math.cos(angle) * 95;
            const y = 110 + Math.sin(angle) * 95;
            return (
              <g key={p.seat}>
                <line x1="110" y1="110" x2={x} y2={y} stroke="rgba(77,199,255,.09)" />
                <text x={x} y={y} fill="#9fb2d8" fontSize="10" textAnchor="middle">
                  {p.name}
                </text>
              </g>
            );
          })}
          {positivePoints.length > 0 && (
            <polygon points={positivePoints.join(" ")} fill="rgba(34,211,238,.2)" stroke="#22d3ee" strokeWidth="1.5" />
          )}
          {negativePoints.length > 0 && (
            <polygon points={negativePoints.join(" ")} fill="rgba(251,113,133,.18)" stroke="#fb7185" strokeWidth="1.5" />
          )}
          {heatPoints.length > 0 && (
            <polygon points={heatPoints.join(" ")} fill="rgba(251,191,36,.12)" stroke="#fbbf24" strokeWidth="1" strokeDasharray="4 2" />
          )}
        </svg>
      </div>
      <div className="mt-1 flex justify-center gap-5 text-xs text-slate-400">
        <span className="text-cyan">正面</span>
        <span className="text-rose-400">负面</span>
        <span className="text-amber-400">被关注</span>
      </div>
    </section>
  );
}

function Timeline({ events, currentEvent, onSelect }: { events: ArenaEvent[]; currentEvent: ArenaEvent; onSelect: (e: ArenaEvent) => void }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLButtonElement>(null);
  const dragState = useRef({ dragging: false, startX: 0, scrollLeft: 0 });
  const currentIdx = events.findIndex((e) => e.id === currentEvent.id);
  const gameOver = events.some((e) => e.type === "game_over");

  useEffect(() => {
    if (activeRef.current && scrollRef.current) {
      const container = scrollRef.current;
      const node = activeRef.current;
      const left = node.offsetLeft - container.clientWidth / 2 + node.clientWidth / 2;
      container.scrollTo({ left, behavior: "smooth" });
    }
  }, [currentEvent.id]);

  const onMouseDown = (e: React.MouseEvent) => {
    const el = scrollRef.current;
    if (!el) return;
    dragState.current = { dragging: true, startX: e.pageX - el.offsetLeft, scrollLeft: el.scrollLeft };
    el.style.cursor = "grabbing";
  };
  const onMouseMove = (e: React.MouseEvent) => {
    if (!dragState.current.dragging) return;
    const el = scrollRef.current!;
    const x = e.pageX - el.offsetLeft;
    el.scrollLeft = dragState.current.scrollLeft - (x - dragState.current.startX);
  };
  const onMouseUp = () => {
    dragState.current.dragging = false;
    if (scrollRef.current) scrollRef.current.style.cursor = "grab";
  };

  const phaseColor = (e: ArenaEvent) => {
    if (e.phase?.includes("夜")) return "bg-indigo-500";
    if (e.phase?.includes("讨论")) return "bg-cyan";
    if (e.phase?.includes("投票") || e.phase?.includes("vote")) return "bg-amber-400";
    if (e.type === "game_over") return "bg-emerald-400";
    return "bg-slate-500";
  };

  return (
    <section className="hud-panel min-w-0 overflow-hidden p-4">
      <div className="mb-2 flex items-center justify-between">
        <div className="section-title">对局时间轴</div>
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <span className="font-mono text-cyan">{currentIdx + 1}</span>
          <span>/</span>
          <span className="font-mono">{events.length}</span>
          {gameOver && <span className="ml-2 rounded bg-emerald-500/20 px-1.5 py-0.5 text-emerald-300">已结束</span>}
        </div>
      </div>
      <div
        ref={scrollRef}
        className="overflow-x-scroll pb-2"
        style={{ scrollbarWidth: "thin", scrollbarColor: "rgba(34,211,238,.3) transparent", cursor: "grab" }}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      >
        <div className="relative flex items-center" style={{ width: `${Math.max(events.length * 28, 200)}px`, height: "56px" }}>
          <div className="absolute left-3 right-3 top-[18px] h-[2px] bg-gradient-to-r from-cyan/20 via-cyan/40 to-cyan/20" />
          {events.map((e, i) => {
            const isActive = e.id === currentEvent.id;
            const isPast = i <= currentIdx;
            const isPhaseStart = i === 0 || e.phase !== events[i - 1]?.phase || e.round !== events[i - 1]?.round;
            return (
              <button
                key={e.id}
                ref={isActive ? activeRef : undefined}
                type="button"
                onClick={() => onSelect(e)}
                className="group relative flex flex-col items-center"
                style={{ width: "28px", flexShrink: 0 }}
                title={`${e.speaker ?? "系统"}: ${(e.text ?? e.action ?? "").slice(0, 30)}`}
              >
                <div className={`h-3.5 w-3.5 rounded-full border-2 transition-all duration-150 ${
                  isActive ? `border-white ${phaseColor(e)} scale-150 shadow-[0_0_10px_rgba(34,211,238,.8)]` :
                  isPast ? `border-transparent ${phaseColor(e)} opacity-70 group-hover:opacity-100 group-hover:scale-125` :
                  "border-slate-600 bg-slate-800 group-hover:border-slate-400"
                }`} />
                {isPhaseStart && (
                  <span className={`mt-1 whitespace-nowrap text-[9px] leading-none ${isActive ? "text-cyan font-bold" : "text-slate-500"}`}>
                    {e.phase?.includes("夜") ? `R${e.round ?? ""}夜` :
                     e.phase?.includes("讨论") ? `R${e.round ?? ""}议` :
                     e.phase?.includes("投票") ? `R${e.round ?? ""}票` :
                     e.type === "game_over" ? "终" : ""}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>
      <div className="mt-1 flex items-center justify-center gap-4 text-[10px] text-slate-500">
        <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-indigo-500" />夜晚</span>
        <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-cyan" />讨论</span>
        <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-amber-400" />投票</span>
        <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-emerald-400" />结局</span>
      </div>
    </section>
  );
}

function BubbleOverlay({ event, selectedSeat, onClose }: { event: ArenaEvent; selectedSeat: number; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div
        className="relative w-[560px] max-h-[70vh] overflow-y-auto rounded-sm border border-cyan/40 bg-[#030e1e]/98 p-0 shadow-[0_0_40px_rgba(77,199,255,0.12)]"
        style={{ clipPath: "polygon(0 0, calc(100% - 16px) 0, 100% 16px, 100% 100%, 16px 100%, 0 calc(100% - 16px))" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-cyan/20 bg-gradient-to-r from-cyan/10 to-transparent px-5 py-3">
          <div className="flex items-center gap-3">
            <span className="h-2 w-2 rounded-full bg-cyan shadow-[0_0_6px_#4dc7ff] animate-pulse" />
            <span className="text-sm font-semibold text-cyan">{event.speaker ?? "系统"}</span>
            <span className="text-xs text-slate-500">{event.action ?? event.type}</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs text-slate-500">{event.timestamp?.slice(11, 19) ?? ""}</span>
            <button onClick={onClose} className="grid h-6 w-6 place-items-center rounded border border-cyan/30 text-xs text-slate-400 hover:text-cyan">✕</button>
          </div>
        </div>
        <div className="px-5 py-4 text-sm leading-7 text-slate-200 whitespace-pre-wrap">
          {replaceWithFirstPerson(event.text ?? "", selectedSeat)}
        </div>
        {event.target && (
          <div className="border-t border-cyan/10 px-5 py-2 text-xs text-slate-500">
            目标：{event.target}
          </div>
        )}
      </div>
    </div>
  );
}
