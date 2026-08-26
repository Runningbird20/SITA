import { useMemo } from "react";
import { API_BASE_URL } from "../api/client";
import { PhaseRow } from "../components/PhaseRow";
import { StatusDot } from "../components/StatusDot";
import { PHASES, type PhaseStatusValue } from "../data/phases";
import { useBackendStatus } from "../hooks/useBackendStatus";
import "./StatusPage.css";

function formatTime(date: Date | null): string {
  if (!date) return "never";
  return date.toLocaleTimeString([], { hour12: false });
}

export function StatusPage() {
  const backendStatus = useBackendStatus();

  const evaluated = useMemo(
    () => PHASES.map((phase) => ({ phase, status: phase.evaluate(backendStatus) })),
    [backendStatus],
  );

  const counts = useMemo(() => {
    const initial: Record<PhaseStatusValue, number> = {
      implemented: 0,
      implemented_static: 0,
      not_implemented: 0,
      broken: 0,
      checking: 0,
    };
    for (const { status } of evaluated) initial[status] += 1;
    return initial;
  }, [evaluated]);

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <div>
          <h1>SITA</h1>
          <p className="dashboard-subtitle">Local Security Incident Triage Agent — Build Status</p>
        </div>
        <div className="backend-status">
          <StatusDot
            status={
              backendStatus.loading
                ? "checking"
                : backendStatus.reachable
                  ? "implemented"
                  : "broken"
            }
          />
          <div className="backend-status-detail">
            <span>{API_BASE_URL}</span>
            <span>
              checked {formatTime(backendStatus.checkedAt)}
              {backendStatus.error ? ` — ${backendStatus.error}` : ""}
            </span>
          </div>
          <button type="button" onClick={backendStatus.refresh} disabled={backendStatus.loading}>
            Refresh
          </button>
        </div>
      </header>

      <section className="summary-bar">
        <span className="summary-item" data-status="implemented">
          {counts.implemented} working
        </span>
        <span className="summary-item" data-status="implemented_static">
          {counts.implemented_static} implemented
        </span>
        <span className="summary-item" data-status="broken">
          {counts.broken} broken
        </span>
        <span className="summary-item" data-status="not_implemented">
          {counts.not_implemented} not implemented
        </span>
      </section>

      <ul className="phase-list">
        {evaluated.map(({ phase, status }) => (
          <PhaseRow key={phase.id} phase={phase} status={status} />
        ))}
      </ul>

      <footer className="dashboard-footer">
        <p>
          Phases 0, 1, 2, 3, 4, 5, 7, 8, and 9 are checked live against the running backend (
          <code>/healthz</code>, <code>/openapi.json</code>) — green means "Working," verified just
          now. Phases 6 and 10 have no REST resource of their own to check (the LLM provider
          abstraction and this dashboard itself aren't domain objects Phase 9 exposes) — yellow
          "Implemented" is asserted from each one's own test suite and report, not guessed. Red
          means a live check ran and failed. Phases 11–15 have no built surface at all yet, shown
          gray rather than guessed at. This page is now a standing diagnostic — the real product
          lives behind the nav.
        </p>
      </footer>
    </div>
  );
}
