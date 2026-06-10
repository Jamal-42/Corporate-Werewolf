import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { sampleEvents, samplePlayers } from "@/lib/game-data";
import { ArenaStageFallback } from "./arena-stage-fallback";

describe("ArenaStageFallback", () => {
  it("renders a tactical table with players and current event context", () => {
    render(
      <ArenaStageFallback
        players={samplePlayers}
        currentEvent={sampleEvents[3]}
        viewMode="god"
        selectedSeat={5}
        reason="loading"
      />
    );

    expect(screen.getByText("2D 战术圆桌")).toBeTruthy();
    expect(screen.getAllByText("3号").length).toBeGreaterThan(0);
    expect(screen.getAllByText("5号").length).toBeGreaterThan(0);
    expect(screen.getByText("背调")).toBeTruthy();
    expect(screen.getAllByTestId("fallback-seat")).toHaveLength(samplePlayers.length);
  });
});
