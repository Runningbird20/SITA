import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { AiBadge, Pill, SeverityBadge } from "../components/ui/Badges";
import { ErrorState, LoadingState } from "../components/ui/QueryState";
import { useApiQuery } from "../hooks/useApiQuery";
import { fetchIncident } from "../api/resources";
import type { AnalysisResult, IncidentTechniqueEntry } from "../api/types";
import "../styles/dashboard.css";

const TASK_TITLES: Record<AnalysisResult["task_type"], string> = {
  incident_summary: "Summary",
  severity_explanation: "Severity explanation",
  attack_classification: "Attack classification",
  investigation_hypothesis: "Investigation hypotheses",
  investigation_steps: "Suggested investigation steps",
  mitre_suggestion: "MITRE technique suggestions",
};

function renderAnalysisBody(result: AnalysisResult): ReactNode {
  if (result.validation_status !== "valid" || !result.parsed_output) {
    return (
      <p style={{ color: "var(--color-text-dim)" }}>
        This analysis did not validate ({result.validation_status}) — no structured output to show.
      </p>
    );
  }

  const output = result.parsed_output;
  switch (result.task_type) {
    case "incident_summary":
      return (
        <div>
          <p>{String(output.summary ?? "")}</p>
          {Array.isArray(output.key_points) && (
            <ul>
              {(output.key_points as string[]).map((point, i) => (
                <li key={i}>{point}</li>
              ))}
            </ul>
          )}
        </div>
      );
    case "severity_explanation":
      return <p>{String(output.explanation ?? "")}</p>;
    case "attack_classification":
      return (
        <p>
          <strong>{String(output.category ?? "")}</strong> — {String(output.kill_chain_stage ?? "")}
          <br />
          {String(output.rationale ?? "")}
        </p>
      );
    case "investigation_hypothesis":
      return Array.isArray(output.hypotheses) ? (
        <ul>
          {(output.hypotheses as string[]).map((h, i) => (
            <li key={i}>{h}</li>
          ))}
        </ul>
      ) : null;
    case "investigation_steps":
      return Array.isArray(output.steps) ? (
        <ul>
          {(output.steps as { text: string; priority: string }[]).map((step, i) => (
            <li key={i}>
              <Pill>{step.priority}</Pill> {step.text}
            </li>
          ))}
        </ul>
      ) : null;
    case "mitre_suggestion":
      return Array.isArray(output.techniques) ? (
        <ul>
          {(
            output.techniques as {
              technique_id: string;
              technique_name: string;
              rationale: string;
            }[]
          ).map((t, i) => (
            <li key={i}>
              <span className="mono">{t.technique_id}</span> — {t.technique_name}: {t.rationale}
            </li>
          ))}
        </ul>
      ) : null;
    default:
      return null;
  }
}

function MitreTechniquesList({ entries }: { entries: IncidentTechniqueEntry[] }) {
  if (entries.length === 0) {
    return (
      <p style={{ color: "var(--color-text-dim)", fontSize: "0.85rem" }}>
        No MITRE techniques mapped yet.
      </p>
    );
  }
  return (
    <div className="technique-grid">
      {entries.map((entry) => (
        <div className="technique-card" key={entry.technique_id}>
          <div className="technique-card-id">{entry.technique_id}</div>
          <div className="technique-card-name">{entry.name}</div>
          <div
            style={{ fontSize: "0.78rem", color: "var(--color-text-dim)", marginBottom: "0.4rem" }}
          >
            {entry.tactic}
          </div>
          <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
            {entry.sources.includes("rule") && <Pill>rule</Pill>}
            {entry.sources.includes("llm") && <AiBadge />}
          </div>
        </div>
      ))}
    </div>
  );
}

