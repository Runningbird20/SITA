# SITA — Local Security Incident Triage Agent

A local-first security incident triage platform. It ingests simulated security
events, normalizes them, runs deterministic detection rules, extracts
indicators of compromise, correlates alerts into incidents, maps activity to
MITRE ATT&CK, and layers AI-assisted triage (via a local LLM through
[Ollama](https://ollama.com)) on top of — never in place of — that
deterministic pipeline.

No paid APIs or API keys are required anywhere in this project.

See [TODO.md](TODO.md) for the full engineering roadmap, [DEF.md](DEF.md) for
the core data model, and [docs/architecture.md](docs/architecture.md) for a
system overview.

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

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Visit http://localhost:5173.

```bash
npm run lint
npm run format:check
npm run build
```

## Status

Phase 0 (project foundation) and Phase 1 data model definitions are in place.
See [TODO.md](TODO.md) for what's next.

## License

[MIT](LICENSE)
