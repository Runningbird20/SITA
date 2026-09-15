import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AlertStatusSelect } from "./AlertStatusSelect";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AlertStatusSelect", () => {
  it("changing the status calls PUT with the new status", async () => {
    const fetchMock = vi.fn(async () => {
      return new Response(
        JSON.stringify({
          id: "alert-1",
          detection_id: "det-1",
          incident_id: null,
          severity: "high",
          confidence: 0.8,
          status: "false_positive",
          rationale: "test",
          severity_factors: {},
          first_event_at: "2026-01-15T03:00:00Z",
          last_event_at: "2026-01-15T03:00:00Z",
          created_at: "2026-01-15T03:00:00Z",
          updated_at: "2026-01-15T03:00:00Z",
        }),
        { status: 200 },
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<AlertStatusSelect alertId="alert-1" status="new" />);

    await user.selectOptions(screen.getByLabelText("Alert status"), "false_positive");

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/alerts/alert-1/status");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({ status: "false_positive" });
    expect(screen.getByLabelText("Alert status")).toHaveValue("false_positive");
  });

  it("reverts the selection and shows an error when the request fails", async () => {
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

    render(<AlertStatusSelect alertId="alert-1" status="new" />);
    await user.selectOptions(screen.getByLabelText("Alert status"), "resolved");

    await waitFor(() => expect(screen.getByText(/couldn't save/i)).toBeInTheDocument());
    expect(screen.getByLabelText("Alert status")).toHaveValue("new");
  });
});
