import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { SeverityBadge } from "../components/ui/Badges";
import { Pagination } from "../components/ui/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/QueryState";
import { useApiQuery } from "../hooks/useApiQuery";
import { fetchIncidents } from "../api/resources";
import type { IncidentStatus, Severity } from "../api/types";
import "../styles/dashboard.css";

const LIMIT = 25;

const SORT_COLUMNS: { key: string; label: string }[] = [
  { key: "last_activity_at", label: "Last activity" },
  { key: "first_activity_at", label: "First activity" },
  { key: "created_at", label: "Created" },
];

export function IncidentsPage() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<IncidentStatus | "">("");
  const [severity, setSeverity] = useState<Severity | "">("");
  const [sort, setSort] = useState("-last_activity_at");
  const [offset, setOffset] = useState(0);

  const query = useApiQuery(
    () =>
      fetchIncidents({
        limit: LIMIT,
        offset,
        sort,
        status: status || undefined,
        severity: severity || undefined,
      }),
    [status, severity, sort, offset],
  );

  function toggleSort(key: string) {
    setOffset(0);
    setSort((current) => (current === key ? `-${key}` : key));
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Incidents</h1>
          <p>Correlated groups of alerts representing one security narrative.</p>
        </div>
      </div>

      <div className="filter-bar">
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as IncidentStatus | "");
            setOffset(0);
          }}
        >
          <option value="">All statuses</option>
          <option value="open">Open</option>
          <option value="investigating">Investigating</option>
          <option value="contained">Contained</option>
          <option value="closed">Closed</option>
        </select>
        <select
          value={severity}
          onChange={(e) => {
            setSeverity(e.target.value as Severity | "");
            setOffset(0);
          }}
        >
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      {query.loading && <LoadingState label="Loading incidents…" />}
      {!query.loading && query.error && (
        <ErrorState message={query.error} onRetry={query.refetch} />
      )}
      {!query.loading && !query.error && query.data && query.data.items.length === 0 && (
        <EmptyState message="No incidents match these filters." />
      )}
      {!query.loading && !query.error && query.data && query.data.items.length > 0 && (
        <div className="panel">
          <table className="data-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Alerts</th>
                {SORT_COLUMNS.map((col) => (
                  <th key={col.key} data-sortable onClick={() => toggleSort(col.key)}>
                    {col.label}
                    {sort.replace("-", "") === col.key ? (sort.startsWith("-") ? " ↓" : " ↑") : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {query.data.items.map((incident) => (
                <tr
                  key={incident.id}
                  data-clickable
                  onClick={() => navigate(`/incidents/${incident.id}`)}
                >
                  <td>{incident.title}</td>
                  <td>
                    <SeverityBadge severity={incident.severity} />
                  </td>
                  <td>{incident.status}</td>
                  <td>{incident.alert_count}</td>
                  <td className="mono">{new Date(incident.last_activity_at).toLocaleString()}</td>
                  <td className="mono">{new Date(incident.first_activity_at).toLocaleString()}</td>
                  <td className="mono">{new Date(incident.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pagination
            total={query.data.total}
            limit={LIMIT}
            offset={offset}
            onOffsetChange={setOffset}
          />
        </div>
      )}
    </div>
  );
}
