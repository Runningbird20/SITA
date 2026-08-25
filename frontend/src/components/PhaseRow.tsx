import type { Phase, PhaseStatusValue } from "../data/phases";
import { StatusDot } from "./StatusDot";
import "./PhaseRow.css";

interface PhaseRowProps {
  phase: Phase;
  status: PhaseStatusValue;
}

export function PhaseRow({ phase, status }: PhaseRowProps) {
  return (
    <li className="phase-row" data-status={status}>
      <span className="phase-row-id">{String(phase.id).padStart(2, "0")}</span>
      <div className="phase-row-body">
        <span className="phase-row-title">{phase.title}</span>
        <span className="phase-row-goal">{phase.goal}</span>
      </div>
      <StatusDot status={status} />
    </li>
  );
}
