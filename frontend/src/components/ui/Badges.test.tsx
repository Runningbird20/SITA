import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AiBadge, Pill, SeverityBadge } from "./Badges";

describe("SeverityBadge", () => {
  it("renders the severity text and a matching data-severity attribute", () => {
    render(<SeverityBadge severity="critical" />);
    const badge = screen.getByText("critical");
    expect(badge).toHaveAttribute("data-severity", "critical");
  });
});

describe("AiBadge", () => {
  it("always reads AI-generated, regardless of context", () => {
    render(<AiBadge />);
    expect(screen.getByText("AI-generated")).toBeInTheDocument();
  });
});

describe("Pill", () => {
  it("renders its children", () => {
    render(<Pill>open</Pill>);
    expect(screen.getByText("open")).toBeInTheDocument();
  });
});
