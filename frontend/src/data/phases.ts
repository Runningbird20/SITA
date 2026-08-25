import type { BackendStatus } from "../hooks/useBackendStatus";

export type PhaseStatusValue =
  "implemented" | "implemented_static" | "not_implemented" | "broken" | "checking";

export interface Phase {
  id: number;
  title: string;
  goal: string;
  /** How this phase's status is determined — three kinds:
   *  - `liveCheck(...)`: a real HTTP surface exists; status is computed from
   *    a live backend response (green "Working", or red "Broken" if the
   *    check fails or the backend is unreachable). Always prefer this.
   *  - `staticImplemented`: the phase is genuinely complete (its own
   *    PHASE-N.md report says so, with real tests), but has no
   *    live-checkable HTTP surface yet — green "Implemented", asserted
   *    rather than verified at runtime. Only for phases that are actually
   *    done, never for partial/in-progress work.
   *  - `notImplemented`: nothing built yet — gray.
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

const staticImplemented: Phase["evaluate"] = () => "implemented_static";

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
    // No REST endpoint exists yet (deliberately deferred to Phase 9), so
    // there's nothing to live-check — but the phase is genuinely complete:
    // 7 rules, 99 passing tests, verified against SQLite and Postgres. See
    // Documentation/PHASE-3.md.
    evaluate: staticImplemented,
  },
  {
    id: 4,
    title: "IOC Extraction",
    goal: "Pull structured indicators out of events/alerts, validated deterministically.",
    // Same shape as Phase 3: no REST endpoint yet (deferred to Phase 9), but
    // genuinely complete — 6 regex extractors + username, all 9 IOCType
    // values verified through the real pipeline against SQLite and
    // Postgres. See Documentation/PHASE-4.md.
    evaluate: staticImplemented,
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
