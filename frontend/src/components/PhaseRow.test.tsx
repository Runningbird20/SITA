import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Phase } from "../data/phases";
import { PhaseRow } from "./PhaseRow";

const PHASE: Phase = {
  id: 3,
  title: "Detection Engine",
  goal: "Turn raw events into real findings.",
  evaluate: () => "implemented",
};

describe("PhaseRow", () => {
  it("shows the phase id, title, and goal", () => {
    render(<PhaseRow phase={PHASE} status="implemented" />);
    expect(screen.getByText("03")).toBeInTheDocument();
    expect(screen.getByText("Detection Engine")).toBeInTheDocument();
    expect(screen.getByText("Turn raw events into real findings.")).toBeInTheDocument();
  });

  it("pads a single-digit id with a leading zero", () => {
    render(<PhaseRow phase={{ ...PHASE, id: 7 }} status="implemented" />);
    expect(screen.getByText("07")).toBeInTheDocument();
  });

  it("renders the status label via StatusDot", () => {
    render(<PhaseRow phase={PHASE} status="broken" />);
    expect(screen.getByText("Broken")).toBeInTheDocument();
  });
});
