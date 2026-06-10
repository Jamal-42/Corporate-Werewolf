"use client";

import { Mic, RefreshCw, Send, SquarePen, StopCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useVoice } from "@/hooks/use-voice";
import { cn } from "@/lib/utils";

type HumanConsoleProps = {
  runId: string;
  seat: number;
  urgent?: boolean;
  onSubmitted?: (text: string) => void;
};

export function HumanConsole({ runId, seat, urgent, onSubmitted }: HumanConsoleProps) {
  const [draft, setDraft] = useState("");
  const [recording, setRecording] = useState(false);
  const [asrStatus, setAsrStatus] = useState("等待语音输入");
  const [submitStatus, setSubmitStatus] = useState("选择真人座位后可提交");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const { capabilities, speechState, speakingText, startListening, resetTranscript } = useVoice();
  const [clientCaps, setClientCaps] = useState({ asr: false, tts: false });
  const transcript = speechState.transcript;
  const textValue = draft || transcript;

  useEffect(() => { setClientCaps(capabilities); }, [capabilities]);

  async function toggleCloudAsr() {
    if (recording) {
      recorderRef.current?.stop();
      setRecording(false);
      setAsrStatus("正在上传识别...");
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      startListening();
      setAsrStatus("浏览器录音不可用，已尝试本地识别");
      return;
    }

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream);
    chunksRef.current = [];
    recorderRef.current = recorder;
    recorder.ondataavailable = (event) => {
      if (event.data.size) chunksRef.current.push(event.data);
    };
    recorder.onstop = async () => {
      stream.getTracks().forEach((track) => track.stop());
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
      try {
        const formData = new FormData();
        formData.set("audio", blob, "human-input.webm");
        formData.set("provider", "dashscope");
        const response = await fetch("/api/voice/asr", {
          method: "POST",
          body: formData
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) throw new Error(payload.error ?? "ASR failed");
        setDraft(payload.text);
        setAsrStatus("识别完成，可编辑后提交");
      } catch (error) {
        setAsrStatus(error instanceof Error ? error.message : "ASR failed");
      }
    };
    recorder.start();
    setRecording(true);
    setAsrStatus("录音中，再点一次停止");
  }

  async function submitHumanInput() {
    const text = textValue.trim();
    if (!runId) {
      setSubmitStatus("请先选择或启动一局 runs 日志");
      return;
    }
    if (!text) {
      setSubmitStatus("请输入或识别一段发言");
      return;
    }

    setSubmitStatus("正在提交给后端队列...");
    try {
      const response = await fetch("/api/human/input", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          runId,
          seat,
          text,
          source: asrStatus.includes("识别完成") ? "asr" : "typed"
        })
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error ?? "submit failed");
      setSubmitStatus(`已提交给 ${seat} 号真人队列`);
      const submitted = text;
      setDraft("");
      resetTranscript();
      onSubmitted?.(submitted);
    } catch (error) {
      setSubmitStatus(error instanceof Error ? error.message : "提交失败");
    }
  }

  return (
    <section className={cn("hud-panel p-4", urgent && "ring-2 ring-gold/60 animate-pulse")}>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.28em] text-cyan">Human Console</p>
          <h2 className="mt-1 text-lg font-semibold">人机混战输入</h2>
        </div>
        <SquarePen className="h-6 w-6 text-cyan" />
      </div>
      <div className="mb-3 grid grid-cols-2 gap-2 text-xs text-slate-400">
        <div className="hud-card px-3 py-2">Run: <span className="text-cyan">{runId || "未选择"}</span></div>
        <div className="hud-card px-3 py-2">Seat: <span className="text-cyan">{seat}号</span></div>
      </div>
      <textarea
        value={textValue}
        onChange={(event) => setDraft(event.target.value)}
        rows={3}
        placeholder="输入你的发言，或点击 ASR 录音转写..."
        className="hud-select min-h-[72px] w-full resize-none p-3 text-sm leading-6"
      />
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={() => void toggleCloudAsr()}
          className={cn("hud-button flex items-center justify-center gap-2 px-3 py-2 text-sm text-cyan", recording && "is-active")}
        >
          {recording ? <StopCircle className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
          {recording ? "停止" : "ASR"}
        </button>
        <button
          type="button"
          onClick={() => {
            resetTranscript();
            setDraft("");
          }}
          className="hud-button flex items-center justify-center gap-2 px-3 py-2 text-sm"
        >
          <RefreshCw className="h-4 w-4" />
          清空
        </button>
      </div>
      <button type="button" onClick={() => void submitHumanInput()} className={cn("hud-button mt-3 flex w-full items-center justify-center gap-2 px-3 py-3 text-sm", urgent ? "text-gold ring-1 ring-gold/40" : "text-cyan")}>
        <Send className="h-4 w-4" />
        提交真人发言
      </button>
      <div className="mt-3 rounded-md border border-cyan/10 bg-black/20 p-3 text-xs leading-5 text-slate-400">
        ASR: {asrStatus} · 本地识别: {clientCaps.asr ? "可用" : "不可用"} · TTS: {clientCaps.tts ? "可回退" : "仅云端"}
        <div className="mt-1 text-cyan">{submitStatus}</div>
        {speakingText ? <div className="mt-1 text-cyan">正在播报: {speakingText.slice(0, 36)}...</div> : null}
      </div>
    </section>
  );
}
