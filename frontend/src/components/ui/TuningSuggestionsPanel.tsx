import { useState } from "react";
import { updateDetectionConfig } from "../../api/resources";
import type { Detection, TuningSuggestion } from "../../api/types";
import { LoadingState } from "./QueryState";

/** Deterministic, LLM-free suggestions computed from analyst
 * false-positive feedback (marking alerts false_positive on AlertsPage) —
 * see DEF.md § Phase 7, "Post-roadmap addition: rule tuning suggestions
 * from analyst feedback". Advisory only: nothing here changes a
 * Detection's config until an analyst explicitly clicks Apply.
 */
export function TuningSuggestionsPanel({
  suggestions,
  loading,
  detectionsByRuleKey,
  onApplied,
}: {
  suggestions: TuningSuggestion[];
  loading: boolean;
  detectionsByRuleKey: Map<string, Detection>;
  onApplied: () => void;
}) {
  const [pendingRuleKey, setPendingRuleKey] = useState<string | null>(null);
  const [errorRuleKey, setErrorRuleKey] = useState<string | null>(null);

  async function apply(suggestion: TuningSuggestion) {
    const detection = detectionsByRuleKey.get(suggestion.rule_key);
    if (!detection || pendingRuleKey) return;
    setErrorRuleKey(null);
    setPendingRuleKey(suggestion.rule_key);
    try {
      await updateDetectionConfig(detection.id, {
        [suggestion.threshold_key]: suggestion.suggested_threshold_value,
      });
      onApplied();
    } catch {
      setErrorRuleKey(suggestion.rule_key);
    } finally {
      setPendingRuleKey(null);
    }
  }

  if (loading) return <LoadingState label="Checking for tuning suggestions…" />;
  if (suggestions.length === 0) return null;

  return (
    <div className="panel" style={{ marginBottom: "1rem", padding: "0.9rem 1.1rem" }}>
      <div style={{ fontWeight: 600, marginBottom: "0.6rem" }}>
        Tuning suggestions from analyst feedback
      </div>
      {suggestions.map((s) => (
        <div
          key={s.rule_key}
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: "1rem",
            padding: "0.5rem 0",
            borderTop: "1px solid var(--color-border)",
          }}
        >
          <div style={{ fontSize: "0.85rem" }}>
            <strong>{s.rule_name}</strong> — {s.rationale}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexShrink: 0 }}>
            {errorRuleKey === s.rule_key && (
              <span style={{ color: "var(--color-red)", fontSize: "0.75rem" }}>couldn't save</span>
            )}
            <button
              type="button"
              disabled={pendingRuleKey === s.rule_key}
              onClick={() => void apply(s)}
            >
              {pendingRuleKey === s.rule_key ? "Applying…" : "Apply"}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
