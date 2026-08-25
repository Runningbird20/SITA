# SITA — Local Security Incident Triage Agent

Engineering roadmap. This is a living document — check items off as completed, and update the **Architecture Decisions / Open Questions** section as decisions are made rather than leaving them stale.

## Legend

- `[HIGH VALUE]` — disproportionately strengthens the portfolio/resume story; don't skip these even under time pressure.
- `[STRETCH]` — nice to have once the core pipeline works end-to-end; sequence last within a phase.

## Proposed Repository Layout

```
SITA/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI routers (events, alerts, incidents, iocs, detections, ai, mitre)
│   │   ├── core/              # config, logging, security, exceptions
│   │   ├── db/                 # SQLAlchemy session/engine, base models, Alembic glue
│   │   ├── models/            # SQLAlchemy ORM models
│   │   ├── schemas/           # Pydantic request/response schemas
│   │   ├── ingestion/          # source adapters -> raw events
│   │   ├── normalization/     # raw -> SecurityEvent canonical schema
│   │   ├── ioc/                 # extraction + validation
│   │   ├── detection/          # deterministic rule engine + rules/
│   │   ├── correlation/        # incident correlation engine
│   │   ├── mitre/              # local ATT&CK dataset + mapping logic
│   │   ├── llm/                # LLMProvider interface, OllamaProvider, MockProvider, prompts/
│   │   ├── triage/             # orchestrates deterministic + LLM steps into AnalysisResult
│   │   ├── recommendations/    # next-step recommendation logic
│   │   └── main.py
│   ├── alembic/
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── fixtures/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── api/                # typed API client
│   │   └── types/
│   ├── package.json
│   └── Dockerfile
├── data/
│   ├── synthetic_events/       # generated/curated sample event sets
│   ├── mitre/                  # local ATT&CK STIX/JSON subset
│   └── eval/                   # labeled evaluation datasets
├── docs/
│   ├── architecture.md
│   ├── correlation_strategy.md
│   └── evaluation_methodology.md
├── docker-compose.yml
├── .env.example
├── TODO.md
└── README.md
```

---

## Phase 0: Project Foundation

**Goal:** A cloneable, runnable skeleton with dev tooling, containers, and CI in place before any feature logic is written.

**Tasks**

- [ ] Create `backend/` and `frontend/` top-level structure per layout above
- [ ] Initialize backend with `uv` (`pyproject.toml`, lockfile, `uv.lock`)
- [ ] Add FastAPI + Uvicorn as base backend deps; confirm `uvicorn app.main:app` boots an empty app
- [ ] Configure Ruff (lint + format) with a project `ruff.toml` / `pyproject.toml` section
- [ ] Initialize frontend with Vite + React + TypeScript template
- [ ] Configure ESLint + Prettier for the frontend
- [ ] Add `docker-compose.yml` with services: `backend`, `frontend`, `postgres`, `ollama` (no service requires a paid API key)
- [ ] Write backend `Dockerfile` (multi-stage: deps install via `uv`, then runtime image)
- [ ] Write frontend `Dockerfile` (build stage + static serve, or Vite dev server for local)
- [ ] Design configuration management: `backend/app/core/config.py` using `pydantic-settings`, reading from `.env`
- [ ] Write `.env.example` documenting every configurable variable (DB URL, Ollama host/model, log level, etc.)
- [ ] Set up structured logging (JSON logs, configurable level) as a reusable `core/logging.py` — used from Phase 0 onward so every later phase logs consistently
- [ ] `[HIGH VALUE]` Set up GitHub Actions CI: lint (Ruff + ESLint), backend tests (pytest), frontend build, on every PR
- [ ] Add pre-commit hooks (Ruff, ESLint) `[STRETCH]`
- [ ] Write root `README.md` covering project purpose, architecture diagram, and quick-start (expand in Phase 15)
- [ ] Add `docs/architecture.md` stub to be filled in as phases land
- [ ] Add `LICENSE` (MIT or similar) `[STRETCH]`
- [ ] Add `.gitignore` covering Python, Node, Docker, env files, IDE artifacts

