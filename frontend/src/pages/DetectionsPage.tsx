import { useState } from "react";
import { Pill, SeverityBadge } from "../components/ui/Badges";
import { ErrorState, LoadingState } from "../components/ui/QueryState";
import { useApiQuery } from "../hooks/useApiQuery";
import { fetchAlerts, fetchDetections } from "../api/resources";
import type { Detection } from "../api/types";
import "../styles/dashboard.css";

function RecentFirings({ detection }: { detection: Detection }) {
  const query = useApiQuery(
    () => fetchAlerts({ ruleKey: detection.rule_key, limit: 5, sort: "-first_event_at" }),
    [detection.rule_key],
  );

  if (query.loading) return <LoadingState label="Loading recent firings…" />;
  if (query.error) return <ErrorState message={query.error} onRetry={query.refetch} />;
  if (!query.data || query.data.items.length === 0) {
    return (
      <p style={{ color: "var(--color-text-dim)", fontSize: "0.85rem", padding: "0.75rem 0.9rem" }}>
        No alerts have fired for this rule yet.
      </p>
    );
  }

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Severity</th>
          <th>Rationale</th>
          <th>First seen</th>
        </tr>
      </thead>
      <tbody>
        {query.data.items.map((alert) => (
          <tr key={alert.id}>
            <td>
              <SeverityBadge severity={alert.severity} />
            </td>
            <td>{alert.rationale}</td>
            <td className="mono">{new Date(alert.first_event_at).toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function DetectionsPage() {
  const [expanded, setExpanded] = useState<string | null>(null);
  const query = useApiQuery(() => fetchDetections({ limit: 100, sort: "name" }), []);

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Detections</h1>
          <p>Deterministic rule definitions. Click a rule to see its recent firings.</p>
        </div>
      </div>

      {query.loading && <LoadingState label="Loading detections…" />}
      {!query.loading && query.error && (
        <ErrorState message={query.error} onRetry={query.refetch} />
      )}

      {!query.loading &&
        !query.error &&
        query.data?.items.map((detection) => (
          <div className="panel" key={detection.id} style={{ marginBottom: "0.85rem" }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: "1rem",
                padding: "0.9rem 1.1rem",
                cursor: "pointer",
              }}
              onClick={() =>
                setExpanded((current) => (current === detection.id ? null : detection.id))
              }
            >
              <div>
                <div style={{ fontWeight: 600 }}>{detection.name}</div>
                <div
                  style={{
                    fontSize: "0.82rem",
                    color: "var(--color-text-dim)",
                    marginTop: "0.2rem",
                  }}
                >
                  {detection.description}
                </div>
              </div>
              <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexShrink: 0 }}>
                <Pill>{detection.category}</Pill>
                <SeverityBadge severity={detection.default_severity} />
                <Pill>{detection.enabled ? "enabled" : "disabled"}</Pill>
              </div>
            </div>
            {expanded === detection.id && (
              <div style={{ borderTop: "1px solid var(--color-border)" }}>
                <RecentFirings detection={detection} />
              </div>
            )}
          </div>
        ))}
    </div>
  );
}
