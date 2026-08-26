import { Link, useNavigate } from "react-router-dom";
import { SeverityBadge } from "../components/ui/Badges";
import { ErrorState, LoadingState } from "../components/ui/QueryState";
import { useApiQuery } from "../hooks/useApiQuery";
import { fetchAlerts, fetchIncidents } from "../api/resources";
import { bucketByDay } from "../lib/aggregate";
import type { Severity } from "../api/types";
import "../styles/dashboard.css";

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];

export function OverviewPage() {
  const navigate = useNavigate();
  const incidents = useApiQuery(
    () => fetchIncidents({ limit: 200, sort: "-last_activity_at" }),
    [],
  );
  const alerts = useApiQuery(() => fetchAlerts({ limit: 200, sort: "-first_event_at" }), []);

  const loading = incidents.loading || alerts.loading;
  const error = incidents.error ?? alerts.error;

  const severityCounts: Record<Severity, number> = { low: 0, medium: 0, high: 0, critical: 0 };
  for (const incident of incidents.data?.items ?? []) {
    severityCounts[incident.severity] += 1;
  }

  const volume = bucketByDay((alerts.data?.items ?? []).map((a) => a.first_event_at));
  const maxVolume = Math.max(1, ...volume.map((v) => v.count));

  const recentIncidents = (incidents.data?.items ?? []).slice(0, 8);

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Overview</h1>
          <p>Current state of the environment, from the last 200 incidents/alerts.</p>
        </div>
      </div>

      {loading && <LoadingState label="Loading overview…" />}
      {!loading && error && (
        <ErrorState
          message={error}
          onRetry={() => {
            incidents.refetch();
            alerts.refetch();
          }}
        />
      )}

      {!loading && !error && (
        <>
          <div className="card-grid">
            {SEVERITIES.map((severity) => (
              <div className="stat-card" data-severity={severity} key={severity}>
                <div className="stat-card-value">{severityCounts[severity]}</div>
                <div className="stat-card-label">{severity} severity incidents</div>
              </div>
            ))}
            <div className="stat-card">
              <div className="stat-card-value">{alerts.data?.total ?? 0}</div>
              <div className="stat-card-label">total alerts</div>
            </div>
          </div>

          <div className="detail-section">
            <h2>Alert volume</h2>
            {volume.length === 0 ? (
              <p style={{ color: "var(--color-text-dim)", fontSize: "0.85rem" }}>No alerts yet.</p>
            ) : (
              <div style={{ display: "flex", alignItems: "flex-end", gap: "4px", height: "80px" }}>
                {volume.map((v) => (
                  <div
                    key={v.day}
                    title={`${v.day}: ${v.count}`}
                    style={{
                      flex: 1,
                      background: "var(--color-severity-medium)",
                      opacity: 0.75,
                      height: `${(v.count / maxVolume) * 100}%`,
                      minHeight: "3px",
                      borderRadius: "2px 2px 0 0",
                    }}
                  />
                ))}
              </div>
            )}
          </div>

          <div className="detail-section">
            <h2>Recent incidents</h2>
            {recentIncidents.length === 0 ? (
              <p style={{ color: "var(--color-text-dim)", fontSize: "0.85rem" }}>
                No incidents yet — try running the pipeline from the nav.
              </p>
            ) : (
              <div className="panel">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Title</th>
                      <th>Severity</th>
                      <th>Status</th>
                      <th>Alerts</th>
                      <th>Last activity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentIncidents.map((incident) => (
                      <tr
                        key={incident.id}
                        data-clickable
                        onClick={() => navigate(`/incidents/${incident.id}`)}
                      >
                        <td>
                          <Link
                            to={`/incidents/${incident.id}`}
                            onClick={(e) => e.stopPropagation()}
                          >
                            {incident.title}
                          </Link>
                        </td>
                        <td>
                          <SeverityBadge severity={incident.severity} />
                        </td>
                        <td>{incident.status}</td>
                        <td>{incident.alert_count}</td>
                        <td className="mono">
                          {new Date(incident.last_activity_at).toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
