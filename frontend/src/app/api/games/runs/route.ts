import { NextResponse } from "next/server";
import { getRunStatus, startGameRun } from "@/lib/server/game-runner";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const runId = url.searchParams.get("runId");
  if (!runId) {
    return NextResponse.json({ ok: false, error: "missing runId" }, { status: 400 });
  }

  try {
    return NextResponse.json({
      ok: true,
      ...(await getRunStatus(runId))
    });
  } catch (error) {
    return NextResponse.json({
      ok: false,
      error: error instanceof Error ? error.message : "run status failed"
    }, { status: 400 });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const run = await startGameRun(body);
    return NextResponse.json({
      ok: true,
      ...run
    });
  } catch (error) {
    return NextResponse.json({
      ok: false,
      error: error instanceof Error ? error.message : "启动对局失败"
    }, { status: 400 });
  }
}
