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
   *    live-checkable HTTP surface yet — yellow "Implemented", asserted
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
    // PHASE-3.md promised this would switch from static "Implemented" to a
    // live check "once Phase 9 exposes alerts over the API" — Phase 9 did,
    // via GET /api/v1/detections. Same shallow-but-honest check as Phase 2:
    // confirms the route is genuinely mounted, not that any rule has fired.
    evaluate: liveCheck(
      (status) =>
        status.healthz?.database === "ok" &&
        (status.openApiPaths?.has("/api/v1/detections") ?? false),
    ),
  },
  {
    id: 4,
    title: "IOC Extraction",
    goal: "Pull structured indicators out of events/alerts, validated deterministically.",
    // Live since Phase 9's GET /api/v1/iocs — same promise/pattern as Phase 3.
    evaluate: liveCheck(
      (status) =>
        status.healthz?.database === "ok" && (status.openApiPaths?.has("/api/v1/iocs") ?? false),
    ),
  },
  {
    id: 5,
    title: "Incident Correlation",
    goal: "Group related alerts into incidents using explainable, deterministic correlation logic.",
    // Live since Phase 9's GET /api/v1/incidents — same promise/pattern as Phase 3/4.
    evaluate: liveCheck(
      (status) =>
        status.healthz?.database === "ok" &&
        (status.openApiPaths?.has("/api/v1/incidents") ?? false),
    ),
  },
  {
    id: 6,
    title: "Local LLM Integration",
    goal: "A clean provider abstraction so the AI layer is swappable and never a single point of failure.",
    // Deliberately still static, unlike Phase 3/4/5/7/8: the LLMProvider
    // abstraction has no domain-object identity of its own for Phase 9 to
    // expose a resource for — Phase 7's AnalysisResult rows are what Phase 9
    // can live-check, not the provider layer itself. Genuinely complete —
    // LLMProvider base class, MockProvider, OllamaProvider, structured
    // output validation, retry/confidence logic, all verified against a
    // real running Ollama instance. See Documentation/PHASE-6.md.
    evaluate: staticImplemented,
  },
  {
    id: 7,
    title: "AI-Powered Triage",
    goal: "LLM-assisted reasoning, always clearly labeled and layered on top of — never replacing — deterministic output.",
    // Live since Phase 9's GET /api/v1/analysis-results.
    evaluate: liveCheck(
      (status) =>
        status.healthz?.database === "ok" &&
        (status.openApiPaths?.has("/api/v1/analysis-results") ?? false),
    ),
  },
  {
    id: 8,
    title: "MITRE ATT&CK Integration",
    goal: "Ground the system in a recognized security framework using local data.",
    // Live since Phase 9's GET /api/v1/mitre-techniques.
    evaluate: liveCheck(
      (status) =>
        status.healthz?.database === "ok" &&
        (status.openApiPaths?.has("/api/v1/mitre-techniques") ?? false),
    ),
  },
  {
    id: 9,
    title: "REST API",
    goal: "A well-documented, consistent API surface over every domain object.",
    // Checks the one endpoint genuinely new to Phase 9 itself rather than
    // any single resource's list/get pair (those are Phase 3-8's own
    // live checks above) — the pipeline-trigger endpoint, plus pagination,
    // filtering, sorting, and the structured error envelope underneath
    // every resource. See Documentation/PHASE-9.md.
    evaluate: liveCheck(
      (status) =>
        status.healthz?.database === "ok" &&
        (status.openApiPaths?.has("/api/v1/pipeline/run") ?? false),
    ),
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