**Definition of Done:** `docker compose up` brings up an empty FastAPI backend (health check responds), an empty React app, Postgres, and Ollama. CI runs lint + a trivial passing test on push. `.env.example` fully documents configuration.

---

## Phase 1: Core Data Model

**Goal:** Stable, well-typed schemas that every later phase builds on. Getting this right early avoids painful migrations later.

**Tasks**

- [ ] Define `SecurityEvent` (normalized, source-agnostic single observation: timestamp, source type, raw payload, normalized fields, entity refs)
- [ ] Define `Alert` (output of the detection engine: rule/source that fired, severity, related events, IOCs, MITRE technique refs, status)
- [ ] Define `Incident` (correlated group of alerts: title, status, severity, timeline, related entities, related AI analyses)
- [ ] Define `IOC` (type, value, first_seen, last_seen, confidence, validation status, source alerts/events)
- [ ] Define `Entity` (host, user, IP, or other actor referenced across events — enables correlation)
- [ ] Define `Detection` (a deterministic rule definition + its firing metadata, distinct from the `Alert` instance it produces)
- [ ] Define `MITRETechnique` (technique ID, name, tactic, description — locally stored subset of ATT&CK)
- [ ] Define `Recommendation` (next-step suggestion: text, source [rule-based vs LLM], related incident/alert, priority)
- [ ] Define `AnalysisResult` (LLM output envelope: model/provider used, prompt version, raw + parsed structured output, confidence, timestamp, latency) — see [[llm-provider-abstraction]] in Phase 6
- [ ] `[HIGH VALUE]` Explicitly tag every field/table as `deterministic` or `ai_generated` at the schema level (e.g., separate tables/columns, never commingled) so provenance is enforced by the data model, not just convention
- [ ] Design relational schema (SQLAlchemy models) capturing the above and their relationships (Event ↔ Alert ↔ Incident ↔ IOC ↔ Entity ↔ MITRETechnique ↔ Recommendation ↔ AnalysisResult)
- [ ] Set up Alembic migrations, first migration creating all core tables
- [ ] Implement the data-layer abstraction: SQLAlchemy engine/session configured from `DATABASE_URL`, supporting both `postgresql+psycopg` and `sqlite` dialects without code changes elsewhere
- [ ] Write Pydantic schemas mirroring ORM models for API I/O (request/response), separate from ORM models
- [ ] Add DB-level indexes for expected hot paths (event timestamp, IOC value, entity identifiers, incident status)
- [ ] Write unit tests validating schema constraints (required fields, enum values, FK integrity)

**Definition of Done:** All core tables exist via Alembic migration, apply cleanly against both Postgres and SQLite, and are covered by model-level tests. ER diagram committed to `docs/architecture.md`.

---

## Phase 2: Event Ingestion

**Goal:** Accept simulated security events from multiple source types and normalize them into the common schema.

**Tasks**

- [ ] Define the common normalized event schema fields shared across all source types (timestamp, source_type, entity refs, raw payload, normalized attributes)
- [ ] Implement ingestion adapter: authentication events (SSH/login success/failure, source IP, user, host)
- [ ] Implement ingestion adapter: endpoint events (process execution, command line, parent/child process)
- [ ] Implement ingestion adapter: network events (connection tuples, ports, protocol, bytes)
- [ ] Implement ingestion adapter: DNS events (query, response, record type, resolver)
- [ ] Implement ingestion adapter: web server events (HTTP method, path, status, user agent, source IP)
- [ ] Implement a normalization layer that maps each adapter's raw shape into `SecurityEvent`
- [ ] Support both batch ingestion (upload/import a file of events) and a REST endpoint for streaming individual events
- [ ] `[HIGH VALUE]` Build a synthetic dataset generator (or curated static datasets) producing realistic events for each source type, including both benign and attack-pattern traffic
- [ ] Include at least one full "attack scenario" dataset spanning multiple source types (e.g., brute force → lateral movement → data access) for end-to-end demos
- [ ] Validate and reject malformed events at the ingestion boundary (schema validation, not silent drops)
- [ ] Write ingestion + normalization unit tests per source type
- [ ] Document the normalized event schema in `docs/architecture.md`

