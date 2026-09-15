import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import type { PipelineJob, PipelineRunReport, TriageRunReport } from "../api/types";
import { ApiError } from "../api/client";
import { fetchPipelineJob, reanalyze, runPipeline } from "../api/resources";
import { useAuth } from "./AuthContext";
import "./Layout.css";

const NAV_ITEMS = [
  { to: "/", label: "Overview", end: true },
  { to: "/incidents", label: "Incidents" },
  { to: "/alerts", label: "Alerts" },
  { to: "/iocs", label: "IOCs" },
  { to: "/detections", label: "Detections" },
  { to: "/mitre", label: "MITRE ATT&CK" },
];

const POLL_INTERVAL_MS = 1500;

/** Polls GET /pipeline/jobs/{id} until the job leaves pending/running —
 * both trigger buttons below share this rather than blocking on the
 * original synchronous response, which real Ollama calls could hold for
 * minutes (Phase 15 measured ~5.5 minutes for a 10-incident run). See
 * DEF.md § Phase 9, "Post-roadmap addition: background pipeline jobs".
 */
async function pollUntilDone(
  jobId: string,
  onUpdate: (job: PipelineJob) => void,
): Promise<PipelineJob> {
  for (;;) {
    const job = await fetchPipelineJob(jobId);
    onUpdate(job);
    if (job.status === "completed" || job.status === "failed") {
      return job;
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }
}

function progressLabel(job: PipelineJob | null, fallback: string): string {
  if (!job || job.status === "pending") return "Starting…";
  if (job.status !== "running") return fallback;
  if (job.progress_current != null && job.progress_total != null) {
    return `${job.current_stage ?? "running"} (${job.progress_current}/${job.progress_total})…`;
  }
  return job.current_stage ? `${job.current_stage}…` : fallback;
}

export function Layout() {
  const [running, setRunning] = useState(false);
  const [runningJob, setRunningJob] = useState<PipelineJob | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [reanalyzing, setReanalyzing] = useState(false);
  const [reanalyzeJob, setReanalyzeJob] = useState<PipelineJob | null>(null);
  const [reanalyzeResult, setReanalyzeResult] = useState<string | null>(null);
  const { user, logout } = useAuth();
  // null user means either "auth disabled" or "not logged in" — AuthGate
  // never renders Layout in the latter case, so within here null always
  // means disabled, and both admin-only actions (like every other route)
  // stay unrestricted, matching the backend's own require_admin behavior
  // (see app/auth/deps.py).
  const canRunAdminActions = user === null || user.role === "admin";

  async function handleRunPipeline() {
    setRunning(true);
    setResult(null);
    setRunningJob(null);
    try {
      const initial = await runPipeline();
      const job = await pollUntilDone(initial.id, setRunningJob);
      if (job.status === "failed") {
        setResult(job.error ?? "Pipeline run failed.");
      } else {
        const report = job.result as PipelineRunReport;
        const alerts = report.detection.alerts_created;
        const incidents =
          report.correlation.incidents_created + report.correlation.incidents_joined;
        setResult(`Done — ${alerts} new alert(s), ${incidents} incident update(s).`);
      }
    } catch (err) {
      setResult(err instanceof ApiError ? err.message : "Pipeline run failed.");
    } finally {
      setRunning(false);
      setRunningJob(null);
    }
  }

  async function handleReanalyze() {
    setReanalyzing(true);
    setReanalyzeResult(null);
    setReanalyzeJob(null);
    try {
      const initial = await reanalyze();
      const job = await pollUntilDone(initial.id, setReanalyzeJob);
      if (job.status === "failed") {
        setReanalyzeResult(job.error ?? "Reanalyze failed.");
      } else {
        const report = job.result as TriageRunReport;
        setReanalyzeResult(
          `Done — ${report.analysis_results_created} AI result(s) regenerated across ${report.incidents_processed} incident(s).`,
        );
      }
    } catch (err) {
      setReanalyzeResult(err instanceof ApiError ? err.message : "Reanalyze failed.");
    } finally {
      setReanalyzing(false);
      setReanalyzeJob(null);
    }
  }

  return (
    <div className="app-shell">
      <aside className="app-nav">
        <div className="app-nav-brand">
          <span className="app-nav-title">SITA</span>
          <span className="app-nav-subtitle">Incident Triage</span>
        </div>
        <nav>
          <ul>
            {NAV_ITEMS.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} end={item.end}>
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="app-nav-footer">
          {canRunAdminActions && (
            <button
              type="button"
              onClick={handleReanalyze}
              disabled={reanalyzing}
              title="Force-regenerate AI analysis for every incident, even ones that already have a result"
            >
              {reanalyzing ? progressLabel(reanalyzeJob, "Reanalyzing…") : "Reanalyze"}
            </button>
          )}
          {reanalyzeResult && <p className="app-nav-result">{reanalyzeResult}</p>}
          {canRunAdminActions && (
            <button type="button" onClick={handleRunPipeline} disabled={running}>
              {running ? progressLabel(runningJob, "Running…") : "Run pipeline"}
            </button>
          )}
          {result && <p className="app-nav-result">{result}</p>}
          {user && (
            <div className="app-nav-user">
              <span>
                {user.username} <span className="app-nav-user-role">({user.role})</span>
              </span>
              <button type="button" className="app-nav-logout" onClick={logout}>
                Log out
              </button>
            </div>
          )}
          <NavLink to="/status" className="app-nav-status-link">
            Build status →
          </NavLink>
        </div>
      </aside>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
