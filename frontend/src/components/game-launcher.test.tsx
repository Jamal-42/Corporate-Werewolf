import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GameLauncher } from "./game-launcher";

describe("GameLauncher", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("passes the launched run to the page so it can auto-follow the jsonl", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      ok: true,
      runId: "game_6p_20260607_120000",
      pid: 42,
      logBase: "exports/runs/game_6p_20260607_120000",
      stdoutLog: "exports/runs/game_6p_20260607_120000.process.log"
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    }));
    vi.stubGlobal("fetch", fetchMock);
    const onStarted = vi.fn();

    render(<GameLauncher onStarted={onStarted} />);
    fireEvent.click(screen.getByRole("button"));

    await waitFor(() => {
      expect(onStarted).toHaveBeenCalledWith(expect.objectContaining({
        runId: "game_6p_20260607_120000",
        logBase: "exports/runs/game_6p_20260607_120000",
        fileId: "runs/game_6p_20260607_120000.jsonl"
      }));
    });
  });
});
