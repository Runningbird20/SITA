import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EmptyState, ErrorState, LoadingState } from "./QueryState";

describe("LoadingState", () => {
  it("shows the default label", () => {
    render(<LoadingState />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("shows a custom label", () => {
    render(<LoadingState label="Fetching incidents…" />);
    expect(screen.getByText("Fetching incidents…")).toBeInTheDocument();
  });
});

describe("EmptyState", () => {
  it("shows the given message", () => {
    render(<EmptyState message="No alerts found" />);
    expect(screen.getByText("No alerts found")).toBeInTheDocument();
  });
});

describe("ErrorState", () => {
  it("shows the error message without a retry button when onRetry is omitted", () => {
    render(<ErrorState message="Failed to load" />);
    expect(screen.getByText("Failed to load")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });

  it("calls onRetry when the retry button is clicked", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(<ErrorState message="Failed to load" onRetry={onRetry} />);

    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
