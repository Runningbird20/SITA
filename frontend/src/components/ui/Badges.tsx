import type { ReactNode } from "react";
import type { Severity } from "../../api/types";
import "./Badges.css";

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className="severity-badge" data-severity={severity}>
      {severity}
    </span>
  );
}

/** A plain neutral pill for status/category/priority values that don't
 * carry severity's color semantics — just a consistent label shape.
 */
export function Pill({ children }: { children: ReactNode }) {
  return <span className="pill">{children}</span>;
}

/** The one consistent marker for AI-generated content, wherever it
 * appears — badge only; pair with .ai-panel/.ai-border for the fuller
 * treatment. See DEF.md § Phase 10.
 */
export function AiBadge() {
  return <span className="ai-badge">AI-generated</span>;
}
