# Phase 0: Project Foundation — Completion Report

Status: complete. This document explains what was built, how the pieces fit together, and why each decision was made. For the checklist itself, see [TODO.md](../TODO.md#phase-0-project-foundation). For the living architecture reference, see [docs/architecture.md](../docs/architecture.md) — this document is a point-in-time explanation of *how Phase 0 got built*; that one is the evolving summary of *how the system works now*.

## Goal

Phase 0's job was narrow on purpose: produce a skeleton that actually runs — backend, frontend, database, and local LLM runtime, all wired together through Docker Compose — before any real feature logic exists. Nothing in this phase does anything security-related yet. It exists so every later phase has a floor to build on: a place to put code, a way to run it, a way to lint and test it, and a way to prove it works in the same environment a reviewer would use to check it out.

## What was built

### Backend skeleton (`backend/`)

The backend is a Python project managed by [uv](https://docs.astral.sh/uv/), initialized as a flat package (`app/`) rather than uv's default `src/` layout — the `src/` layout is meant for projects that get published as installable packages with public/private import boundaries; SITA is deployed as a running service, not a library, so the extra indirection would have added nothing.

- **`app/main.py`** — the FastAPI application. Uses a `lifespan` context manager (not the deprecated `@app.on_event("startup")` hook) to log a startup message with the active environment and LLM provider.
- **`app/core/config.py`** — a single `Settings` class (`pydantic-settings`) that is the *only* place environment variables are read anywhere in the app. Every setting used by any later phase — database URL, Ollama host, log level, LLM temperature — is declared here and documented in `.env.example`. The rule going forward: if code needs a config value, it goes through `get_settings()`, never `os.environ` directly.
- **`app/core/logging.py`** — configures the root logger once, as structured JSON by default (`python-json-logger`), with a `LOG_FORMAT=console` escape hatch for readable local output. Every later phase should get its logger via `logging.getLogger(__name__)` and inherit this configuration rather than setting up its own handlers.
- **`app/db/session.py`** — the SQLAlchemy engine, `SessionLocal` factory, declarative `Base`, and a `get_db()` FastAPI dependency. This existed in skeletal form in Phase 0 (no tables yet) specifically so the `/healthz` endpoint could prove real database connectivity, not just process liveness.
- **`app/api/health.py`** — `GET /healthz`, returning process status plus a live `SELECT 1` against the configured database. This is deliberately the *only* endpoint in Phase 0; it exists to prove the backend, its config, and its database connection all actually work together, not to be a real feature.
- **`pyproject.toml`** — dependencies (FastAPI, Uvicorn, SQLAlchemy, Alembic, psycopg, pydantic-settings, httpx, python-json-logger) and dev dependencies (pytest, pytest-asyncio, pytest-cov, ruff), plus Ruff and pytest configuration.

**Why uv instead of pip/poetry:** specified in the project's initial tech direction as the preferred modern Python dependency manager — fast, lockfile-based, and it doubles as the task runner (`uv run ...`) so there's no separate virtualenv-activation step to document for a reviewer cloning the repo.

### Frontend skeleton (`frontend/`)

Scaffolded via `npm create vite@latest -- --template react-ts`, which as of the current Vite release defaults to [oxlint](https://oxc.rs/) rather than ESLint. That default was **overridden**: oxlint was removed and replaced with ESLint (flat config, `typescript-eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`) plus Prettier, because the project's stated tooling direction explicitly calls for ESLint/Prettier — a newer default from the scaffolding tool doesn't override an explicit requirement from the project spec.

- **`eslint.config.js`** — flat config, TypeScript-aware, React Hooks rules, wired to defer formatting concerns to Prettier via `eslint-config-prettier` (so the two tools never fight over the same rule).
- **`.prettierrc.json`** / **`.prettierignore`** — formatting rules (100-char width, double quotes off, trailing commas).
- **`package.json` scripts** — `lint` (ESLint), `format` / `format:check` (Prettier), `build`, `dev`, `preview`.

### Docker (`backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`)

**Backend Dockerfile:** built on `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`. Dependencies are installed in a layer *before* application code is copied in (`COPY pyproject.toml uv.lock ./` → `uv sync --no-install-project` → `COPY app ./app` → `uv sync`), so that changing a source file doesn't invalidate the dependency-install cache — only changing `pyproject.toml`/`uv.lock` does. The image runs as a non-root `appuser` (uid 1000). One implementation note worth flagging: this is a single `FROM` stage with two `uv sync` calls for cache efficiency, not a literal multi-stage (`FROM ... AS build` → `FROM ... AS runtime`) build. The original plan called for a true multi-stage build; this achieves the same practical goal (fast rebuilds, no dependency reinstall on code-only changes) with less complexity, at the cost of a slightly larger final image than a true multi-stage build would produce. Worth revisiting if image size becomes a concern.

**A bug that came up during verification and its fix:** the first version of the Dockerfile built `.venv` as root (during the build stage) but ran the container as `appuser`. In the `docker-compose` dev configuration, the backend source directory is bind-mounted for hot-reload, which causes `uv run` to re-resolve the editable install on every container start — and that re-resolution needs write access to `.venv`, which `appuser` didn't have. The container crash-looped with `Permission denied` errors. Fix: `chown -R appuser:appuser /app` before switching to the non-root user. This was caught by actually running the container, not just building it — see Verification below.

**Frontend Dockerfile:** three build targets in one file — `dev` (Vite dev server, used by `docker-compose` for hot-reload), `build` (produces the static bundle), and `production` (nginx serving that static bundle). Only `dev` is wired into `docker-compose.yml` today; `production` exists for when the project needs an actual deployed build, which is out of scope until much later phases.

**`docker-compose.yml`:** four services.

| Service | Image | Purpose |
|---|---|---|
| `postgres` | `postgres:16-alpine` | Primary database for Docker-based dev |
| `ollama` | `ollama/ollama:latest` | Local LLM runtime — no API key, no external network call |
| `backend` | built from `backend/Dockerfile` (`dev` behavior via `--reload`) | FastAPI app |
| `frontend` | built from `frontend/Dockerfile`, `dev` target | Vite dev server |

The backend's `DATABASE_URL` is overridden inside `docker-compose.yml` to point at the `postgres` service by hostname; a developer running the backend natively (no Docker) instead gets a SQLite file from `.env`. This is the practical demonstration of the Phase 1 data-layer abstraction working — same code, same models, two different database backends, decided entirely by which `DATABASE_URL` is active.

**A second bug, found after a user report post-Phase-2 ("the frontend is stuck in a loading loop") and its fix:** every service's `ports:` entry originally published on all interfaces (e.g. `"5173:5173"`), which on macOS is a real problem: `localhost` resolves to `::1` (IPv6) before `127.0.0.1`, and a container process bound only to `0.0.0.0` (IPv4) can end up with Docker Desktop accepting an IPv6-routed connection and never servicing it — the browser hangs indefinitely instead of failing over to IPv4. Fix: every port mapping now binds explicitly to `127.0.0.1` (e.g. `"127.0.0.1:5173:5173"`), so an IPv6 attempt is refused immediately and the browser's IPv4 fallback (Happy Eyeballs) kicks in right away instead of hanging.

In the specific case that prompted this investigation, the actual root cause turned out to be different and more mundane: an unrelated project's Vite dev server, left running (and stopped/suspended — `T` process state) for four days, was squatting on `[::1]:5173` and intercepting the browser's IPv6-first connection attempts before Docker ever saw them. The `127.0.0.1`-binding fix is still correct and worth keeping regardless — it closes off this entire class of "IPv6 hang instead of fast-fail" bug for any future port collision, not just this one — but it's worth recording that the debugging process here involved two layers: a genuine (if latent) networking configuration gap in `docker-compose.yml`, and a separate, unrelated host-machine process conflict that would have caused the identical symptom even with a perfect config. `curl -v` against both `127.0.0.1` and `localhost` (showing which address curl actually resolved to and connected on) was what separated the two.

### Configuration and secrets (`.env.example`, `.gitignore`)

`.env.example` is the single source of truth for every environment variable the project uses — general settings, Postgres credentials, the database URL, every Ollama/LLM setting, and the frontend's API base URL. `.gitignore` excludes `.env` itself (but not `.env.example`), `.venv/`, `node_modules/`, `*.db`, and standard editor/OS noise. Both were checked, not just written — `git status` was used to confirm `.venv`, `node_modules`, and `.env` are actually excluded, not just theoretically covered by a gitignore pattern that might not match.

### CI (`.github/workflows/ci.yml`)

Three jobs, all running on every push/PR to `main`:

1. **`backend-lint`** — `ruff check` and `ruff format --check`.
2. **`backend-test`** — `pytest` with coverage, against SQLite (`LLM_PROVIDER=mock`, so CI never depends on a live Ollama instance or any external network call).
3. **`frontend-lint-build`** — ESLint, Prettier check, and a production build.

This workflow has been written and is believed correct (it mirrors commands verified locally), but has **not yet run for real** — the repository hasn't been pushed to a point where GitHub Actions would trigger. That's flagged explicitly in `TODO.md` rather than checked off as fully verified.

### Supporting files

- **`.pre-commit-config.yaml`** — Ruff (check + format) for the backend, ESLint + Prettier for the frontend, as local hooks. Written but not installed (`pre-commit install`) in this environment, since the `pre-commit` tool itself isn't present here — another item flagged rather than silently assumed done.
- **`docs/architecture.md`** — a stub, expanded incrementally as phases land, rather than written once and left stale.
- **`README.md`** — quick-start for both the Docker path and the native (no-Docker) path.
- **`LICENSE`** — MIT.

## How it all connects

```
Developer runs `docker compose up`
        │
        ├─→ postgres (health-checked before backend starts)
        ├─→ ollama (independent — LLM_PROVIDER=mock means the app doesn't need it yet)
        ├─→ backend  ─── reads .env / docker-compose environment overrides
        │        │             via app/core/config.py (single source of config truth)
        │        ├─→ app/core/logging.py configures structured JSON logs on startup
        │        └─→ app/db/session.py opens a SQLAlchemy engine against
        │             whatever DATABASE_URL it was given (sqlite locally,
        │             postgresql+psycopg via Docker) — same code either way
        └─→ frontend (Vite dev server, proxies API calls to VITE_API_BASE_URL)
```

The one thing every later phase depends on from Phase 0 is the **configuration and logging discipline**: no new module should read `os.environ` directly, and no new module should call `logging.basicConfig()` or otherwise set up its own handlers. Everything routes through `app/core/config.py` and `app/core/logging.py` so the system's runtime behavior stays centrally controllable — a requirement for the observability work planned in Phase 13.

## Key decisions and why

| Decision | Reasoning |
|---|---|
| Flat `app/` package, not `src/app/` | This is a service, not a distributed library — the `src/` layout's import-isolation benefit doesn't apply |
| ESLint/Prettier over the newer `oxlint` default | Explicit project requirement beats a scaffolding tool's newer default |
| Single-stage Dockerfile with layered `uv sync`, not literal multi-stage | Achieves the actual goal (fast rebuild on code-only changes) with less file complexity; noted as revisitable if image size matters |
| `chown -R appuser:appuser /app` before switching users | Required because dev-mode bind-mounting + `--reload` triggers a runtime `.venv` write that a root-owned `.venv` would reject under a non-root runtime user |
| Every `docker-compose.yml` port bound explicitly to `127.0.0.1` | Prevents an IPv6 (`::1`) connection from being silently accepted-then-never-serviced by Docker Desktop on macOS — an explicit IPv4-only host bind makes an IPv6 attempt fail fast so the browser's fallback works, instead of hanging indefinitely |
| `LLM_PROVIDER=mock` as the default | The whole system — including CI — must run with zero LLM dependency; Ollama is opt-in, not required, for anything through Phase 0 |
| SQLite default outside Docker, Postgres inside Docker | Zero-dependency native development (no need to install/run Postgres locally to write code) while still exercising the "real" database in the containerized path — and Phase 1 proves both paths actually produce identical schemas |

## Verification performed

This wasn't just "the files exist" — each claim below was actually run, not assumed:

- `uv run uvicorn app.main:app` boots locally; `/healthz` and `/docs` both respond.
- `uv run ruff check .` and `uv run ruff format --check .` pass.
- `uv run pytest` passes (the one Phase 0 test hits `/healthz` via `TestClient`).
- `npm run lint`, `npm run format:check`, and `npm run build` all pass on the frontend.
- `docker compose build` succeeds for both `backend` and `frontend` images.
- `postgres` + `backend` + `frontend` were brought up together via `docker compose up`; `/healthz` was confirmed returning `{"status":"ok","database":"ok"}` against the **real** containerized Postgres, not SQLite.
- `ollama` was brought up independently and confirmed responding on `:11434` (no model pulled — that's a multi-GB download reserved for the Phase 15 quick-start, not something to do speculatively in Phase 0).
- `.gitignore` effectiveness was checked directly via `git status`, not assumed from the pattern list.

Not yet verified (called out rather than silently marked done): an actual GitHub Actions run (no push to a triggering point yet), and `pre-commit install` (tool not present in this environment).

## What Phase 0 deliberately does not include

No database tables, no ORM models, no business logic, no real API endpoints beyond the health check, no frontend UI beyond the Vite template's default page. That's all intentional — Phase 0's only job is to make the next phase's work possible, not to anticipate it.
