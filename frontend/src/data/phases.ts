import type { BackendStatus } from "../hooks/useBackendStatus";

export type PhaseStatusValue = "implemented" | "not_implemented" | "broken" | "checking";

export interface Phase {
  id: number;
  title: string;
  goal: string;
  /** How this phase's live status is determined. Phases with no backend
   * surface yet (nothing has been built) are statically "not_implemented" —
   * there's nothing to check. Phases with real endpoints are evaluated
   * against live backend responses, never hardcoded to "implemented".
   */
  evaluate: (status: BackendStatus) => PhaseStatusValue;
}

/** Wraps a live check with the shared "loading / unreachable" handling so
 * each phase only has to state what "working" means for it.
 */
function liveCheck(isWorking: (status: BackendStatus) => boolean): Phase["evaluate"] {
  return (status) => {
    if (status.loading) return "checking";
    if (!status.reachable) return "broken";
    return isWorking(status) ? "implemented" : "broken";
  };
}

const notImplemented: Phase["evaluate"] = () => "not_implemented";

export const PHASES: Phase[] = [
  {
    id: 0,
    title: "Project Foundation",
    goal: "A cloneable, runnable skeleton with dev tooling, containers, and CI in place before any feature logic is written.",
    evaluate: liveCheck(() => true),
  },
  {
    id: 1,
    title: "Core Data Model",
    goal: "Stable, well-typed schemas that every later phase builds on.",
    evaluate: liveCheck((status) => status.healthz?.database === "ok"),
  },
  {
    id: 2,
    title: "Event Ingestion",
    goal: "Accept simulated security events from multiple source types and normalize them into the common schema.",
    evaluate: liveCheck(
      (status) =>
        status.healthz?.database === "ok" &&
        (status.openApiPaths?.has("/api/v1/events/{source_type}") ?? false),
    ),
  },
  {
    id: 3,
    title: "Detection Engine",
    goal: "Deterministic, explainable rules that turn normalized events into structured alerts.",
    evaluate: notImplemented,
  },
  {
    id: 4,
    title: "IOC Extraction",
    goal: "Pull structured indicators out of events/alerts, validated deterministically.",
    evaluate: notImplemented,
  },
  {
    id: 5,
    title: "Incident Correlation",
    goal: "Group related alerts into incidents using explainable, deterministic correlation logic.",
    evaluate: notImplemented,
  },
  {
    id: 6,
    title: "Local LLM Integration",
    goal: "A clean provider abstraction so the AI layer is swappable and never a single point of failure.",
    evaluate: notImplemented,
  },
  {
    id: 7,
    title: "AI-Powered Triage",
    goal: "LLM-assisted reasoning, always clearly labeled and layered on top of — never replacing — deterministic output.",
    evaluate: notImplemented,
  },
  {
    id: 8,
    title: "MITRE ATT&CK Integration",
    goal: "Ground the system in a recognized security framework using local data.",
    evaluate: notImplemented,
  },
  {
    id: 9,
    title: "REST API",
    goal: "A well-documented, consistent API surface over every domain object.",
    evaluate: notImplemented,
  },
  {
    id: 10,
    title: "Frontend",
    goal: "A dense, usable SOC-style dashboard — the primary visual artifact for demos and interviews.",
    evaluate: notImplemented,
  },
  {
    id: 11,
    title: "Testing",
    goal: "Confidence that the pipeline is correct and stays correct.",
    evaluate: notImplemented,
  },
  {
    id: 12,
    title: "Performance and Evaluation",
    goal: "Measured, defensible numbers — precision/recall, throughput, latency.",
    evaluate: notImplemented,
  },
  {
    id: 13,
    title: "Observability",
    goal: "Production-style visibility into what the system is doing.",
    evaluate: notImplemented,
  },
  {
    id: 14,
    title: "Security Hardening",
    goal: "The project's own security posture, treated as part of the pitch.",
    evaluate: notImplemented,
  },
  {
    id: 15,
    title: "Deployment",
    goal: "Anyone can clone the repo and have the full system running locally within a few commands.",
    evaluate: notImplemented,
  },
];
