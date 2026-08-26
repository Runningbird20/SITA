import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { ApiError } from "../api/client";
import { runPipeline } from "../api/resources";
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
          <button type="button" onClick={handleRunPipeline} disabled={running}>
            {running ? "Running…" : "Run pipeline"}
          </button>
          {result && <p className="app-nav-result">{result}</p>}
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
