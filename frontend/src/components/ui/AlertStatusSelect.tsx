import { useState } from "react";
import { setAlertStatus } from "../../api/resources";
import type { AlertStatus } from "../../api/types";

const OPTIONS: AlertStatus[] = ["new", "investigating", "resolved", "false_positive"];

/** Inline status editor for one alert. Marking an alert `false_positive`
 * here is the real feedback source for rule-tuning suggestions (see
 * DEF.md § Phase 7, "Post-roadmap addition: rule tuning suggestions from
 * analyst feedback") — this is the only place that feedback loop starts.
 * Optimistic update with rollback on failure, mirroring FeedbackButtons.
 */
export function AlertStatusSelect({ alertId, status }: { alertId: string; status: AlertStatus }) {
  const [value, setValue] = useState(status);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(false);

  async function change(next: AlertStatus) {
    if (pending || next === value) return;
    const previous = value;
    setError(false);
    setPending(true);
    setValue(next);
    try {
      await setAlertStatus(alertId, next);
    } catch {
      setValue(previous);
      setError(true);
    } finally {
      setPending(false);
    }
  }

  return (
    <span>
      <select
        value={value}
        disabled={pending}
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => void change(e.target.value as AlertStatus)}
        aria-label="Alert status"
      >
        {OPTIONS.map((option) => (
          <option key={option} value={option}>
            {option.replace("_", " ")}
          </option>
        ))}
      </select>
      {error && (
        <span style={{ color: "var(--color-red)", fontSize: "0.75rem", marginLeft: "0.4rem" }}>
          couldn't save
        </span>
      )}
    </span>
  );
}
