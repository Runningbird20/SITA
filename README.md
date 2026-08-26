# SITA — Local Security Incident Triage Agent

A local-first security incident triage platform. It ingests simulated security
events, normalizes them, runs deterministic detection rules, extracts
indicators of compromise, correlates alerts into incidents, maps activity to
MITRE ATT&CK, and layers AI-assisted triage (via a local LLM through
[Ollama](https://ollama.com)) on top of — never in place of — that
deterministic pipeline.

No paid APIs or API keys are required anywhere in this project.

See [TODO.md](TODO.md) for the full engineering roadmap, [Documentation/DEF.md](Documentation/DEF.md)
for the field-level data model and contracts, [docs/architecture.md](docs/architecture.md)
for a system overview, and [Documentation/](Documentation/) for a per-phase
narrative of what was built and why (`PHASE-0.md`, `PHASE-1.md`, ...).

## Stack

| Layer | Choice |
|---|---|
| Backend | Python + FastAPI |
| Database | PostgreSQL (Docker) / SQLite (local dev) |
| Frontend | React + TypeScript + Vite |
| Local LLM | Ollama, behind a swappable `LLMProvider` interface |
| Containerization | Docker / Docker Compose |
| Backend package manager | [uv](https://docs.astral.sh/uv/) |
| Backend lint/format | Ruff |
| Frontend lint/format | ESLint + Prettier |
| Backend tests | pytest |

## Quick Start (Docker)

Requires only Docker.

```bash
cp .env.example .env
docker compose up --build
```

This starts Postgres, Ollama, the FastAPI backend (http://localhost:8000,
docs at `/docs`), and the React frontend (http://localhost:5173).

Apply database migrations (first run only, or after pulling new model changes):

```bash
docker compose exec backend uv run alembic upgrade head
```

Pull a local model for Ollama (first run only):

```bash
docker compose exec ollama ollama pull llama3.1:8b-instruct-q4_K_M
```

Then set `LLM_PROVIDER=ollama` in `.env` and restart the backend service to
enable AI-assisted triage. With `LLM_PROVIDER=mock` (the default), the full
app runs with no LLM dependency at all.

## Local Development (without Docker)

### Backend

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Runs against SQLite by default (`DATABASE_URL` in `.env`/`.env.example`) — no
Postgres required for backend development. Visit http://localhost:8000/docs
for the interactive API docs and http://localhost:8000/healthz for a health
check.

Run tests and lint:

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```

With coverage (CI enforces a 95% minimum; the suite is currently at 99%):

```bash
uv run pytest --cov=app --cov-report=term-missing
```

CI also runs the full suite against a real Postgres instance, not just
SQLite — see [DEF.md § Phase 11](Documentation/DEF.md#phase-11-testing) for
how that's done safely (opt-in only, never against a real database by
accident).

### Loading synthetic security event data

A collection of realistic synthetic events (benign and attack-pattern, per
source type) lives under [data/synthetic_events/](data/synthetic_events/),
including a full multi-stage attack scenario
(`scenarios/brute_force_to_lateral_movement/`) meant to be reconstructed as a
single incident once correlation (Phase 5) exists. Load any file with the
batch-import CLI:

```bash
cd backend
uv run python -m app.ingestion.cli auth ../data/synthetic_events/auth/brute_force.jsonl
```

Or send events individually via `POST /api/v1/events/{source_type}` (accepts
a single event object or a JSON array).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Visit http://localhost:5173 for the real SOC-style dashboard: an overview
(severity counts, recent incidents, alert volume), filterable/sortable
alert and incident lists, an incident detail page (constituent alerts,
IOCs, entities, MITRE techniques, recommendations, and an AI analysis
panel visually distinct from deterministic content), an IOC explorer, a
detections page, and a MITRE ATT&CK technique library — all backed live by
the Phase 9 REST API. A "Run pipeline" button in the nav triggers
`POST /api/v1/pipeline/run` for demos.

The original build-status page — one row per roadmap phase with a live
status dot (gray/not implemented, green/live-checked and working, yellow/
complete but with no live-checkable surface, red/unreachable or failing)
— didn't go away; it moved to http://localhost:5173/status as a standing
diagnostic.

```bash
npm run test
npm run lint
npm run format:check
npm run build
```

## Status

Complete: Phase 0 (project foundation), Phase 1 (core data model — SQLAlchemy
models, Alembic migrations, Postgres/SQLite dual-dialect support), Phase 2
(event ingestion — 5 source-type adapters, batch CLI import, REST ingestion
endpoint, synthetic datasets), Phase 3 (detection engine — 7 deterministic
rules), Phase 4 (IOC extraction — 6 regex extractors + structured fields,
dedup), Phase 5 (incident correlation — weighted scoring across
time/IOC/host/MITRE signals), Phase 6 (local LLM integration — a
swappable `LLMProvider` abstraction with `MockProvider`/`OllamaProvider`,
structured-output validation, retry/confidence handling; the app runs with
zero LLM network dependency by default), Phase 7 (AI-powered triage —
six LLM-assisted tasks per incident — summary, severity explanation, attack
classification, investigation hypotheses, investigation steps, MITRE
suggestions — each persisted as a labeled `AnalysisResult`, idempotent and
re-runnable, never merged into deterministic fields), Phase 8 (MITRE
ATT&CK integration — a curated local technique dataset, deterministic
rule-to-technique mappings declared on each detection rule, and the
incident-level technique rollup that also switches on Phase 5's
correlation MITRE-agreement signal, dormant until now for lack of data),
Phase 9 (REST API — a paginated, filterable, sortable read surface
over every domain object, a structured error envelope, auto-generated
OpenAPI docs, and a pipeline-trigger endpoint for demos; also switches
Phase 3/4/5/7/8's dashboard entries from static "Implemented" to
live-checked "Working," a promise each of those phases' own docs made),
Phase 10 (frontend — a real SOC-style dashboard: overview, alert and
incident lists, an incident detail page with a visually distinct AI
analysis panel, an IOC explorer, a detections page, and a MITRE technique
library, all live against the Phase 9 API; the original build-status page
moved to `/status` rather than being replaced), Phase 11 (testing — an
audited, coverage-enforced suite: 338 backend tests at 99% line coverage
with a 95% CI floor, run against both SQLite and a real Postgres instance
on every CI run, plus failure-injection tests proving the system degrades
gracefully — not crashes — when the database or the LLM is unavailable),
and Phase 12 (performance and evaluation — a generated, held-out dataset
(`data/eval/`) distinct from the dev/demo data, scoring detection
(1.0 precision/recall across all 7 rules), IOC extraction (1.0
precision/recall across all 9 types), and correlation (1.0 accuracy)
against it; automated AI-output grounding checks against a live local
model, honestly reporting a 0% grounding rate and one hallucinated
classification; and real pipeline throughput / API latency benchmarks —
see [docs/evaluation_methodology.md](docs/evaluation_methodology.md) and
[docs/benchmarks.md](docs/benchmarks.md)).
See [Documentation/](Documentation/) for the detailed report on each
completed phase, and [TODO.md](TODO.md) for the full roadmap and what's
next (Phase 13: Observability).

## License

[MIT](LICENSE)
