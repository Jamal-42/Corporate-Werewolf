import { NextResponse } from "next/server";
import { sampleEvents } from "@/lib/game-data";
import { discoverReplayFiles, readReplayFile } from "@/lib/server/replay-files";
import { delay, formatSseMessage, tailReplayUpdates } from "@/lib/server/sse";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const file = url.searchParams.get("file");
  const tail = url.searchParams.get("tail") === "1";
  const intervalMs = Math.max(120, Math.min(2500, Number(url.searchParams.get("interval") ?? 720)));

  if (tail && file) {
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      async start(controller) {
        try {
          for await (const update of tailReplayUpdates(file, { intervalMs, signal: request.signal })) {
            if (request.signal.aborted) break;

            if (update.type === "meta") {
              controller.enqueue(encoder.encode(formatSseMessage({
                event: "arena-meta",
                data: {
                  id: update.replay.id,
                  name: update.replay.name,
                  players: update.replay.players,
                  totalEvents: update.replay.events.length
                }
              })));
              continue;
            }

            if (update.type === "event") {
              controller.enqueue(encoder.encode(formatSseMessage({
                id: update.event.id || String(update.index + 1),
                event: "arena-event",
                data: {
                  ...update.event,
                  streamIndex: update.index
                }
              })));
              continue;
            }

            if (update.type === "complete") {
              controller.enqueue(encoder.encode(formatSseMessage({
                event: "arena-complete",
                data: {
                  id: file,
                  totalEvents: update.totalEvents
                }
              })));
              break;
            }

            // heartbeat: SSE comment to keep connection alive
            controller.enqueue(encoder.encode(": heartbeat\n\n"));
          }
        } finally {
          controller.close();
        }
      }
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive"
      }
    });
  }

  let replay;
  try {
    if (file) {
      replay = await readReplayFile(file);
    } else {
      const files = await discoverReplayFiles();
      replay = files.length ? await readReplayFile(files[0].id) : {
        id: "demo-agent-arena",
        name: "AI 狼人杀演示局",
        players: [],
        events: sampleEvents,
        summary: {
          totalEvents: sampleEvents.length,
          aliveCount: 0,
          latestPhase: sampleEvents.at(-1)?.phase ?? "未知",
          deaths: sampleEvents.filter((event) => event.type === "death").length
        }
      };
    }
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "无法创建事件流" }, { status: 400 });
  }

  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      controller.enqueue(encoder.encode(formatSseMessage({
        event: "arena-meta",
        data: {
          id: replay.id,
          name: replay.name,
          totalEvents: replay.events.length
        }
      })));

      for (const [index, event] of replay.events.entries()) {
        if (request.signal.aborted) break;
        controller.enqueue(encoder.encode(formatSseMessage({
          id: event.id || String(index + 1),
          event: "arena-event",
          data: {
            ...event,
            streamIndex: index
          }
        })));
        await delay(intervalMs);
      }

      controller.enqueue(encoder.encode(formatSseMessage({
        event: "arena-complete",
        data: {
          id: replay.id,
          totalEvents: replay.events.length
        }
      })));
      controller.close();
    }
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive"
    }
  });
}
