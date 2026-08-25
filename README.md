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

Visit http://localhost:5173. Right now the frontend is a **build status
dashboard**: one row per roadmap phase, each with a live status dot —
gray (not implemented), green (checked against the running backend and
working), or red (expected to work but the backend is unreachable or
unhealthy). Phases 0–2 are checked live via `/healthz` and `/openapi.json`;
phases 3–15 have no built surface yet, so they're shown as not implemented
rather than guessed at. This gets replaced by the real SOC-style dashboard
in Phase 10.

```bash
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
zero LLM network dependency by default), and Phase 7 (AI-powered triage —
six LLM-assisted tasks per incident — summary, severity explanation, attack
classification, investigation hypotheses, investigation steps, MITRE
suggestions — each persisted as a labeled `AnalysisResult`, idempotent and
re-runnable, never merged into deterministic fields), and Phase 8 (MITRE
ATT&CK integration — a curated local technique dataset, deterministic
rule-to-technique mappings declared on each detection rule, and the
incident-level technique rollup that also switches on Phase 5's
correlation MITRE-agreement signal, dormant until now for lack of data).
See [Documentation/](Documentation/) for the detailed report on each
completed phase, and [TODO.md](TODO.md) for the full roadmap and what's
next (Phase 9: REST API).

## License

[MIT](LICENSE)
