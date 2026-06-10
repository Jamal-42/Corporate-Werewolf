import { NextResponse } from "next/server";
import { synthesizeTts } from "@/lib/server/voice-gateway";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const audio = await synthesizeTts(body);
    const payload = new Uint8Array(audio.bytes).buffer;
    return new Response(payload, {
      headers: {
        "Content-Type": audio.contentType,
        "Cache-Control": "no-store",
        "X-Voice-Provider": audio.provider
      }
    });
  } catch (error) {
    return NextResponse.json({
      ok: false,
      error: error instanceof Error ? error.message : "TTS failed"
    }, { status: 400 });
  }
}
