import { NextResponse } from "next/server";
import { enqueueHumanInput } from "@/lib/server/human-input-queue";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const item = await enqueueHumanInput(body);
    return NextResponse.json({
      ok: true,
      item
    });
  } catch (error) {
    return NextResponse.json({
      ok: false,
      error: error instanceof Error ? error.message : "human input failed"
    }, { status: 400 });
  }
}
