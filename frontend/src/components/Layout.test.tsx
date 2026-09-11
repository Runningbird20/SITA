import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PipelineJobType } from "../api/types";
import { AuthContext } from "./AuthContext";
import { Layout } from "./Layout";

function pendingJob(jobType: PipelineJobType) {
  return {
    id: "job-1",
    job_type: jobType,
    status: "pending",
    since: null,
    current_stage: null,
    progress_current: null,
    progress_total: null,
    result: null,
    error: null,
    created_at: "2026-01-01T00:00:00Z",
    started_at: null,
    completed_at: null,
  };
}

function completedJob(jobType: PipelineJobType, result: unknown) {
  return {
    ...pendingJob(jobType),
    status: "completed",
    current_stage: null,
    result,
    started_at: "2026-01-01T00:00:01Z",
    completed_at: "2026-01-01T00:00:05Z",
  };
}

function renderLayout(
  user: { username: string; role: "admin" | "analyst" } | null,
  logout = vi.fn(),
) {
  return render(
    <AuthContext.Provider value={{ user: user as never, logout }}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<div>page content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Layout — admin-only action buttons", () => {
  it("shows Run pipeline and Reanalyze when auth is disabled (user is null)", () => {
    renderLayout(null);
    expect(screen.getByRole("button", { name: /run pipeline/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^reanalyze$/i })).toBeInTheDocument();
  });

  it("shows Run pipeline and Reanalyze for an admin", () => {
    renderLayout({ username: "admin1", role: "admin" });
    expect(screen.getByRole("button", { name: /run pipeline/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^reanalyze$/i })).toBeInTheDocument();
  });

  it("hides both Run pipeline and Reanalyze for an analyst", () => {
    renderLayout({ username: "analyst1", role: "analyst" });
    expect(screen.queryByRole("button", { name: /run pipeline/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^reanalyze$/i })).not.toBeInTheDocument();
  });

  it("Reanalyze schedules a job, polls it, and shows the resulting summary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        if (init?.method === "POST") {
          return new Response(JSON.stringify(pendingJob("triage_reanalyze")), { status: 202 });
        }
        return new Response(
          JSON.stringify(
            completedJob("triage_reanalyze", {
              since: null,
              incidents_processed: 3,
              analysis_results_created: 18,
              analysis_results_skipped: 0,
              recommendations_created: 4,
              mitre_mappings_created: 2,
              by_task_type: {},
            }),
          ),
          { status: 200 },
        );
      }),
    );
    const user = userEvent.setup();
    renderLayout(null);

    await user.click(screen.getByRole("button", { name: /^reanalyze$/i }));

    await screen.findByText(/18 AI result\(s\) regenerated across 3 incident\(s\)/i);
  });

  it("Run pipeline schedules a job, polls it, and shows the resulting summary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        if (init?.method === "POST") {
          return new Response(JSON.stringify(pendingJob("pipeline_run")), { status: 202 });
        }
        return new Response(
          JSON.stringify(
            completedJob("pipeline_run", {
              since: null,
              detection: { since: null, rules_run: 9, alerts_created: 2, alerts_by_rule: {} },
              ioc: {
                since: null,
                events_scanned: 0,
                iocs_created: 0,
                iocs_updated: 0,
                event_links_created: 0,
                alert_links_created: 0,
                iocs_by_type: {},
              },
              mitre: {
                since: null,
                detection_technique_links_created: 0,
                alerts_processed: 0,
                alert_technique_mappings_created: 0,
              },
              correlation: {
                since: null,
                alerts_processed: 2,
                incidents_created: 1,
                incidents_joined: 0,
                host_entities_created: 0,
                host_links_created: 0,
              },
              triage: {
                since: null,
                incidents_processed: 1,
                analysis_results_created: 6,
                analysis_results_skipped: 0,
                recommendations_created: 2,
                mitre_mappings_created: 0,
                by_task_type: {},
              },
            }),
          ),
          { status: 200 },
        );
      }),
    );
    const user = userEvent.setup();
    renderLayout(null);

    await user.click(screen.getByRole("button", { name: /run pipeline/i }));

    await screen.findByText(/2 new alert\(s\), 1 incident update\(s\)/i);
  });

  it("shows the job's error message when the background job fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        if (init?.method === "POST") {
          return new Response(JSON.stringify(pendingJob("triage_reanalyze")), { status: 202 });
        }
        return new Response(
          JSON.stringify({
            ...pendingJob("triage_reanalyze"),
            status: "failed",
            error: "Ollama unreachable",
            completed_at: "2026-01-01T00:00:05Z",
          }),
          { status: 200 },
        );
      }),
    );
    const user = userEvent.setup();
    renderLayout(null);

    await user.click(screen.getByRole("button", { name: /^reanalyze$/i }));

    await screen.findByText(/ollama unreachable/i);
  });
});

describe("Layout — current user / logout", () => {
  it("shows nothing user-related when auth is disabled", () => {
    renderLayout(null);
    expect(screen.queryByText(/log out/i)).not.toBeInTheDocument();
  });

  it("shows the username, role, and a working logout control when signed in", async () => {
    const logout = vi.fn();
    const user = userEvent.setup();
    renderLayout({ username: "analyst1", role: "analyst" }, logout);

    expect(screen.getByText("analyst1")).toBeInTheDocument();
    expect(screen.getByText("(analyst)")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /log out/i }));
    expect(logout).toHaveBeenCalledOnce();
  });
});
