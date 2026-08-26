import { ErrorState, LoadingState } from "../components/ui/QueryState";
import { useApiQuery } from "../hooks/useApiQuery";
import { fetchMitreTechniques } from "../api/resources";
import { groupByTactic } from "../lib/aggregate";
import "../styles/dashboard.css";

export function MitrePage() {
  const query = useApiQuery(() => fetchMitreTechniques({ limit: 200, sort: "technique_id" }), []);

  const grouped = groupByTactic(query.data?.items ?? []);
  const tactics = Object.keys(grouped).sort();

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>MITRE ATT&amp;CK</h1>
          <p>
            The locally vendored technique library, grouped by tactic — not a live "observed in
            environment" view. See an incident's detail page for which techniques a specific
            incident actually maps to.
          </p>
        </div>
      </div>

      {query.loading && <LoadingState label="Loading techniques…" />}
      {!query.loading && query.error && (
        <ErrorState message={query.error} onRetry={query.refetch} />
      )}
      {!query.loading && !query.error && tactics.length === 0 && (
        <p style={{ color: "var(--color-text-dim)", fontSize: "0.85rem" }}>
          No techniques loaded yet — run <code>app.mitre.cli</code> from the backend.
        </p>
      )}

      {!query.loading &&
        !query.error &&
        tactics.map((tactic) => (
          <div className="tactic-group" key={tactic}>
            <h2>{tactic}</h2>
            <div className="technique-grid">
              {grouped[tactic].map((technique) => (
                <div className="technique-card" key={technique.id}>
                  <div className="technique-card-id">{technique.technique_id}</div>
                  <div className="technique-card-name">{technique.name}</div>
                  <div className="technique-card-desc">{technique.description}</div>
                </div>
              ))}
            </div>
          </div>
        ))}
    </div>
  );
}
