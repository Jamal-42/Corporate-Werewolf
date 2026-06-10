import { NextResponse } from "next/server";
import { transcribeAsr } from "@/lib/server/voice-gateway";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const audio = formData.get("audio");
    if (!(audio instanceof File)) {
      throw new Error("audio file is required");
    }

    const result = await transcribeAsr(Buffer.from(await audio.arrayBuffer()), {
      provider: formData.get("provider") ?? "dashscope",
      model: formData.get("model") ?? undefined,
      mimeType: audio.type,
      sampleRate: formData.get("sampleRate") ?? undefined
    });

    return NextResponse.json({
      ok: true,
      ...result
    });
  } catch (error) {
    return NextResponse.json({
      ok: false,
      error: error instanceof Error ? error.message : "ASR failed"
    }, { status: 400 });
  }
}
