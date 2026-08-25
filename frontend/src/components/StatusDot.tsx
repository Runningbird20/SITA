import type { PhaseStatusValue } from "../data/phases";
import "./StatusDot.css";

const LABELS: Record<PhaseStatusValue, string> = {
  implemented: "Working",
  implemented_static: "Implemented",
  not_implemented: "Not implemented",
  broken: "Broken",
  checking: "Checking…",
};

interface StatusDotProps {
  status: PhaseStatusValue;
}

export function StatusDot({ status }: StatusDotProps) {
  return (
    <span className="status-dot-wrap" data-status={status}>
      <span className="status-dot" aria-hidden="true" />
      <span className="status-dot-label">{LABELS[status]}</span>
    </span>
  );
}
