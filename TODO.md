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

- [x] Create `backend/` and `frontend/` top-level structure per layout above
- [x] Initialize backend with `uv` (`pyproject.toml`, lockfile, `uv.lock`)
- [x] Add FastAPI + Uvicorn as base backend deps; confirm `uvicorn app.main:app` boots an empty app — verified locally via `uv run uvicorn app.main:app` and inside the Docker container; `/healthz` and `/docs` both respond
- [x] Configure Ruff (lint + format) with a project `ruff.toml` / `pyproject.toml` section — `uv run ruff check .` and `uv run ruff format --check .` both pass
- [x] Initialize frontend with Vite + React + TypeScript template
- [x] Configure ESLint + Prettier for the frontend — swapped out the template's default `oxlint` for ESLint (flat config, typescript-eslint, react-hooks/react-refresh plugins) + Prettier, per the project's stated tooling direction; `npm run lint` / `npm run format:check` pass
- [x] Add `docker-compose.yml` with services: `backend`, `frontend`, `postgres`, `ollama` (no service requires a paid API key) — all four services verified to build/start; `ollama` confirmed to pull and boot (no model pulled yet — that's a Phase 15 quick-start step, and a multi-GB download)
- [x] Write backend `Dockerfile` (deps installed via `uv` in a cached layer before source is copied, then a non-root runtime user) — note: implemented as a single `FROM` stage with layered `uv sync` calls for build-cache efficiency rather than multiple `FROM ... AS` stages; revisit as a literal multi-stage build if a smaller final image size becomes a priority
- [x] Write frontend `Dockerfile` (build stage + static serve, or Vite dev server for local) — three targets: `dev` (Vite dev server, used by compose), `build`, and `production` (nginx static serve)
- [x] Design configuration management: `backend/app/core/config.py` using `pydantic-settings`, reading from `.env`
- [x] Write `.env.example` documenting every configurable variable (DB URL, Ollama host/model, log level, etc.)
- [x] Set up structured logging (JSON logs, configurable level) as a reusable `core/logging.py` — used from Phase 0 onward so every later phase logs consistently
- [x] `[HIGH VALUE]` Set up GitHub Actions CI: lint (Ruff + ESLint), backend tests (pytest), frontend build, on every PR — `.github/workflows/ci.yml`; not yet run on an actual push/PR since this hasn't been pushed to GitHub
- [x] Add pre-commit hooks (Ruff, ESLint) `[STRETCH]` — `.pre-commit-config.yaml` added; not yet installed via `pre-commit install` (requires the `pre-commit` tool, not currently installed in this environment)
- [x] Write root `README.md` covering project purpose, architecture diagram, and quick-start (expand in Phase 15)
- [x] Add `docs/architecture.md` stub to be filled in as phases land
- [x] Add `LICENSE` (MIT or similar) `[STRETCH]`
- [x] Add `.gitignore` covering Python, Node, Docker, env files, IDE artifacts — verified `.venv/`, `node_modules/`, and `.env` are actually excluded from `git status`

**Definition of Done:** `docker compose up` brings up an empty FastAPI backend (health check responds), an empty React app, Postgres, and Ollama. CI runs lint + a trivial passing test on push. `.env.example` fully documents configuration.

**Verified so far:** `docker compose build` succeeds for both images; `postgres` + `backend` + `frontend` were brought up together and confirmed working end-to-end (`/healthz` returns `{"status":"ok","database":"ok"}` against the *real* Postgres container, not just SQLite; frontend serves the Vite dev app on `:5173`). `ollama` was brought up independently and confirmed responding (`http://localhost:11434` → `Ollama is running`) — no model pulled yet. Not yet verified: an actual CI run on GitHub (no remote push yet), `pre-commit install` (tool not installed locally), and all four services running together simultaneously in one `docker compose up` (verified in two groups instead, to keep the Ollama image pull — ~2.6GB — off the critical path).

---

## Phase 1: Core Data Model

**Goal:** Stable, well-typed schemas that every later phase builds on. Getting this right early avoids painful migrations later.

**Tasks**

- [x] Define `SecurityEvent` (normalized, source-agnostic single observation: timestamp, source type, raw payload, normalized fields, entity refs) — see [DEF.md](Documentation/DEF.md#1-securityevent)
- [x] Define `Alert` (output of the detection engine: rule/source that fired, severity, related events, IOCs, MITRE technique refs, status) — see [DEF.md](Documentation/DEF.md#4-alert)
- [x] Define `Incident` (correlated group of alerts: title, status, severity, timeline, related entities, related AI analyses) — see [DEF.md](Documentation/DEF.md#5-incident)
- [x] Define `IOC` (type, value, first_seen, last_seen, confidence, validation status, source alerts/events) — see [DEF.md](Documentation/DEF.md#6-ioc)
- [x] Define `Entity` (host, user, IP, or other actor referenced across events — enables correlation) — see [DEF.md](Documentation/DEF.md#2-entity)
- [x] Define `Detection` (a deterministic rule definition + its firing metadata, distinct from the `Alert` instance it produces) — see [DEF.md](Documentation/DEF.md#3-detection)
- [x] Define `MITRETechnique` (technique ID, name, tactic, description — locally stored subset of ATT&CK) — see [DEF.md](Documentation/DEF.md#7-mitretechnique)
- [x] Define `Recommendation` (next-step suggestion: text, source [rule-based vs LLM], related incident/alert, priority) — see [DEF.md](Documentation/DEF.md#9-recommendation)
- [x] Define `AnalysisResult` (LLM output envelope: model/provider used, prompt version, raw + parsed structured output, confidence, timestamp, latency) — see [DEF.md](Documentation/DEF.md#8-analysisresult); see also [[llm-provider-abstraction]] in Phase 6
- [x] `[HIGH VALUE]` Explicitly tag every field/table as `deterministic` or `ai_generated` at the schema level (e.g., separate tables/columns, never commingled) so provenance is enforced by the data model, not just convention — provenance convention documented in [DEF.md](Documentation/DEF.md#conventions)
- [x] Design relational schema (SQLAlchemy models) capturing the above and their relationships (Event ↔ Alert ↔ Incident ↔ IOC ↔ Entity ↔ MITRETechnique ↔ Recommendation ↔ AnalysisResult) — `backend/app/models/`; 9 entity tables + 4 plain junction tables (`alert_event`, `event_ioc`, `alert_ioc`, `detection_mitre_mapping`) + 3 association-object junction tables that carry their own attributes (`EventEntity`, `AlertEntity`, `AlertMitreMapping`), all mirroring [DEF.md](Documentation/DEF.md#entity-relationship-overview)'s ERD; `configure_mappers()` verified clean
- [x] Set up Alembic migrations, first migration creating all core tables — `backend/alembic/`, migration `6224f8f082fb_initial_schema.py`; applied and verified against **both** SQLite and a real Postgres container (`docker compose`); `alembic check` confirms no model/migration drift
- [x] Implement the data-layer abstraction: SQLAlchemy engine/session configured from `DATABASE_URL`, supporting both `postgresql+psycopg` and `sqlite` dialects without code changes elsewhere — `backend/app/db/session.py` (engine/session) + `backend/app/db/types.py` (JSON/JSONB variant type); verified end-to-end against both dialects via the same model/migration code
- [x] Write Pydantic schemas mirroring ORM models for API I/O (request/response), separate from ORM models — `backend/app/schemas/`; one `*Read` schema per entity (`from_attributes=True`). Scope note: only read/response schemas were written, since no endpoints exist yet to consume Create/Update payloads (Phase 9 adds those alongside the actual routes that need them) — not building unused schemas now per the "don't design for hypothetical requirements" principle
- [x] Add DB-level indexes for expected hot paths (event timestamp, IOC value, entity identifiers, incident status) — declared directly on the models (see each table in [DEF.md](Documentation/DEF.md) for its index list); confirmed present in the generated migration and, for Postgres, via `\d` inspection
- [x] Write unit tests validating schema constraints (required fields, enum values, FK integrity) — `backend/tests/unit/test_models.py` (11 cases: full graph round-trip, unique constraints, NOT NULL, FK integrity, both check constraints) + `backend/tests/unit/test_schemas.py`; all passing against an in-memory SQLite DB with `PRAGMA foreign_keys=ON`

**Definition of Done:** All core tables exist via Alembic migration, apply cleanly against both Postgres and SQLite, and are covered by model-level tests. ER diagram committed to `docs/architecture.md`. — met; the ERD itself lives in [DEF.md](Documentation/DEF.md#entity-relationship-overview) with `docs/architecture.md` linking to it rather than duplicating it.

---

## Phase 2: Event Ingestion

**Goal:** Accept simulated security events from multiple source types and normalize them into the common schema.

**Tasks**

- [x] Define the common normalized event schema fields shared across all source types (timestamp, source_type, entity refs, raw payload, normalized attributes) — finalized in [DEF.md § Phase 2](Documentation/DEF.md#2-normalized-shape-securityeventnormalized--finalized); raw per-source contracts also defined in [DEF.md § Phase 2 §1](Documentation/DEF.md#1-raw-event-contracts)
- [x] Implement ingestion adapter: authentication events (SSH/login success/failure, source IP, user, host) — `backend/app/ingestion/auth.py`
- [x] Implement ingestion adapter: endpoint events (process execution, command line, parent/child process) — `backend/app/ingestion/endpoint.py`
- [x] Implement ingestion adapter: network events (connection tuples, ports, protocol, bytes) — `backend/app/ingestion/network.py`
- [x] Implement ingestion adapter: DNS events (query, response, record type, resolver) — `backend/app/ingestion/dns.py`
- [x] Implement ingestion adapter: web server events (HTTP method, path, status, user agent, source IP) — `backend/app/ingestion/web.py`
- [x] Implement a normalization layer that maps each adapter's raw shape into `SecurityEvent` — `IngestionAdapter.parse()` (`backend/app/ingestion/base.py`) validates/normalizes into a `ParsedEvent`; `backend/app/ingestion/service.py` maps `ParsedEvent` → a persisted `SecurityEvent` row
- [x] Support both batch ingestion (upload/import a file of events) and a REST endpoint for streaming individual events — CLI batch importer `backend/app/ingestion/cli.py` (`uv run python -m app.ingestion.cli <source_type> <path>`) and `POST /api/v1/events/{source_type}` (`backend/app/api/events.py`), both sharing `ingest_records()`
- [x] `[HIGH VALUE]` Build a synthetic dataset generator (or curated static datasets) producing realistic events for each source type, including both benign and attack-pattern traffic — `data/synthetic_events/{auth,endpoint,network,dns,web}/` — a `benign.jsonl` baseline plus one attack-pattern file per source type, all verified to ingest with zero rejections
- [x] Include at least one full "attack scenario" dataset spanning multiple source types (e.g., brute force → lateral movement → data access) for end-to-end demos — `data/synthetic_events/scenarios/brute_force_to_lateral_movement/` (auth → network → endpoint → dns, with a narrative `README.md` and shared-entity design for Phase 5 correlation)
- [x] Validate and reject malformed events at the ingestion boundary (schema validation, not silent drops) — every adapter raises `IngestionValidationError` with a specific reason/field; `ingest_records()` catches it per-record and never aborts the rest of the batch
- [x] Write ingestion + normalization unit tests per source type — `backend/tests/unit/test_ingestion_adapters.py` (all 5 adapters), `test_ingestion_service.py`, `test_ingestion_cli.py`, plus `backend/tests/integration/test_events_api.py` and `test_synthetic_datasets.py` (which ingests every real dataset file, including the scenario, and asserts zero rejections)
- [x] Document the normalized event schema in `docs/architecture.md` — [docs/architecture.md](docs/architecture.md) now has an "Event Ingestion" section pointing to the finalized schema in DEF.md, following the same link-rather-than-duplicate pattern used for the Phase 1 ERD

**Definition of Done:** Each of the 5 source types can be ingested via file import and/or API, normalized into `SecurityEvent` rows, and persisted. At least one multi-stage synthetic attack scenario dataset exists and is checked in under `data/synthetic_events/`. — met; verified via the CLI against every dataset file (all 116 events across 5 source types plus the 4-stage scenario persisted with zero rejections) and via a live `POST /api/v1/events/{source_type}` call against a running instance.

---

## Phase 3: Detection Engine

**Goal:** Deterministic, explainable rules that turn normalized events into structured alerts — the system's ground truth, independent of the LLM.

**Tasks**

- [x] Design the rule engine interface (a `DetectionRule` base with `evaluate(events) -> Alert | None`, or windowed/stateful variant) — `backend/app/detection/base.py`: `DetectionRule.evaluate(db, events, config) -> list[RuleFinding]`, defined in [DEF.md § Phase 3](Documentation/DEF.md#rule-engine-interface) before implementation
- [x] Implement rule: SSH brute force (repeated auth failures from one source against one target within a window) — `backend/app/detection/ssh_brute_force.py`; escalates to critical if a same-group success follows
- [x] Implement rule: password spraying (many usernames, few attempts each, one source, within a window) — `backend/app/detection/password_spraying.py`
- [x] Implement rule: suspicious authentication patterns (e.g., unusual hour, new source IP for a known user) — `backend/app/detection/suspicious_auth_pattern.py`; two independent sub-checks, the new-IP check reads full auth history via `db`
- [x] Implement rule: port scanning (one source touching many destination ports/hosts in a short window) — `backend/app/detection/port_scanning.py`
- [x] Implement rule: suspicious PowerShell activity (encoded commands, download cradles, suspicious flags in command-line events) — `backend/app/detection/suspicious_powershell.py`; confidence scales with matched indicator categories
- [x] Implement rule: impossible travel (same user authenticating from geographically implausible locations within an implausible time delta) — `backend/app/detection/impossible_travel.py` + `geoip.py`. **Known limitation**: the GeoIP resolver is a small static stub covering only this project's own synthetic-dataset IPs, not a real geolocation database — see [[geoip-resolver-stub]] in Architecture Decisions below
- [x] Implement rule: repeated authentication failures (generalized threshold rule, distinct from brute force's single-source/single-target framing) — `backend/app/detection/repeated_auth_failures.py`; groups by destination host only, requires ≥3 distinct source IPs so it never re-detects what `ssh_brute_force` already catches
- [x] Each rule produces a structured `Alert` with: rule ID, matched events, severity, confidence, human-readable rationale — verified with real, readable rationale text against actual dataset data (see PHASE-3.md)
- [x] Implement deterministic severity scoring (e.g., weighted factors: rule criticality, asset sensitivity, volume/frequency) — kept separate from any LLM severity *explanation* — `score_severity()` in `base.py`; formula in [DEF.md § Phase 3](Documentation/DEF.md#deterministic-severity-scoring)
- [x] Build a rule execution pipeline that runs on ingestion (or on-demand) and persists resulting alerts — on-demand: `backend/app/detection/pipeline.py` (`run_detection`) + CLI (`backend/app/detection/cli.py`). No REST trigger endpoint added — deliberately deferred to Phase 9, which owns the general API surface. **Known limitation**: not idempotent — re-running over an already-processed range creates duplicate alerts; see [[detection-run-idempotency]] below
- [x] `[HIGH VALUE]` Write a test suite with labeled synthetic scenarios per rule (true positives + true negatives) to measure precision/recall — feeds Phase 12 — 24 rule-level unit tests (`test_detection_rules.py`) plus integration tests running the real pipeline against every real dataset file (`test_detection_against_datasets.py`): every attack-pattern file triggers its intended rule, every benign file triggers zero alerts
- [x] Document each rule's logic, thresholds, and rationale in `docs/architecture.md` or a dedicated `docs/detection_rules.md` — full rule table in [DEF.md § Phase 3](Documentation/DEF.md#the-7-rules); `docs/architecture.md` links to it rather than duplicating

**Definition of Done:** All 7 rules run against the Phase 2 synthetic datasets and produce correctly-labeled alerts with documented false-positive/false-negative behavior on the test fixtures. — met; verified via `uv run python -m app.detection.cli` against every real dataset (12 alerts across all 7 rule types, zero false positives on any benign file) and against a live Postgres container.

---

## Phase 4: IOC Extraction

**Goal:** Pull structured indicators out of events/alerts, validated deterministically, with LLM assistance as a supplement — not a replacement.

**Tasks**

- [x] Implement deterministic extractor: IPv4 addresses (regex + validation, reject private/reserved ranges where relevant to context) — `backend/app/ioc/ipv4.py`; private/reserved rejected from free-text scans only, kept for structured fields (needed for Phase 5 correlation) — see [DEF.md § Phase 4](Documentation/DEF.md#regex-extractors-the-scan-strategy)
- [x] Implement deterministic extractor: IPv6 addresses — `backend/app/ioc/ipv6.py`, same private/reserved policy
- [x] Implement deterministic extractor: domains (regex + basic TLD/format validation) — `backend/app/ioc/domain.py`; excludes RFC 2606/6762 reserved TLDs and a file-extension denylist (fixed a real false-positive bug caught during verification — see PHASE-4.md)
- [x] Implement deterministic extractor: URLs — `backend/app/ioc/url.py`
- [x] Implement deterministic extractor: file hashes (MD5/SHA1/SHA256, validated by length/charset) — `backend/app/ioc/file_hash.py`, classified by matched length
- [x] Implement deterministic extractor: email addresses — `backend/app/ioc/email.py`
- [x] Implement deterministic extractor: usernames (context-aware — only from fields known to carry them, to avoid false positives) — `backend/app/ioc/username.py`; field-only, never regex-scanned from free text
- [x] Deduplicate and upsert IOCs against the `IOC` table, tracking first_seen/last_seen and source references — `backend/app/ioc/service.py` (`upsert_ioc`, `link_event`), `pipeline.py`'s pass 2 additionally rolls matched-event IOCs up onto `alert_ioc`
- [ ] `[STRETCH]` Add LLM-assisted extraction as a secondary pass over free-text fields (e.g., log messages) that the regex layer can't parse, with output validated against the same deterministic validators before being trusted — not implemented this pass
- [x] Clearly tag each stored IOC with its extraction source (`regex` vs `llm_assisted`) — every row this phase produces is `regex`; `llm_assisted` stays reserved for the unimplemented stretch goal
- [x] Write extraction accuracy tests against a labeled fixture set (known IOCs embedded in synthetic text) — 25 extractor-level unit tests plus integration tests reaching all 9 `IOCType` values through the real pipeline against real datasets, with dedicated benign-data false-positive checks

**Definition of Done:** All 7 IOC types are deterministically extracted and validated with measured precision/recall against a labeled fixture set. If implemented, LLM-assisted extraction never bypasses deterministic validation. — met (LLM-assisted extraction not implemented, so the second clause is vacuously satisfied); verified via `uv run python -m app.ioc.cli` against every real dataset (all 9 `IOCType` values populated, zero false positives on benign fixtures) and against a live Postgres container.

---

## Phase 5: Incident Correlation

**Goal:** Group related alerts into incidents using explainable, deterministic correlation logic.

**Tasks**

- [x] Design and document the correlation strategy in `docs/correlation_strategy.md` before implementing (see [[correlation-strategy]] open question below) — documented in [DEF.md § Phase 5](Documentation/DEF.md#phase-5-incident-correlation) instead of a separate file, per the project's established pattern (see the resolved `[[correlation-strategy]]` entry below); `docs/architecture.md` links to it
- [x] Implement time-window-based correlation (alerts within a configurable rolling window are candidates for grouping) — `backend/app/correlation/scoring.py`, decaying time score + a DB-level candidate window filter
- [x] Implement shared-IP correlation — subsumed by shared-IOC correlation below (IPv4/IPv6 are `IOCType` values)
- [x] Implement shared-user correlation — subsumed by shared-IOC correlation below (`username` is an `IOCType` value)
- [x] Implement shared-host correlation — new `Entity`/`EventEntity`/`AlertEntity` host population this phase, `backend/app/correlation/{host_extraction,host_identity,entity_service}.py`, including the `[[host-identity-stub]]` hostname↔IP bridge
- [x] Implement shared-domain correlation — subsumed by shared-IOC correlation below (`domain` is an `IOCType` value)
- [x] Implement shared-IOC correlation (generalizes the above via the `IOC` table) — reads `Alert.iocs` (Phase 4), one mechanism covering ip/user/domain/url/hash/email uniformly
- [x] Implement shared-MITRE-technique correlation (alerts mapped to the same/related techniques within a window) — real, tested code path (`Alert.mitre_mappings`); live since Phase 8 populated technique mappings (see `test_shared_technique_produces_nonzero_mitre_score` in `backend/tests/unit/test_mitre_pipeline.py`)
- [x] Combine correlation signals into a single scoring function that decides whether alerts join an existing incident, start a new one, or stay uncorrelated — weighted scoring (not graph clustering), `backend/app/correlation/scoring.py`; formula and weights in [DEF.md § Phase 5](Documentation/DEF.md#scoring-formula)
- [x] Persist incident-to-alert relationships and maintain incident-level rollup fields (severity, status, first/last activity) — `backend/app/correlation/pipeline.py`; severity=max, activity range=min/max, deterministic title generation (`title.py`)
- [x] `[HIGH VALUE]` Validate correlation against the multi-stage synthetic attack scenario (Phase 2) — confirm the pipeline reconstructs it as a single incident, not scattered alerts — confirmed: all 4 scenario alerts land in one incident titled `"SSH Brute Force → Suspicious Authentication Pattern → Port Scanning → Suspicious PowerShell Activity"`, verified against both SQLite and Postgres
- [x] Write correlation unit/integration tests covering merge, split, and no-match cases — 30 new tests: scoring, host extraction, entity service, title generation, pipeline (merge/split/closed-incident/re-run), CLI, and integration tests against the real scenario + a genuine near-miss case (same target host as the scenario, ~2.7 hours later, correctly stays separate)

**Definition of Done:** Alerts from the multi-stage attack scenario correlate into one incident with a documented, explainable strategy; unrelated alerts remain separate. Strategy and scoring are documented in `docs/correlation_strategy.md`. — met; strategy documented in DEF.md § Phase 5 (see note above); verified via `uv run python -m app.correlation.cli` against every real dataset and against a live Postgres container.

---

## Phase 6: Local LLM Integration

**Goal:** A clean provider abstraction so the AI layer is swappable, testable without Ollama running, and never a single point of failure for the system.

**Tasks**

- [x] `[HIGH VALUE]` Design `LLMProvider` interface (e.g., `generate(prompt, schema, config) -> AnalysisResult`) — see [[llm-provider-abstraction]]; `backend/app/llm/base.py` (`LLMProvider.generate`); see [DEF.md § Phase 6, "Interface: template method, not duplicated retry logic"](Documentation/DEF.md#interface-template-method-not-duplicated-retry-logic)
- [x] Implement `OllamaProvider` (HTTP client against local Ollama instance) — `backend/app/llm/ollama_provider.py`
- [x] Implement `MockProvider` returning deterministic canned/templated responses — used in tests and when Ollama is unavailable, so the app degrades gracefully rather than failing — `backend/app/llm/mock_provider.py`
- [x] Define structured output contracts (JSON schemas) per LLM task instead of relying on free-form text — enforce via Ollama's JSON mode/grammar or explicit parsing + validation — `backend/app/llm/validation.py` (`validate_structured_output`, Pydantic `model_validate_json`) and `OllamaProvider`'s `"format": "json"`; per-task schemas themselves are Phase 7's job, Phase 6 proves the mechanism with an illustrative schema
- [x] Implement prompt versioning (prompts stored as versioned templates, version recorded on every `AnalysisResult`) — `LLMRequest.prompt_version`/`LLMResponse.prompt_version` in `backend/app/llm/types.py`; deliberately a plain string tag rather than a templating engine, since there are no real prompts yet to template (see [DEF.md § Phase 6](Documentation/DEF.md))
- [x] Implement model configuration (model name, temperature, max tokens, etc. sourced from config, not hardcoded) — `backend/app/llm/registry.py` (`default_llm_config`), all fields read from `Settings` in `backend/app/core/config.py`
- [x] Implement timeout handling for provider calls — `LLMTimeoutError` in `backend/app/llm/exceptions.py`, raised by `OllamaProvider._complete`, handled in `LLMProvider.generate`
- [x] Implement retry behavior (bounded retries with backoff on transient failures) — `LLMProvider.generate`'s retry loop in `backend/app/llm/base.py`
- [x] Implement response validation (parse + validate against the expected schema; reject/flag malformed output rather than trusting it blindly) — `backend/app/llm/validation.py`
- [x] Implement failure handling: on provider failure/timeout/invalid response, the system continues operating on deterministic results alone and clearly marks AI analysis as unavailable — `LLMProvider.generate` never raises, always returns an `LLMResponse` with `validation_status` reflecting the failure (`backend/app/llm/base.py`); wiring this into a pipeline step that runs alongside deterministic results is Phase 7's job
- [x] Log model metadata per call: provider, model name, prompt version, latency, token counts if available, success/failure — structured `logger.warning`/`logger.info` calls in `backend/app/llm/base.py`
- [x] Document recommended local model(s) and rationale (see [[recommended-local-model]] open question) — [DEF.md § Phase 6, "Recommended local model"](Documentation/DEF.md)
- [x] Write provider tests using `MockProvider` (no live Ollama dependency in CI) — `backend/tests/unit/test_llm_{validation,mock_provider,generate,ollama_provider,registry,cli}.py`
- [x] `[STRETCH]` Write opportunistic integration tests that run only when a real Ollama instance is detected — `backend/tests/integration/test_llm_ollama_live.py`

**Definition of Done:** The app runs fully (ingestion → detection → correlation → API → frontend) with `MockProvider` and zero network calls. Swapping to `OllamaProvider` via config requires no code changes elsewhere. Every `AnalysisResult` records provider, model, prompt version, and latency. Confirmed — see [DEF.md § Phase 6 Status](Documentation/DEF.md) and [PHASE-6.md](Documentation/PHASE-6.md).

---

## Phase 7: AI-Powered Triage

**Goal:** Use the LLM for reasoning/summarization tasks that deterministic code can't do well — always clearly labeled as AI-generated and layered on top of, never replacing, deterministic output.

**Tasks**

- [x] Implement incident summarization (structured prompt over an incident's alerts/events/IOCs → human-readable summary) — `IncidentSummaryOutput`, `build_incident_summary_prompt` in `backend/app/triage/schemas.py`/`prompts.py`; see [DEF.md § Phase 7](Documentation/DEF.md#phase-7-ai-powered-triage)
- [x] Implement severity *explanation* (LLM explains the deterministic severity score in natural language; it does not compute the score) — `SeverityExplanationOutput`/`build_severity_explanation_prompt`, which hands the deterministic severity/`severity_factors` to the model as given fact and explicitly instructs it not to recompute
- [x] Implement attack classification (LLM suggests an attack category/kill-chain stage as a labeled hypothesis, not a ground-truth verdict) — `AttackClassificationOutput`/`build_attack_classification_prompt`
- [x] Implement investigation hypothesis generation (plausible explanations for the observed activity) — `InvestigationHypothesisOutput`/`build_investigation_hypothesis_prompt`
- [x] Implement recommended investigation steps (distinct from Phase-9 rule-based recommendations — LLM-generated, contextual) — `InvestigationStepsOutput`/`build_investigation_steps_prompt`; each validated step is persisted as a `Recommendation(source=llm)` row in `app/triage/pipeline.py::_apply_investigation_steps`
- [x] Implement MITRE ATT&CK technique suggestions from the LLM, cross-checked against the deterministic mapping in Phase 8 (flag disagreements rather than silently trusting either source) — `MitreSuggestionOutput`/`build_mitre_suggestion_prompt`; suggestions matching a locally-known `MITRETechnique` become `AlertMitreMapping(source=llm)` rows alongside any `source=rule` ones, so agreement/disagreement is computable directly from the data (no separate flag needed); inert (zero mapping rows) until Phase 8 vendors real MITRE data — see [DEF.md § Phase 7, "MITRE cross-check"](Documentation/DEF.md#phase-7-ai-powered-triage)
- [x] `[HIGH VALUE]` Enforce UI/API-level separation: every AI-generated field is wrapped in an `AnalysisResult`-linked structure and visually/structurally distinct from deterministic `Alert`/`Detection`/`Incident` fields — structurally satisfied (`AnalysisResult` is its own table; `Recommendation`/`AlertMitreMapping` carry a `source` column); the *visual* half is Phase 10's job, since no dashboard incident view exists yet
- [x] Orchestrate the above as a `triage` pipeline step that runs after correlation, is idempotent/re-runnable, and stores results linked to the triggering incident — `run_triage()` in `backend/app/triage/pipeline.py`, `backend/app/triage/cli.py`
- [x] Write tests validating that structured LLM output is correctly parsed, validated, and rejected/flagged when malformed (using `MockProvider` with both valid and deliberately malformed fixtures) — `backend/tests/unit/test_triage_{context,prompts,pipeline,cli}.py` (19 cases)

**Definition of Done:** Every incident in the dashboard can show an AI analysis panel populated end-to-end via `MockProvider` (and, when available, `OllamaProvider`), with every AI claim traceable to an `AnalysisResult` row and visually distinguished from deterministic findings. Confirmed end-to-end via `MockProvider` against both SQLite and a live Postgres container — see [DEF.md § Phase 7 Status](Documentation/DEF.md#phase-7-status-implemented) and [PHASE-7.md](Documentation/PHASE-7.md). No dashboard UI panel yet (Phase 10); every AI claim is traceable to a persisted `AnalysisResult` row today.

---

## Phase 8: MITRE ATT&CK Integration

**Goal:** Ground the system in a recognized security framework using local data — no runtime dependency on an external API.

**Tasks**

- [x] Source and vendor a local subset of MITRE ATT&CK data (see [[mitre-data-source]] open question — resolved) into `data/mitre/` — `data/mitre/techniques.json`, 6 techniques curated to match the 7 existing detection rules; see [DEF.md § Phase 8](Documentation/DEF.md#phase-8-mitre-attck-integration)
- [x] Build a loader that populates the `MITRETechnique` table from the local dataset — `load_techniques()` in `backend/app/mitre/loader.py`, idempotent upsert by `technique_id`
- [x] Implement deterministic mapping: detection rules declare their associated technique(s) at definition time (e.g., SSH brute force → T1110.001) — `DetectionRule.mitre_technique_ids` ClassVar (`backend/app/detection/base.py`), set on all 7 rule classes; synced onto `Detection`/`Alert` rows by `run_mitre_mapping()` in `backend/app/mitre/pipeline.py`
- [x] Implement incident-level technique rollup (union of techniques from all constituent alerts) — `incident_technique_rollup()` in `backend/app/mitre/rollup.py`; also switches on Phase 5's `IncidentSignature`/`score_alert_against_incident` MITRE-agreement scoring, dormant since Phase 5 for lack of data (see `test_shared_technique_produces_nonzero_mitre_score`)
- [x] Support the LLM-suggested techniques from Phase 7 as a separate, labeled source alongside deterministic mappings — already written in Phase 7 (`AlertMitreMapping(source='llm')`); `incident_technique_rollup()` surfaces both `source='rule'` and `source='llm'` rows per technique via its `sources` set
- [x] Design the technique display model: technique ID, name, tactic, evidence (which alert/event triggered it), confidence, and source (`rule` vs `llm`) — `IncidentTechniqueEntry`/`TechniqueEvidence` dataclasses in `backend/app/mitre/rollup.py`
- [x] Write tests confirming every detection rule maps to at least one valid, existing technique ID — `backend/tests/unit/test_mitre_rule_mapping.py`
- [x] `[STRETCH]` Add tactic-level rollup/visualization data (group techniques by tactic for the ATT&CK matrix view in Phase 10) — `techniques_by_tactic()` in `backend/app/mitre/rollup.py`

**Definition of Done:** Every rule-based detection carries a deterministic MITRE mapping sourced from local data; the app has zero runtime network dependency on attack.mitre.org or any ATT&CK API. Confirmed against both SQLite and a live Postgres container — see [DEF.md § Phase 8 Status](Documentation/DEF.md#phase-8-status-implemented) and [PHASE-8.md](Documentation/PHASE-8.md).

---

## Phase 9: REST API

**Goal:** A well-documented, consistent API surface over every domain object, ready for the frontend and for external tooling.

**Tasks**

- [x] Design REST endpoints for `SecurityEvent` (list/filter/get) — `GET /api/v1/events`, `GET /api/v1/events/{id}` in `backend/app/api/events.py`; see [DEF.md § Phase 9](Documentation/DEF.md#phase-9-rest-api)
- [x] Design REST endpoints for `Alert` (list/filter/get, filter by severity/rule/status) — `backend/app/api/alerts.py`, plus `GET /alerts/{id}/mitre-techniques`
- [x] Design REST endpoints for `Incident` (list/filter/get, including nested alerts/IOCs/AI analyses) — `backend/app/api/incidents.py`; `GET /incidents/{id}` returns `IncidentDetail` with nested `alerts`/`iocs`/`analysis_results`/`recommendations`/`mitre_techniques`
- [x] Design REST endpoints for `IOC` (list/filter/get, filter by type/confidence) — `backend/app/api/iocs.py`
- [x] Design REST endpoints for `Detection` (list rule definitions and their metadata) — `backend/app/api/detections.py`, `GET /detections/{id}` returns `DetectionDetail` with nested `mitre_techniques`
- [x] Design REST endpoints for AI analyses (`AnalysisResult`, scoped to an incident/alert) — `backend/app/api/analysis_results.py`; exactly one of `incident_id`/`alert_id` required, enforced as a 422
- [x] Design REST endpoints for `Recommendation` — `backend/app/api/recommendations.py`
- [x] Design REST endpoints for `MITRETechnique` (list/get, plus incident/alert technique rollups) — `backend/app/api/mitre.py`; rollups live on `GET /incidents/{id}/mitre-techniques` and `GET /alerts/{id}/mitre-techniques`, reusing Phase 8's `incident_technique_rollup()`
- [x] Implement pagination (cursor or offset-based, consistent across list endpoints) — offset-based, `Page[T]` envelope in `backend/app/schemas/pagination.py` (see DEF.md for why offset over cursor)
- [x] Implement filtering (query params per resource, validated) — see the filter table in [DEF.md § Phase 9](Documentation/DEF.md#phase-9-rest-api)
- [x] Implement sorting (whitelisted sortable fields per resource) — `apply_sort()` in `backend/app/api/deps.py`, per-resource whitelist dicts, `Severity`/enum fields deliberately excluded (see DEF.md)
- [x] Implement request validation via Pydantic schemas with clear 4xx error responses — FastAPI's own query/path param typing (enums, UUIDs, bounded ints) plus `InvalidQueryParameterError` for cross-field checks
- [x] Implement consistent error handling (structured error envelope, mapped exception handlers) — `backend/app/core/exceptions.py`, handlers in `backend/app/main.py`, one `{"error": {...}}` shape for both custom and FastAPI-native validation failures
- [x] `[HIGH VALUE]` Ensure full OpenAPI/Swagger docs are auto-generated and accurate (FastAPI default) — polish descriptions/examples since this is a resume artifact reviewers may actually open — `openapi_tags` + per-endpoint docstrings in `backend/app/main.py`; `/docs`/`/redoc` confirmed rendering against the live stack
- [x] Add an endpoint to trigger/re-run the pipeline (ingest → detect → correlate → triage) for demo purposes — `POST /api/v1/pipeline/run` in `backend/app/api/pipeline.py`; does not re-run ingestion itself (the existing `POST /events/{source_type}` already covers that) — see DEF.md for why
- [x] Write API tests (status codes, pagination, filtering, error cases) per resource — `backend/tests/integration/test_{events,alerts,incidents,iocs,detections,analysis_results,recommendations,mitre,pipeline}_api.py` (51 cases)

**Definition of Done:** All domain objects are exposed via a consistent, paginated, filterable, sortable REST API with auto-generated OpenAPI docs and passing API tests. Confirmed against both SQLite integration tests and the live docker-compose Postgres stack — see [DEF.md § Phase 9 Status](Documentation/DEF.md#phase-9-status-implemented) and [PHASE-9.md](Documentation/PHASE-9.md). As a consequence, Phase 3/4/5/7/8's dashboard entries switched from static "Implemented" to live-checked "Working," honoring the promise each of their own completion reports made.

---

## Phase 10: Frontend

**Goal:** A dense, usable SOC-style dashboard — the primary visual artifact for demos and interviews.

**Tasks**

- [x] Set up typed API client (generated from OpenAPI schema or hand-written typed fetch layer) — hand-written: `frontend/src/api/types.ts` (mirrored schemas) + `frontend/src/api/resources.ts` (one function per endpoint); see [DEF.md § Phase 10](Documentation/DEF.md#phase-10-frontend) for why hand-written over generated
- [x] Build overview dashboard (counts by severity, recent incidents, alert volume over time) — `frontend/src/pages/OverviewPage.tsx`
- [x] Build alert list view (filterable/sortable table, severity indicators) — `frontend/src/pages/AlertsPage.tsx`
- [x] Build incident list view (status, severity, alert count, last activity) — `frontend/src/pages/IncidentsPage.tsx`; `alert_count` added to `IncidentRead` this phase (Phase 9 amendment, see DEF.md)
- [x] Build incident detail page (constituent alerts, IOCs, entities, MITRE techniques, AI analysis panel, recommendations) — `frontend/src/pages/IncidentDetailPage.tsx`; `entities` added to `IncidentDetail` this phase
- [x] Build IOC explorer (searchable/filterable, links back to source alerts/events) — `frontend/src/pages/IocsPage.tsx`; `search` param + `alert_ids`/`event_ids` added to the IOC endpoints this phase
- [x] Build detection page (list of rule definitions, their descriptions, and recent firings) — `frontend/src/pages/DetectionsPage.tsx` (expand a rule to see its recent alerts)
- [x] Build MITRE ATT&CK visualization (matrix-style view highlighting techniques observed in the environment) — `frontend/src/pages/MitrePage.tsx`, grouped by tactic; renders the local technique library, not a live cross-incident "observed" aggregate (no such endpoint exists — see DEF.md § Phase 10 for why that wasn't built speculatively)
- [x] `[HIGH VALUE]` Build the AI analysis panel with unmistakable visual separation from deterministic content (distinct styling, "AI-generated" labeling, confidence/model metadata shown) — `<AiBadge />` + `.ai-panel` styling in `frontend/src/styles/dashboard.css`, used identically in the incident AI panel, LLM-sourced recommendations, and LLM-sourced MITRE evidence
- [x] Build incident timeline (chronological view of events/alerts within an incident) — timeline section on `IncidentDetailPage.tsx`, alerts sorted by `first_event_at`
- [x] Implement loading/empty/error states across all views — `frontend/src/components/ui/QueryState.tsx` (`LoadingState`/`EmptyState`/`ErrorState`), used by every page via the shared `useApiQuery` hook
- [x] Apply consistent design system/theming (component library or hand-rolled, dark-mode-friendly SOC aesthetic) `[STRETCH]` — hand-rolled, extends the existing dark/monospace palette from the status page (`index.css`'s new severity/AI-attribution tokens, `styles/dashboard.css`)
- [x] Add basic frontend tests for key components `[STRETCH]` — Vitest + Testing Library; `frontend/src/lib/aggregate.test.ts`, `frontend/src/components/ui/{Badges,Pagination}.test.tsx` (11 cases)

**Definition of Done:** A reviewer can open the dashboard, browse incidents end-to-end from overview → incident detail → AI analysis → MITRE mapping, with no dead ends or unhandled empty states. Confirmed against the live docker-compose stack with real pipeline-generated data — see [DEF.md § Phase 10 Status](Documentation/DEF.md#phase-10-status-implemented) and [PHASE-10.md](Documentation/PHASE-10.md). The old build-status page moved to `/status` rather than being replaced.

---

## Phase 11: Testing

**Goal:** Confidence that the pipeline is correct and stays correct — this is what separates a portfolio project from a toy demo.

**Tasks**

- [x] Unit tests for normalization, IOC extraction, detection rules, correlation logic (largely produced incrementally in earlier phases — this phase closes gaps and raises coverage) — measured coverage first (98% at phase start), closed the specific gaps it found (IOC extractor false-positive/malformed branches, correlation scoring/title/host-extraction branches); see [DEF.md § Phase 11](Documentation/DEF.md#phase-11-testing)
- [x] Integration tests exercising the full pipeline (ingest → normalize → detect → extract IOCs → correlate → triage) against synthetic datasets — `backend/tests/integration/test_full_pipeline_against_datasets.py`, the first test to run the complete chain (prior dataset tests stopped at correlation)
- [x] API tests for every resource and error path — closed several filters/branches that were documented but never actually called by a passing test (`Alert.status`, `SecurityEvent.since`/`until`, `IOC.validation_status`, `Recommendation.alert_id`/`source`, `AnalysisResult`'s `alert_id` scope, `GET /alerts/{id}/mitre-techniques`'s own 404)
- [x] Database tests (migrations apply cleanly on both Postgres and SQLite; constraints enforced) — migrations already CI-verified on both (Phase 0); constraints already thoroughly tested (Phase 1's `test_models.py`) and now also verified for real against live Postgres via the new dual-dialect fixture (see the `[[postgres-vs-sqlite]]` resolution below)
- [x] Detection rule tests with labeled true/false-positive fixtures (already started in Phase 3 — consolidate here) — consolidated the one real duplication found (`brute_force_events` fixture, previously copied across 3 files)
- [x] IOC extraction accuracy tests (already started in Phase 4 — consolidate here) — every extractor now matches `TestIPv4`'s full pattern (public match, filtered match, dedup, malformed rejection); `ipv6.py` went from 79% to 100%
- [x] Incident correlation accuracy tests (already started in Phase 5 — consolidate here) — closed the "alert before incident window" and "no activity window yet" scoring branches, and the entity-link-vs-IOC title-generation fallback
- [x] LLM response validation tests: valid structured output, malformed output, timeout, provider failure — all via `MockProvider` — already comprehensive since Phase 6/7; this phase added the pipeline-level (not just provider-level) failure-injection test, see below
- [x] Failure-case tests across the stack (bad input, DB unavailable, LLM unavailable) confirming graceful degradation, not crashes — bad input already covered (Phase 2/9); DB unavailable closed via `test_health_api.py` (the one line of `app/api/health.py` that had never run under test); LLM unavailable closed via `TestLLMUnavailableDegradesGracefully` in `test_triage_pipeline.py`, proving the incident's deterministic data is untouched when the LLM is down, not just that `generate()` doesn't raise
- [x] `[HIGH VALUE]` Track and report test coverage in CI; set a minimum threshold — `--cov-fail-under=95` (actual: 99.06%) plus a GitHub Actions step-summary table and an uploaded XML artifact, in `.github/workflows/ci.yml`'s `backend-test` job
- [x] Create reusable synthetic fixtures shared across unit/integration/API tests (avoid duplicated ad-hoc data) — `brute_force_events`/`BRUTE_FORCE_NOW` in `backend/tests/conftest.py`; Phase 9's `seed_full_incident()` was already the API-layer equivalent

**Definition of Done:** CI runs the full test suite (unit + integration + API + DB) on every PR with a published coverage number; all failure-injection tests pass (system degrades gracefully rather than crashing). Confirmed — see [DEF.md § Phase 11 Status](Documentation/DEF.md#phase-11-status-implemented) and [PHASE-11.md](Documentation/PHASE-11.md). One thing beyond the original DoD: the suite now runs against both SQLite and a real Postgres instance on every CI run (`[[postgres-vs-sqlite]]`, resolved below), not just SQLite.

---

## Phase 12: Performance and Evaluation

**Goal:** Turn the project into something with measured, defensible numbers — critical for resume credibility.

**Tasks**

- [x] Define and implement a benchmark harness for events processed per second (ingestion + normalization throughput) — `backend/app/benchmark/harness.py`, ~27.7k events/sec; see [DEF.md § Phase 12 Status](Documentation/DEF.md#phase-12-status-implemented) and [docs/benchmarks.md](docs/benchmarks.md)
- [x] Measure detection latency (event ingested → alert produced) — reported as batch throughput, not per-event latency (the pipelines are batch jobs, not a streaming service — stated explicitly in `docs/benchmarks.md`): ~18.4k events/sec
- [x] Measure incident correlation latency (alert produced → incident updated) — same batch-throughput framing: ~432 alerts/sec
- [x] Measure API latency (p50/p95/p99 per endpoint under load) — `GET /incidents`, `GET /alerts`, `GET /iocs`, real `TestClient` requests, see `docs/benchmarks.md`
- [x] Measure database query performance for common access patterns (incident list, IOC search) — same three endpoints above double as this measurement rather than a redundant separate benchmark (documented rationale in `docs/benchmarks.md`)
- [x] Measure LLM response latency per triage task type — real per-task latency (533–3906ms) from a live opportunistic Ollama run, reused from the AI-grounding check rather than re-measured under Mock (Mock's sub-ms in-process timing is explicitly labeled orchestration overhead, not LLM latency)
- [x] Capture LLM token usage where the provider exposes it — prompt/completion token counts captured from the same live Ollama run (~1200–1251 prompt, 58–317 completion tokens per task)
- [x] `[HIGH VALUE]` Build a labeled evaluation dataset (`data/eval/`) with known ground-truth alerts/incidents distinct from the dev/demo synthetic data (avoid evaluating on data the rules were tuned against) — `backend/app/evaluation/generate_dataset.py`, 33 detection + 12 IOC + 2 correlation cases, distinct epoch/hosts/IPs/usernames from `data/synthetic_events/`
- [x] Compute and report detection precision/recall against the evaluation dataset — 1.0/1.0 overall and per rule; see [docs/evaluation_methodology.md](docs/evaluation_methodology.md)
- [x] Compute and report IOC extraction precision/recall against the evaluation dataset — 1.0/1.0 overall and per `IOCType`; per-case attribution design, not a global set comparison (see methodology doc for why)
- [x] Compute and report incident correlation accuracy (correct grouping rate) against the evaluation dataset — 2/2 (1.0)
- [x] Document evaluation methodology in `docs/evaluation_methodology.md` (dataset construction, ground-truth labeling process, metric definitions) — includes the three dataset bugs found and fixed, the IOC-scoring redesign, and the live AI-grounding results (0% grounding rate, one hallucinated classification)
- [x] Publish a benchmarks summary (table or short report) suitable for linking from the resume/README — [docs/benchmarks.md](docs/benchmarks.md)

**Definition of Done:** A documented, reproducible evaluation run produces concrete precision/recall/throughput/latency numbers against a held-out labeled dataset, written up in `docs/evaluation_methodology.md`. Confirmed — see [DEF.md § Phase 12 Status](Documentation/DEF.md#phase-12-status-implemented) and [PHASE-12.md](Documentation/PHASE-12.md).

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

- **`[[postgres-vs-sqlite]]` PostgreSQL vs SQLite for local development — resolved (Phase 11).** Both, every CI run, not periodic/optional: SQLite stays the primary, fast gate (`backend-test`, coverage-enforced); a second `backend-test-postgres` job runs the same test suite against a real ephemeral Postgres container via a `TEST_POSTGRES_URL`-gated fixture (`tests/conftest.py`), each test isolated in a rolled-back transaction. Chosen over "periodic/optional" because SQLite has already let a real bug through once — Phase 7's over-length `prompt_version` — that only a live Postgres run caught; making it optional would make that class of bug optional to catch, too. See [DEF.md § Phase 11](Documentation/DEF.md#phase-11-testing).
- **`[[recommended-local-model]]` Recommended local model.** Needs a concrete choice (e.g., a Llama 3.x or Qwen2.5 instruct variant in the 7–8B range) balancing: runs on typical dev hardware, supports structured/JSON output well, reasonable latency for demo purposes. Should be pinned in `.env.example` with a documented fallback smaller model for constrained hardware.
- **Orchestration: hand-rolled vs LangChain/LangGraph.** Leaning toward implementing the `LLMProvider` abstraction and triage pipeline ourselves — the project brief explicitly favors this, and it's a stronger engineering signal than wrapping a framework. Revisit only if a specific need (e.g., complex multi-step agent loops) can't be reasonably hand-rolled.
- **`[[event-schema-design]]` Event schema design specifics.** The high-level `SecurityEvent` shape is sketched in Phase 1/2, but exact field-level design (how much source-specific detail lives in a `raw` JSON blob vs. promoted normalized columns) needs to be finalized once real sample data from all 5 source types is in hand.
- **`[[correlation-strategy]]` Incident correlation strategy specifics — resolved.** Weighted scoring (not graph-based clustering), chosen for explainability and consistency with Phase 3's severity-scoring precedent. Full formula, weights, and the chronological single-pass grouping algorithm are documented in [DEF.md § Phase 5](Documentation/DEF.md#scoring-formula) — written there rather than a separate `docs/correlation_strategy.md`, matching the project's established pattern of keeping all phase definitions in one running document instead of scattering them.
- **`[[host-identity-stub]]` Hostname ↔ IP identity resolution.** Phase 5's `KNOWN_HOST_ALIASES` is a small, hardcoded map covering only the two hosts (`web01.internal` ↔ `10.0.0.5`, `ws-07.internal` ↔ `10.0.0.7`) this project's own scenario dataset deliberately ties together — a deliberate stub standing in for a real CMDB/asset-inventory integration, in the same spirit as Phase 3's `StaticGeoIPResolver`. Needs a decision: extend the map manually as new scenarios are added, or build a real (still-local, no paid API) asset-inventory mechanism once enough scenarios exist to justify it.
- **`[[mitre-data-source]]` MITRE ATT&CK data source — resolved.** A curated subset matching implemented detection rules, not a full Enterprise-matrix snapshot: 6 techniques covering all 7 detection rules, hand-picked and hand-written (not a re-vendored upstream STIX/JSON snapshot), checked in at `data/mitre/techniques.json`. Refresh process is manual — add an entry and re-run `app.mitre.cli` whenever a new rule needs a technique not yet vendored; no periodic re-vendoring job. See [DEF.md § Phase 8](Documentation/DEF.md#phase-8-mitre-attck-integration).
- **How AI confidence should be represented — resolved.** Derived, never self-reported: `AnalysisResult.confidence` starts at `1.0` for a response validated on the first attempt, drops `0.15` per retry consumed, floors at `0.5`, and is `null` for any response that never validates — see [DEF.md § Phase 6, "Confidence, derived not self-reported"](Documentation/DEF.md#confidence-derived-not-self-reported). Phase 7 uses this formula unmodified for all six triage tasks; a further refinement (factoring in agreement with deterministic signals, e.g. for `mitre_suggestion`) is deliberately deferred until Phase 8 gives that comparison something real to check against — see [DEF.md § Phase 7](Documentation/DEF.md#phase-7-ai-powered-triage).
- **How to evaluate AI-generated triage — resolved (Phase 12).** Automated grounding checks, not manual rubric scoring: no human rater exists in this project's actual (agentic) workflow, so 1–5 scoring was never really an option. `app/evaluation/ai_grounding.py` checks whether `incident_summary`/`investigation_hypothesis` text mentions a real entity/IOC identifier from the incident, and whether `mitre_suggestion`'s techniques overlap with Phase 8's deterministic rule-mapped techniques. Run for real against a live Ollama model (`qwen2.5:0.5b`) — result: 0% grounding rate, one hallucinated attack-category classification, 100% MITRE overlap. See [DEF.md § Phase 12](Documentation/DEF.md#phase-12-performance-and-evaluation) and [docs/evaluation_methodology.md](docs/evaluation_methodology.md).
- **Authentication approach for the dashboard/API (Phase 14).** Needs a decision on scope — single shared local credential vs. simple user accounts — appropriate for a local-first demo project without over-engineering.
- **`[[geoip-resolver-stub]]` Real GeoIP data source for `impossible_travel`.** Phase 3's `StaticGeoIPResolver` is a small hardcoded table covering only the IPs used in this project's own synthetic datasets — a deliberate stub, not a real geolocation capability, chosen specifically to avoid a paid/rate-limited external API. Needs a decision: bundle a free offline dataset (e.g., a trimmed MaxMind GeoLite2 snapshot) behind the same `GeoIPResolver` interface, or leave the stub in place and document the rule as demo-only until then.
- **`[[detection-run-idempotency]]` Idempotent detection re-runs.** Phase 3's `run_detection()` does not deduplicate — re-running it over an already-processed time range creates duplicate `Alert` rows. Needs a decision on a dedup strategy (e.g., a fingerprint column on `Alert` derived from `detection_id` + sorted matched event IDs) versus relying entirely on callers scoping `since` correctly.

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
