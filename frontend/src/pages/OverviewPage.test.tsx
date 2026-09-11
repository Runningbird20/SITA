import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as resources from "../api/resources";
import { OverviewPage } from "./OverviewPage";

afterEach(() => {
  vi.restoreAllMocks();
});

function renderPage() {
  return render(
    <MemoryRouter>
      <OverviewPage />
    </MemoryRouter>,
  );
}

describe("OverviewPage", () => {
  it("shows a loading state before data arrives", () => {
    vi.spyOn(resources, "fetchIncidents").mockReturnValue(new Promise(() => {}));
    vi.spyOn(resources, "fetchAlerts").mockReturnValue(new Promise(() => {}));

    renderPage();
    expect(screen.getByText(/loading overview/i)).toBeInTheDocument();
  });

  it("shows severity counts and recent incidents once loaded", async () => {
    vi.spyOn(resources, "fetchIncidents").mockResolvedValue({
      items: [
        {
          id: "1",
          title: "SSH Brute Force",
          status: "open",
          severity: "critical",
          first_activity_at: "2026-01-15T03:00:00Z",
          last_activity_at: "2026-01-15T03:05:00Z",
          correlation_method: {},
          created_at: "2026-01-15T03:05:00Z",
          updated_at: "2026-01-15T03:05:00Z",
          alert_count: 2,
        },
      ],
      total: 1,
      limit: 200,
      offset: 0,
    });
    vi.spyOn(resources, "fetchAlerts").mockResolvedValue({
      items: [],
      total: 5,
      limit: 200,
      offset: 0,
    });

    renderPage();

    await waitFor(() => expect(screen.queryByText(/loading overview/i)).not.toBeInTheDocument());
    expect(screen.getByText("SSH Brute Force")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument(); // total alerts stat
    // One "1" among the severity stat cards, for critical.
    expect(screen.getAllByText("1").length).toBeGreaterThan(0);
  });

  it("shows an error state with a working retry", async () => {
    const fetchIncidents = vi
      .spyOn(resources, "fetchIncidents")
      .mockRejectedValueOnce(new Error("network error"))
      .mockResolvedValue({ items: [], total: 0, limit: 200, offset: 0 });
    vi.spyOn(resources, "fetchAlerts").mockResolvedValue({
      items: [],
      total: 0,
      limit: 200,
      offset: 0,
    });

    renderPage();

    await waitFor(() => expect(screen.getByText(/failed to load data/i)).toBeInTheDocument());
    expect(fetchIncidents).toHaveBeenCalledOnce();

    screen.getByRole("button", { name: /retry/i }).click();
    await waitFor(() => expect(fetchIncidents).toHaveBeenCalledTimes(2));
  });

  it("shows an empty-state message when there are no incidents yet", async () => {
    vi.spyOn(resources, "fetchIncidents").mockResolvedValue({
      items: [],
      total: 0,
      limit: 200,
      offset: 0,
    });
    vi.spyOn(resources, "fetchAlerts").mockResolvedValue({
      items: [],
      total: 0,
      limit: 200,
      offset: 0,
    });

    renderPage();

    await waitFor(() => expect(screen.getByText(/no incidents yet/i)).toBeInTheDocument());
  });
});
