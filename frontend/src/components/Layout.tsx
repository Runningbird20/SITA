import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { ApiError } from "../api/client";
import { reanalyze, runPipeline } from "../api/resources";
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

export function Layout() {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [reanalyzing, setReanalyzing] = useState(false);
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
    try {
      const report = await runPipeline();
      const alerts = report.detection.alerts_created;
      const incidents = report.correlation.incidents_created + report.correlation.incidents_joined;
      setResult(`Done — ${alerts} new alert(s), ${incidents} incident update(s).`);
    } catch (err) {
      setResult(err instanceof ApiError ? err.message : "Pipeline run failed.");
    } finally {
      setRunning(false);
    }
  }

  async function handleReanalyze() {
    setReanalyzing(true);
    setReanalyzeResult(null);
    try {
      const report = await reanalyze();
      setReanalyzeResult(
        `Done — ${report.analysis_results_created} AI result(s) regenerated across ${report.incidents_processed} incident(s).`,
      );
    } catch (err) {
      setReanalyzeResult(err instanceof ApiError ? err.message : "Reanalyze failed.");
    } finally {
      setReanalyzing(false);
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
              {reanalyzing ? "Reanalyzing…" : "Reanalyze"}
            </button>
          )}
          {reanalyzeResult && <p className="app-nav-result">{reanalyzeResult}</p>}
          {canRunAdminActions && (
            <button type="button" onClick={handleRunPipeline} disabled={running}>
              {running ? "Running…" : "Run pipeline"}
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