**Definition of Done:** Each of the 5 source types can be ingested via file import and/or API, normalized into `SecurityEvent` rows, and persisted. At least one multi-stage synthetic attack scenario dataset exists and is checked in under `data/synthetic_events/`.

---

## Phase 3: Detection Engine

**Goal:** Deterministic, explainable rules that turn normalized events into structured alerts — the system's ground truth, independent of the LLM.

**Tasks**

- [ ] Design the rule engine interface (a `DetectionRule` base with `evaluate(events) -> Alert | None`, or windowed/stateful variant)
- [ ] Implement rule: SSH brute force (repeated auth failures from one source against one target within a window)
- [ ] Implement rule: password spraying (many usernames, few attempts each, one source, within a window)
- [ ] Implement rule: suspicious authentication patterns (e.g., unusual hour, new source IP for a known user)
- [ ] Implement rule: port scanning (one source touching many destination ports/hosts in a short window)
- [ ] Implement rule: suspicious PowerShell activity (encoded commands, download cradles, suspicious flags in command-line events)
- [ ] Implement rule: impossible travel (same user authenticating from geographically implausible locations within an implausible time delta)
- [ ] Implement rule: repeated authentication failures (generalized threshold rule, distinct from brute force's single-source/single-target framing)
- [ ] Each rule produces a structured `Alert` with: rule ID, matched events, severity, confidence, human-readable rationale
- [ ] Implement deterministic severity scoring (e.g., weighted factors: rule criticality, asset sensitivity, volume/frequency) — kept separate from any LLM severity *explanation*
- [ ] Build a rule execution pipeline that runs on ingestion (or on-demand) and persists resulting alerts
- [ ] `[HIGH VALUE]` Write a test suite with labeled synthetic scenarios per rule (true positives + true negatives) to measure precision/recall — feeds Phase 12
- [ ] Document each rule's logic, thresholds, and rationale in `docs/architecture.md` or a dedicated `docs/detection_rules.md`

**Definition of Done:** All 7 rules run against the Phase 2 synthetic datasets and produce correctly-labeled alerts with documented false-positive/false-negative behavior on the test fixtures.

---

## Phase 4: IOC Extraction

**Goal:** Pull structured indicators out of events/alerts, validated deterministically, with LLM assistance as a supplement — not a replacement.

**Tasks**

- [ ] Implement deterministic extractor: IPv4 addresses (regex + validation, reject private/reserved ranges where relevant to context)
- [ ] Implement deterministic extractor: IPv6 addresses
- [ ] Implement deterministic extractor: domains (regex + basic TLD/format validation)
- [ ] Implement deterministic extractor: URLs
- [ ] Implement deterministic extractor: file hashes (MD5/SHA1/SHA256, validated by length/charset)
- [ ] Implement deterministic extractor: email addresses
- [ ] Implement deterministic extractor: usernames (context-aware — only from fields known to carry them, to avoid false positives)
- [ ] Deduplicate and upsert IOCs against the `IOC` table, tracking first_seen/last_seen and source references
- [ ] `[STRETCH]` Add LLM-assisted extraction as a secondary pass over free-text fields (e.g., log messages) that the regex layer can't parse, with output validated against the same deterministic validators before being trusted
- [ ] Clearly tag each stored IOC with its extraction source (`regex` vs `llm_assisted`)
- [ ] Write extraction accuracy tests against a labeled fixture set (known IOCs embedded in synthetic text)

**Definition of Done:** All 7 IOC types are deterministically extracted and validated with measured precision/recall against a labeled fixture set. If implemented, LLM-assisted extraction never bypasses deterministic validation.

---

## Phase 5: Incident Correlation

**Goal:** Group related alerts into incidents using explainable, deterministic correlation logic.

**Tasks**

- [ ] Design and document the correlation strategy in `docs/correlation_strategy.md` before implementing (see [[correlation-strategy]] open question below)
- [ ] Implement time-window-based correlation (alerts within a configurable rolling window are candidates for grouping)
- [ ] Implement shared-IP correlation
- [ ] Implement shared-user correlation
- [ ] Implement shared-host correlation
- [ ] Implement shared-domain correlation
- [ ] Implement shared-IOC correlation (generalizes the above via the `IOC` table)
- [ ] Implement shared-MITRE-technique correlation (alerts mapped to the same/related techniques within a window)
- [ ] Combine correlation signals into a single scoring function that decides whether alerts join an existing incident, start a new one, or stay uncorrelated
- [ ] Persist incident-to-alert relationships and maintain incident-level rollup fields (severity, status, first/last activity)
- [ ] `[HIGH VALUE]` Validate correlation against the multi-stage synthetic attack scenario (Phase 2) — confirm the pipeline reconstructs it as a single incident, not scattered alerts
- [ ] Write correlation unit/integration tests covering merge, split, and no-match cases

**Definition of Done:** Alerts from the multi-stage attack scenario correlate into one incident with a documented, explainable strategy; unrelated alerts remain separate. Strategy and scoring are documented in `docs/correlation_strategy.md`.

---

## Phase 6: Local LLM Integration

**Goal:** A clean provider abstraction so the AI layer is swappable, testable without Ollama running, and never a single point of failure for the system.

**Tasks**

- [ ] `[HIGH VALUE]` Design `LLMProvider` interface (e.g., `generate(prompt, schema, config) -> AnalysisResult`) — see [[llm-provider-abstraction]]
- [ ] Implement `OllamaProvider` (HTTP client against local Ollama instance)
- [ ] Implement `MockProvider` returning deterministic canned/templated responses — used in tests and when Ollama is unavailable, so the app degrades gracefully rather than failing
- [ ] Define structured output contracts (JSON schemas) per LLM task instead of relying on free-form text — enforce via Ollama's JSON mode/grammar or explicit parsing + validation
- [ ] Implement prompt versioning (prompts stored as versioned templates, version recorded on every `AnalysisResult`)
- [ ] Implement model configuration (model name, temperature, max tokens, etc. sourced from config, not hardcoded)
- [ ] Implement timeout handling for provider calls
- [ ] Implement retry behavior (bounded retries with backoff on transient failures)
- [ ] Implement response validation (parse + validate against the expected schema; reject/flag malformed output rather than trusting it blindly)
- [ ] Implement failure handling: on provider failure/timeout/invalid response, the system continues operating on deterministic results alone and clearly marks AI analysis as unavailable
- [ ] Log model metadata per call: provider, model name, prompt version, latency, token counts if available, success/failure
- [ ] Document recommended local model(s) and rationale (see [[recommended-local-model]] open question)
- [ ] Write provider tests using `MockProvider` (no live Ollama dependency in CI)
- [ ] `[STRETCH]` Write opportunistic integration tests that run only when a real Ollama instance is detected

**Definition of Done:** The app runs fully (ingestion → detection → correlation → API → frontend) with `MockProvider` and zero network calls. Swapping to `OllamaProvider` via config requires no code changes elsewhere. Every `AnalysisResult` records provider, model, prompt version, and latency.

---

## Phase 7: AI-Powered Triage

**Goal:** Use the LLM for reasoning/summarization tasks that deterministic code can't do well — always clearly labeled as AI-generated and layered on top of, never replacing, deterministic output.

**Tasks**

- [ ] Implement incident summarization (structured prompt over an incident's alerts/events/IOCs → human-readable summary)
- [ ] Implement severity *explanation* (LLM explains the deterministic severity score in natural language; it does not compute the score)
- [ ] Implement attack classification (LLM suggests an attack category/kill-chain stage as a labeled hypothesis, not a ground-truth verdict)
- [ ] Implement investigation hypothesis generation (plausible explanations for the observed activity)
- [ ] Implement recommended investigation steps (distinct from Phase-9 rule-based recommendations — LLM-generated, contextual)
- [ ] Implement MITRE ATT&CK technique suggestions from the LLM, cross-checked against the deterministic mapping in Phase 8 (flag disagreements rather than silently trusting either source)
- [ ] `[HIGH VALUE]` Enforce UI/API-level separation: every AI-generated field is wrapped in an `AnalysisResult`-linked structure and visually/structurally distinct from deterministic `Alert`/`Detection`/`Incident` fields
- [ ] Orchestrate the above as a `triage` pipeline step that runs after correlation, is idempotent/re-runnable, and stores results linked to the triggering incident
- [ ] Write tests validating that structured LLM output is correctly parsed, validated, and rejected/flagged when malformed (using `MockProvider` with both valid and deliberately malformed fixtures)

**Definition of Done:** Every incident in the dashboard can show an AI analysis panel populated end-to-end via `MockProvider` (and, when available, `OllamaProvider`), with every AI claim traceable to an `AnalysisResult` row and visually distinguished from deterministic findings.

---

## Phase 8: MITRE ATT&CK Integration

**Goal:** Ground the system in a recognized security framework using local data — no runtime dependency on an external API.

**Tasks**

- [ ] Source and vendor a local subset of MITRE ATT&CK data (see [[mitre-data-source]] open question) into `data/mitre/`
- [ ] Build a loader that populates the `MITRETechnique` table from the local dataset
- [ ] Implement deterministic mapping: detection rules declare their associated technique(s) at definition time (e.g., SSH brute force → T1110.001)
- [ ] Implement incident-level technique rollup (union of techniques from all constituent alerts)
- [ ] Support the LLM-suggested techniques from Phase 7 as a separate, labeled source alongside deterministic mappings
- [ ] Design the technique display model: technique ID, name, tactic, evidence (which alert/event triggered it), confidence, and source (`rule` vs `llm`)
- [ ] Write tests confirming every detection rule maps to at least one valid, existing technique ID
- [ ] `[STRETCH]` Add tactic-level rollup/visualization data (group techniques by tactic for the ATT&CK matrix view in Phase 10)

**Definition of Done:** Every rule-based detection carries a deterministic MITRE mapping sourced from local data; the app has zero runtime network dependency on attack.mitre.org or any ATT&CK API.

---

## Phase 9: REST API

**Goal:** A well-documented, consistent API surface over every domain object, ready for the frontend and for external tooling.

**Tasks**

- [ ] Design REST endpoints for `SecurityEvent` (list/filter/get)
- [ ] Design REST endpoints for `Alert` (list/filter/get, filter by severity/rule/status)
- [ ] Design REST endpoints for `Incident` (list/filter/get, including nested alerts/IOCs/AI analyses)
- [ ] Design REST endpoints for `IOC` (list/filter/get, filter by type/confidence)
- [ ] Design REST endpoints for `Detection` (list rule definitions and their metadata)
- [ ] Design REST endpoints for AI analyses (`AnalysisResult`, scoped to an incident/alert)
- [ ] Design REST endpoints for `Recommendation`
- [ ] Design REST endpoints for `MITRETechnique` (list/get, plus incident/alert technique rollups)
- [ ] Implement pagination (cursor or offset-based, consistent across list endpoints)
- [ ] Implement filtering (query params per resource, validated)
- [ ] Implement sorting (whitelisted sortable fields per resource)
- [ ] Implement request validation via Pydantic schemas with clear 4xx error responses
- [ ] Implement consistent error handling (structured error envelope, mapped exception handlers)
- [ ] `[HIGH VALUE]` Ensure full OpenAPI/Swagger docs are auto-generated and accurate (FastAPI default) — polish descriptions/examples since this is a resume artifact reviewers may actually open
- [ ] Add an endpoint to trigger/re-run the pipeline (ingest → detect → correlate → triage) for demo purposes
- [ ] Write API tests (status codes, pagination, filtering, error cases) per resource

**Definition of Done:** All domain objects are exposed via a consistent, paginated, filterable, sortable REST API with auto-generated OpenAPI docs and passing API tests.

---

## Phase 10: Frontend

**Goal:** A dense, usable SOC-style dashboard — the primary visual artifact for demos and interviews.

**Tasks**

- [ ] Set up typed API client (generated from OpenAPI schema or hand-written typed fetch layer)
- [ ] Build overview dashboard (counts by severity, recent incidents, alert volume over time)
- [ ] Build alert list view (filterable/sortable table, severity indicators)
- [ ] Build incident list view (status, severity, alert count, last activity)
- [ ] Build incident detail page (constituent alerts, IOCs, entities, MITRE techniques, AI analysis panel, recommendations)
- [ ] Build IOC explorer (searchable/filterable, links back to source alerts/events)
- [ ] Build detection page (list of rule definitions, their descriptions, and recent firings)
- [ ] Build MITRE ATT&CK visualization (matrix-style view highlighting techniques observed in the environment)
- [ ] `[HIGH VALUE]` Build the AI analysis panel with unmistakable visual separation from deterministic content (distinct styling, "AI-generated" labeling, confidence/model metadata shown)
- [ ] Build incident timeline (chronological view of events/alerts within an incident)
- [ ] Implement loading/empty/error states across all views
- [ ] Apply consistent design system/theming (component library or hand-rolled, dark-mode-friendly SOC aesthetic) `[STRETCH]`
- [ ] Add basic frontend tests for key components `[STRETCH]`

**Definition of Done:** A reviewer can open the dashboard, browse incidents end-to-end from overview → incident detail → AI analysis → MITRE mapping, with no dead ends or unhandled empty states.

---

## Phase 11: Testing

**Goal:** Confidence that the pipeline is correct and stays correct — this is what separates a portfolio project from a toy demo.

**Tasks**

- [ ] Unit tests for normalization, IOC extraction, detection rules, correlation logic (largely produced incrementally in earlier phases — this phase closes gaps and raises coverage)
- [ ] Integration tests exercising the full pipeline (ingest → normalize → detect → extract IOCs → correlate → triage) against synthetic datasets
- [ ] API tests for every resource and error path
- [ ] Database tests (migrations apply cleanly on both Postgres and SQLite; constraints enforced)
- [ ] Detection rule tests with labeled true/false-positive fixtures (already started in Phase 3 — consolidate here)
- [ ] IOC extraction accuracy tests (already started in Phase 4 — consolidate here)
- [ ] Incident correlation accuracy tests (already started in Phase 5 — consolidate here)
- [ ] LLM response validation tests: valid structured output, malformed output, timeout, provider failure — all via `MockProvider`
- [ ] Failure-case tests across the stack (bad input, DB unavailable, LLM unavailable) confirming graceful degradation, not crashes
- [ ] `[HIGH VALUE]` Track and report test coverage in CI; set a minimum threshold
- [ ] Create reusable synthetic fixtures shared across unit/integration/API tests (avoid duplicated ad-hoc data)

**Definition of Done:** CI runs the full test suite (unit + integration + API + DB) on every PR with a published coverage number; all failure-injection tests pass (system degrades gracefully rather than crashing).

---

## Phase 12: Performance and Evaluation

**Goal:** Turn the project into something with measured, defensible numbers — critical for resume credibility.

**Tasks**

- [ ] Define and implement a benchmark harness for events processed per second (ingestion + normalization throughput)
- [ ] Measure detection latency (event ingested → alert produced)
- [ ] Measure incident correlation latency (alert produced → incident updated)
- [ ] Measure API latency (p50/p95/p99 per endpoint under load)
- [ ] Measure database query performance for common access patterns (incident list, IOC search)
- [ ] Measure LLM response latency per triage task type
- [ ] Capture LLM token usage where the provider exposes it
- [ ] `[HIGH VALUE]` Build a labeled evaluation dataset (`data/eval/`) with known ground-truth alerts/incidents distinct from the dev/demo synthetic data (avoid evaluating on data the rules were tuned against)
- [ ] Compute and report detection precision/recall against the evaluation dataset
- [ ] Compute and report IOC extraction precision/recall against the evaluation dataset
- [ ] Compute and report incident correlation accuracy (correct grouping rate) against the evaluation dataset
- [ ] Document evaluation methodology in `docs/evaluation_methodology.md` (dataset construction, ground-truth labeling process, metric definitions)
- [ ] Publish a benchmarks summary (table or short report) suitable for linking from the resume/README

**Definition of Done:** A documented, reproducible evaluation run produces concrete precision/recall/throughput/latency numbers against a held-out labeled dataset, written up in `docs/evaluation_methodology.md`.

---

## Phase 13: Observability

**Goal:** Production-style visibility into what the system is doing — another strong signal of engineering maturity.

**Tasks**

- [ ] Ensure structured (JSON) logging is consistent across ingestion, detection, correlation, LLM, and API layers (builds on Phase 0 logging setup)
- [ ] Implement request IDs (generated per API request, propagated through logs and, where relevant, through async pipeline processing triggered by that request)
- [ ] Emit processing metrics (events ingested, alerts generated, incidents created/updated) — counters at minimum
- [ ] Emit detection metrics (rule firing counts, rule execution latency)
- [ ] Emit LLM metrics (calls made, success/failure rate, latency, provider/model in use)
- [ ] Add basic error tracking (structured error logs with enough context to debug without reproducing)
- [ ] Add health check endpoints (`/healthz` covering DB connectivity and, optionally, LLM provider reachability)
- [ ] `[STRETCH]` Expose metrics in Prometheus format and provide a simple Grafana dashboard/docker-compose profile
- [ ] Document the observability approach in `docs/architecture.md`

**Definition of Done:** Every request is traceable end-to-end via request ID in logs; core throughput/latency/error metrics are queryable (at minimum via logs, ideally via a metrics endpoint); health checks accurately reflect system state.

---

## Phase 14: Security Hardening

**Goal:** Since this is a security-focused project, its own security posture is part of the pitch — treat it accordingly.

**Tasks**

- [ ] Enforce input validation at every boundary (API request bodies, file uploads for ingestion, LLM output)
- [ ] `[HIGH VALUE]` Implement prompt injection resistance: treat event/log content embedded in LLM prompts as untrusted data, not instructions — document the threat model and mitigations (e.g., clear prompt structure/delimiters, output schema enforcement, never letting LLM output trigger actions directly)
- [ ] Enforce LLM output validation as a security boundary, not just a correctness check (reject anything that doesn't conform to the expected schema before it's persisted or displayed)
- [ ] Add authentication for the dashboard/API (even a simple local auth scheme — this is expected by SOC-tool reviewers)
- [ ] Add rate limiting on API endpoints, particularly ingestion and LLM-triggering endpoints
- [ ] Ensure secrets (DB credentials, any future API keys) are handled via environment variables / `.env`, never committed, and documented in `.env.example`
- [ ] Review container security (non-root users in Dockerfiles, minimal base images, no unnecessary exposed ports)
- [ ] Add dependency scanning to CI (`pip-audit`/`uv`-compatible equivalent for backend, `npm audit` for frontend)
- [ ] Add standard security headers to API responses (CSP, X-Content-Type-Options, etc. where applicable)
- [ ] `[STRETCH]` Run a self-review using the project's own detection logic conceptually — document how the app itself would be evaluated against basic hardening checklists (e.g., OWASP ASVS subset)

**Definition of Done:** Prompt injection threat model is documented and mitigated; authentication and rate limiting are in place; CI includes dependency scanning; no secrets are ever committed.

---

## Phase 15: Deployment

**Goal:** Anyone can clone the repo and have the full system running locally within a few commands.

**Tasks**

- [ ] Finalize `docker-compose.yml` covering backend, frontend, Postgres, and Ollama with correct service dependencies/health checks
- [ ] Document installing dependencies (Docker, and native fallback: `uv`, Node version)
- [ ] Document starting PostgreSQL (via Compose) and running migrations
- [ ] Document starting Ollama (via Compose) and pulling the recommended model(s)
- [ ] Document starting the backend (Compose and native dev-server paths)
- [ ] Document starting the frontend (Compose and native dev-server paths)
- [ ] Document loading synthetic security events (seed script or API import)
- [ ] Document viewing the dashboard (URL, default demo flow to click through)
- [ ] `[HIGH VALUE]` Provide a single one-shot bootstrap script/command (e.g., `make demo` or `./scripts/demo.sh`) that brings up the stack, applies migrations, loads synthetic data, and runs the pipeline so a reviewer sees a populated dashboard immediately
- [ ] Add architecture diagram and screenshots to the root README
- [ ] Verify the full quick-start works on a clean checkout (no leftover local state assumptions)

**Definition of Done:** A developer with only Docker installed can clone the repo, run one documented command sequence (ideally one script), and see a populated dashboard with correlated incidents and AI-generated triage within minutes.

---

## Architecture Decisions / Open Questions

These need explicit decisions before or during the relevant phase — don't let them default silently.

- **`[[postgres-vs-sqlite]]` PostgreSQL vs SQLite for local development.** Plan is Postgres as the "real" target (via Compose) with SQLite supported for fast local/test runs through the SQLAlchemy abstraction. Decide: should CI run tests against both, or just SQLite for speed with a periodic/optional Postgres run?
- **`[[recommended-local-model]]` Recommended local model.** Needs a concrete choice (e.g., a Llama 3.x or Qwen2.5 instruct variant in the 7–8B range) balancing: runs on typical dev hardware, supports structured/JSON output well, reasonable latency for demo purposes. Should be pinned in `.env.example` with a documented fallback smaller model for constrained hardware.
- **Orchestration: hand-rolled vs LangChain/LangGraph.** Leaning toward implementing the `LLMProvider` abstraction and triage pipeline ourselves — the project brief explicitly favors this, and it's a stronger engineering signal than wrapping a framework. Revisit only if a specific need (e.g., complex multi-step agent loops) can't be reasonably hand-rolled.
- **`[[event-schema-design]]` Event schema design specifics.** The high-level `SecurityEvent` shape is sketched in Phase 1/2, but exact field-level design (how much source-specific detail lives in a `raw` JSON blob vs. promoted normalized columns) needs to be finalized once real sample data from all 5 source types is in hand.
- **`[[correlation-strategy]]` Incident correlation strategy specifics.** Phase 5 lists the signals (time window, shared IP/user/host/domain/IOC/technique) but not their combination logic — e.g., weighted scoring vs. rule-based thresholds vs. graph-based clustering. Needs a decision + write-up in `docs/correlation_strategy.md` before implementation, since this materially affects both correctness and how impressive the "systems design" story is.
- **`[[mitre-data-source]]` MITRE ATT&CK data source.** Plan is a local static subset (e.g., a pinned snapshot of the ATT&CK STIX/JSON dataset) rather than a live API. Needs a decision on scope (full Enterprise matrix vs. a curated subset matching implemented detection rules) and an update/refresh process (manual, periodic re-vendoring).
- **How AI confidence should be represented.** Needs a decision on whether LLM outputs carry a self-reported confidence (unreliable but simple), a derived confidence (e.g., based on schema-validation success, agreement with deterministic signals), or no numeric confidence at all (just clear "AI-generated, unverified" labeling). Leaning toward the latter two combined, not raw self-reported LLM confidence.
- **How to evaluate AI-generated triage.** Unlike detection rules, LLM summaries/hypotheses don't have a clean precision/recall metric. Needs a decision: manual rubric-based scoring against the eval dataset (e.g., rate summaries 1–5 on accuracy/completeness), automated checks (does the summary mention the correct entities/IOCs present in the incident), or both. Document methodology alongside Phase 12.
- **Authentication approach for the dashboard/API (Phase 14).** Needs a decision on scope — single shared local credential vs. simple user accounts — appropriate for a local-first demo project without over-engineering.

---

## Potential Resume Metrics

Track these as the project matures so eventual resume bullets can cite concrete numbers instead of vague claims.

- Number of distinct simulated event sources supported
- Number of events processed (total, and events/sec sustained throughput)
- Number of deterministic detection rules implemented
- Detection precision/recall on the labeled evaluation dataset
- IOC extraction precision/recall (per IOC type and overall)
- Incident correlation accuracy (% of eval-dataset incidents correctly reconstructed)
- Number of MITRE ATT&CK techniques mapped/supported
- Number of AI-assisted triage steps automated (summarization, classification, hypothesis generation, recommendations, etc.)
- Median and p95 API latency
- Median and p95 detection latency (event → alert)
- Median and p95 incident correlation latency (alert → incident update)
- Median and p95 LLM response latency per triage task
- LLM token usage per triage run (if exposed by the provider)
- Test coverage percentage
- Number of automated tests (unit/integration/API combined)