export function IncidentDetailPage() {
  const { incidentId } = useParams<{ incidentId: string }>();
  const query = useApiQuery(() => fetchIncident(incidentId!), [incidentId]);

  if (query.loading) return <LoadingState label="Loading incident…" />;
  if (query.error) return <ErrorState message={query.error} onRetry={query.refetch} />;
  if (!query.data) return null;

  const incident = query.data;
  const timeline = [...incident.alerts].sort(
    (a, b) => new Date(a.first_event_at).getTime() - new Date(b.first_event_at).getTime(),
  );

  return (
    <div>
      <Link to="/incidents" className="detail-back-link">
        ← All incidents
      </Link>

      <div className="page-header">
        <div>
          <h1>{incident.title}</h1>
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem" }}>
            <SeverityBadge severity={incident.severity} />
            <Pill>{incident.status}</Pill>
          </div>
        </div>
      </div>

      <div className="detail-meta-row">
        <span>
          <strong>{incident.alert_count}</strong> alerts
        </span>
        <span>
          <strong>{incident.iocs.length}</strong> IOCs
        </span>
        <span>
          <strong>{incident.entities.length}</strong> entities
        </span>
        <span>
          First activity: <strong>{new Date(incident.first_activity_at).toLocaleString()}</strong>
        </span>
        <span>
          Last activity: <strong>{new Date(incident.last_activity_at).toLocaleString()}</strong>
        </span>
      </div>

      <div className="detail-section">
        <h2>AI analysis</h2>
        {incident.analysis_results.length === 0 ? (
          <p style={{ color: "var(--color-text-dim)", fontSize: "0.85rem" }}>
            No AI analysis yet — run the pipeline from the nav to generate one.
          </p>
        ) : (
          incident.analysis_results.map((result) => (
            <div className="ai-panel" key={result.id}>
              <div className="ai-panel-header">
                <span className="ai-panel-title">{TASK_TITLES[result.task_type]}</span>
                <AiBadge />
              </div>
              <div className="ai-panel-body">{renderAnalysisBody(result)}</div>
              <div className="ai-panel-meta" style={{ marginTop: "0.5rem" }}>
                {result.provider}/{result.model} · prompt {result.prompt_version} ·{" "}
                {result.confidence !== null
                  ? `confidence ${result.confidence.toFixed(2)}`
                  : "no confidence"}{" "}
                · {result.latency_ms}ms
              </div>
            </div>
          ))
        )}
      </div>

      <div className="detail-section">
        <h2>Recommendations</h2>
        {incident.recommendations.length === 0 ? (
          <p style={{ color: "var(--color-text-dim)", fontSize: "0.85rem" }}>
            No recommendations yet.
          </p>
        ) : (
          <ul className="entity-list">
            {incident.recommendations.map((rec) => (
              <li key={rec.id}>
                <span>
                  <Pill>{rec.priority}</Pill> <Pill>{rec.status}</Pill> {rec.text}
                </span>
                {rec.source === "llm" && <AiBadge />}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="detail-section">
        <h2>MITRE ATT&amp;CK techniques</h2>
        <MitreTechniquesList entries={incident.mitre_techniques} />
      </div>

      <div className="detail-section">
        <h2>Timeline</h2>
        <div className="panel">
          <table className="data-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Severity</th>
                <th>Rationale</th>
              </tr>
            </thead>
            <tbody>
              {timeline.map((alert) => (
                <tr key={alert.id}>
                  <td className="mono">{new Date(alert.first_event_at).toLocaleString()}</td>
                  <td>
                    <SeverityBadge severity={alert.severity} />
                  </td>
                  <td>{alert.rationale}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="detail-section">
        <h2>IOCs</h2>
        {incident.iocs.length === 0 ? (
          <p style={{ color: "var(--color-text-dim)", fontSize: "0.85rem" }}>
            No IOCs extracted yet.
          </p>
        ) : (
          <ul className="ioc-list">
            {incident.iocs.map((ioc) => (
              <li key={ioc.id}>
                <span className="mono">{ioc.value}</span>
                <span style={{ color: "var(--color-text-dim)" }}>{ioc.ioc_type}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="detail-section">
        <h2>Entities</h2>
        {incident.entities.length === 0 ? (
          <p style={{ color: "var(--color-text-dim)", fontSize: "0.85rem" }}>
            No entities linked yet.
          </p>
        ) : (
          <ul className="entity-list">
            {incident.entities.map((entity) => (
              <li key={entity.id}>
                <span className="mono">{entity.identifier}</span>
                <span style={{ color: "var(--color-text-dim)" }}>{entity.entity_type}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
