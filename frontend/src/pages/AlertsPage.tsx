import { useState } from "react";
import { Link } from "react-router-dom";
import { SeverityBadge } from "../components/ui/Badges";
import { Pagination } from "../components/ui/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/QueryState";
import { useApiQuery } from "../hooks/useApiQuery";
import { fetchAlerts, fetchDetections } from "../api/resources";
import type { AlertStatus, Severity } from "../api/types";
import "../styles/dashboard.css";

const LIMIT = 25;

const SORT_COLUMNS: { key: string; label: string }[] = [
  { key: "first_event_at", label: "First seen" },
  { key: "last_event_at", label: "Last seen" },
  { key: "confidence", label: "Confidence" },
  { key: "created_at", label: "Created" },
];

export function AlertsPage() {
  const [severity, setSeverity] = useState<Severity | "">("");
  const [status, setStatus] = useState<AlertStatus | "">("");
  const [ruleKey, setRuleKey] = useState("");
  const [sort, setSort] = useState("-first_event_at");
  const [offset, setOffset] = useState(0);

  const detections = useApiQuery(() => fetchDetections({ limit: 200, sort: "name" }), []);
  const ruleNameById = new Map((detections.data?.items ?? []).map((d) => [d.id, d.name]));

  const query = useApiQuery(
    () =>
      fetchAlerts({
        limit: LIMIT,
        offset,
        sort,
        severity: severity || undefined,
        status: status || undefined,
        ruleKey: ruleKey || undefined,
      }),
    [severity, status, ruleKey, sort, offset],
  );

  function toggleSort(key: string) {
    setOffset(0);
    setSort((current) => (current === key ? `-${key}` : key));
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Alerts</h1>
          <p>Deterministic detection-rule firings.</p>
        </div>
      </div>

      <div className="filter-bar">
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
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as AlertStatus | "");
            setOffset(0);
          }}
        >
          <option value="">All statuses</option>
          <option value="new">New</option>
          <option value="investigating">Investigating</option>
          <option value="resolved">Resolved</option>
          <option value="false_positive">False positive</option>
        </select>
        <select
          value={ruleKey}
          onChange={(e) => {
            setRuleKey(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">All rules</option>
          {(detections.data?.items ?? []).map((d) => (
            <option key={d.rule_key} value={d.rule_key}>
              {d.name}
            </option>
          ))}
        </select>
      </div>

      {query.loading && <LoadingState label="Loading alerts…" />}
      {!query.loading && query.error && (
        <ErrorState message={query.error} onRetry={query.refetch} />
      )}
      {!query.loading && !query.error && query.data && query.data.items.length === 0 && (
        <EmptyState message="No alerts match these filters." />
      )}
      {!query.loading && !query.error && query.data && query.data.items.length > 0 && (
        <div className="panel">
          <table className="data-table">
            <thead>
              <tr>
                <th>Severity</th>
                <th>Rule</th>
                <th>Status</th>
                <th>Incident</th>
                {SORT_COLUMNS.map((col) => (
                  <th key={col.key} data-sortable onClick={() => toggleSort(col.key)}>
                    {col.label}
                    {sort.replace("-", "") === col.key ? (sort.startsWith("-") ? " ↓" : " ↑") : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {query.data.items.map((alert) => (
                <tr key={alert.id} title={alert.rationale}>
                  <td>
                    <SeverityBadge severity={alert.severity} />
                  </td>
                  <td className="mono">
                    {ruleNameById.get(alert.detection_id) ?? alert.detection_id}
                  </td>
                  <td>{alert.status}</td>
                  <td>
                    {alert.incident_id ? (
                      <Link to={`/incidents/${alert.incident_id}`}>view</Link>
                    ) : (
                      <span style={{ color: "var(--color-text-dim)" }}>—</span>
                    )}
                  </td>
                  <td className="mono">{new Date(alert.first_event_at).toLocaleString()}</td>
                  <td className="mono">{new Date(alert.last_event_at).toLocaleString()}</td>
                  <td className="mono">{alert.confidence.toFixed(2)}</td>
                  <td className="mono">{new Date(alert.created_at).toLocaleString()}</td>
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
