import { NextResponse } from "next/server";
import { deriveGameSummary, sampleEvents, samplePlayers } from "@/lib/game-data";
import { discoverReplayFiles, readReplayFile } from "@/lib/server/replay-files";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const file = url.searchParams.get("file");

  if (file) {
    try {
      return NextResponse.json(await readReplayFile(file));
    } catch (error) {
      return NextResponse.json({ error: error instanceof Error ? error.message : "日志读取失败" }, { status: 400 });
    }
  }

  const files = await discoverReplayFiles();
  if (files.length) {
    return NextResponse.json({
      ...(await readReplayFile(files[0].id)),
      files
    });
  }

  return NextResponse.json({
    id: "demo-agent-arena",
    name: "AI 狼人杀演示局",
    players: samplePlayers,
    events: sampleEvents,
    summary: deriveGameSummary(sampleEvents),
    files: []
  });
}
