import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FeedbackButtons } from "./FeedbackButtons";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("FeedbackButtons", () => {
  it("casting a vote calls PUT with the rating and marks the button active", async () => {
    const fetchMock = vi.fn(async () => {
      return new Response(
        JSON.stringify({
          id: "fb-1",
          analysis_result_id: "ar-1",
          rating: "up",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        }),
        { status: 200 },
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<FeedbackButtons analysisResultId="ar-1" initialRating={null} />);

    await user.click(screen.getByLabelText("Mark this analysis as useful"));

    await waitFor(() =>
      expect(screen.getByLabelText("Mark this analysis as useful")).toHaveAttribute(
        "aria-pressed",
        "true",
      ),
    );
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/analysis-results/ar-1/feedback");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({ rating: "up" });
  });

  it("clicking the already-active rating clears it via DELETE", async () => {
    const fetchMock = vi.fn(async () => {
      return new Response(null, { status: 204 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<FeedbackButtons analysisResultId="ar-1" initialRating="up" />);
    expect(screen.getByLabelText("Mark this analysis as useful")).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    await user.click(screen.getByLabelText("Mark this analysis as useful"));

    await waitFor(() =>
      expect(screen.getByLabelText("Mark this analysis as useful")).toHaveAttribute(
        "aria-pressed",
        "false",
      ),
    );
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.method).toBe("DELETE");
  });

  it("reverts and shows an error when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ error: { code: "server_error", message: "boom", details: null } }),
            { status: 500 },
          ),
      ),
    );
    const user = userEvent.setup();

    render(<FeedbackButtons analysisResultId="ar-1" initialRating={null} />);
    await user.click(screen.getByLabelText("Mark this analysis as useful"));

    await waitFor(() => expect(screen.getByText(/couldn't save/i)).toBeInTheDocument());
    expect(screen.getByLabelText("Mark this analysis as useful")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });
});
