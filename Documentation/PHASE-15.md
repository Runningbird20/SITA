# Phase 15: Deployment — Completion Report

Status: complete. See [DEF.md § Phase 15](DEF.md#phase-15-deployment) for the deployment contract (health-check semantics, bootstrap-script idempotency guarantee) and [TODO.md](../TODO.md#phase-15-deployment) for the itemized checklist.

## Goal

Fourteen phases had built a real, hardened, observable, evaluated system — but getting from `git clone` to a populated dashboard still meant reading several README sections and running four or five commands by hand, in the right order, with no feedback about whether a service was actually ready before the next step ran against it. TODO.md's own Definition of Done for this phase is specific: "a developer with only Docker installed can clone the repo, run one documented command sequence (ideally one script), and see a populated dashboard with correlated incidents and AI-generated triage within minutes." This phase closes that gap and is, deliberately, mostly glue and documentation rather than new application code — the pipeline, the API, and the dashboard were already real; what was missing was the last mile connecting them for a first-time reviewer.

## What was built

### `docker-compose.yml`: health checks that mean something

Before this phase, only `postgres` had a `healthcheck` — `backend` and `frontend` had none, and `depends_on` used the default `service_started` condition, which only means "the container process began," not "the service inside it can answer a request." That distinction matters directly for a bootstrap script: `docker compose up --wait` returns as soon as its readiness criteria are met, and without real health checks those criteria were too weak to safely chain a migration step immediately afterward.

Added: a `backend` health check against its own `/healthz` (via `python3 -c "urllib.request.urlopen(...)"` — the base image already has `python3` on `PATH`, no extra tooling installed), an `ollama` health check against `ollama list` (succeeds once the daemon responds, regardless of whether a model has been pulled — pulling one stays a separate, optional step), and a `frontend` health check against its own Vite dev server via Node's built-in `http` module (`node:22-slim` has no `curl`/`wget`). `frontend`'s `depends_on: backend` was upgraded from the default condition to `condition: service_healthy`. `backend` deliberately does **not** hard-depend on `ollama`'s health — `MockProvider` is the project's real default, and making the backend wait on Ollama would make the "zero required LLM dependency" pitch false at the compose-file level, not just in prose.

A new read-only bind mount, `./data:/data:ro` on the `backend` service, gives the container access to `data/synthetic_events/` at runtime — it had never been reachable inside the container before this phase (the Dockerfile only ever `COPY`s `app/`, `alembic/`, `alembic.ini`). This is what makes loading the synthetic datasets from inside the container possible at all, and it's what the bootstrap script below relies on.

### `scripts/demo.sh`: the one-shot bootstrap, and why it uses the CLI, not the REST endpoint, for loading data

Brings up the stack (`docker compose up --build -d --wait`, so it genuinely waits for every service's real health check), applies migrations, loads every file under `data/synthetic_events/` — five source-type directories plus the multi-stage `scenarios/brute_force_to_lateral_movement/` scenario — and triggers one real `POST /api/v1/pipeline/run` so the dashboard is already populated and triaged, not empty, the first time a reviewer opens it.

Data loading goes through `app.ingestion.cli` run inside the container (against the new `/data` bind mount), one call per file — not the REST ingestion endpoint. This was a deliberate choice, not an oversight: Phase 14 added a strict rate limit (30/min default) specifically on the ingestion endpoint, and posting ~20 files' worth of records as individual HTTP requests would either fight that limit or require special-casing the bootstrap script around it. The CLI path is one process-internal call per file — no HTTP round trip, no rate limit interaction, and it's the same, already-tested code path the batch-import documentation has recommended since Phase 2.

**Idempotent by a real check, not a marker file**: before loading anything, the script queries `GET /api/v1/incidents?limit=1` and reads `total` from the live response. A non-zero total means a previous run already populated the database, and the script skips straight to printing the dashboard URL. This sidesteps a real limitation rather than working around it silently: ingestion itself has no deduplication, and detection's own re-run behavior is Phase 3's documented `[[detection-run-idempotency]]` gap — re-running the full load-and-pipeline sequence a second time would create duplicate events, alerts, and incidents. The script's own idempotency check means a reviewer running it twice by accident (or intentionally, to double-check it works) gets a safe no-op, not a silently corrupted demo dataset.

**Never touches `LLM_PROVIDER`**: the script runs with whatever `.env` already specifies, creating one from `.env.example` (`LLM_PROVIDER=mock`) only if none exists — it never switches a reviewer into `ollama` mode or attempts to pull a multi-gigabyte model automatically. That stays a separate, explicit, documented opt-in step in the README, exactly as it worked before this phase; a "quick demo" script silently starting a large background download would be a bad surprise, not a convenience.

**A real bug this phase's own verification caught: MITRE data was never loaded.** The first version of the script ran the pipeline-trigger endpoint expecting it to produce a fully-populated dashboard, including MITRE ATT&CK mappings. It didn't — `POST /api/v1/pipeline/run`'s MITRE-mapping stage only *links* alerts to technique rows that already exist in the `mitre_techniques` table; loading the vendored technique dataset itself has always been a separate step (`app.mitre.cli`, or its `load_techniques()` call specifically), by design (see `app/mitre/pipeline.py`'s own docstring: "if the loader hasn't run yet... that link is silently skipped"). Nothing about this is a bug in Phase 8's code — it's a documented, self-healing characteristic — but the bootstrap script not knowing about it meant a reviewer's first look at the MITRE technique library page, and every incident's technique list, would be empty despite the pipeline having "run." Caught by actually taking screenshots of a live, freshly-bootstrapped instance rather than assuming the pipeline trigger was sufficient — the MITRE library page was visibly blank. Fixed by adding `docker compose exec backend uv run python -m app.mitre.cli` to the script, before the pipeline-trigger call. Verified afterward against a from-scratch clean run: 6 techniques loaded, 17 alert-to-technique mappings created, confirmed present both on `/mitre` and on an incident detail page.

### README: the one-shot script as the lead path, with the manual sequence kept and explained

The Quick Start section now leads with `./scripts/demo.sh` as the single command, showing real expected output and the actual measured runtime, followed by a "doing it by hand" subsection that lists the same steps individually — for a reader who wants to understand what the script does, customize it, or run one step in isolation. A new "Enabling real AI triage" section makes the mock-vs-real-LLM distinction explicit at the point a reader would actually want to act on it, including how to force-regenerate triage results for incidents that already have mock/invalid ones on file (`app.triage.cli --force`) — a real gap that would otherwise leave a reviewer confused about why switching `LLM_PROVIDER` didn't change anything already on screen (Phase 7's `run_triage` is add-only per prompt version; it doesn't overwrite an existing result, by design, for auditability — this documentation is what makes that design decision legible to someone hitting it for the first time rather than a hidden trap).

An ASCII architecture diagram (matching `docs/architecture.md`'s existing one, not a duplicate elaboration of it — see CLAUDE.md's own "don't duplicate DEF.md's content" convention applied here to `docs/architecture.md`) and four real screenshots — the overview dashboard, the incident list, an incident detail page with a real AI-generated analysis panel, and the MITRE technique library — were added, all captured from a stack actually brought up by this phase's own tooling, not mocked up.

## How it all connects

```
git clone && ./scripts/demo.sh
        │
        ▼
docker compose up --build -d --wait
        │  postgres/backend/ollama/frontend healthchecks (new this phase)
        ▼
docker compose exec backend uv run alembic upgrade head
        │
        ▼
GET /api/v1/incidents?limit=1 → total
        │
        ├──[total > 0]──→ skip straight to printing URLs (idempotent re-run)
        │
        └──[total == 0]──→ for each data/synthetic_events/**/*.jsonl:
                                docker compose exec backend
                                  uv run python -m app.ingestion.cli <type> /data/...
                                (the new ./data:/data:ro bind mount)
                                │
                                ▼
                            docker compose exec backend
                              uv run python -m app.mitre.cli
                            (loads the vendored MITRE technique dataset —
                             the pipeline endpoint below only links to it,
                             never loads it; a real gap this phase's own
                             screenshot verification caught)
                                │
                                ▼
                            POST /api/v1/pipeline/run
                                (detection → IOC extraction → MITRE mapping →
                                 correlation → AI triage, LLM_PROVIDER=mock
                                 by default)
                                │
                                ▼
                     http://localhost:5173  (populated dashboard)
```

## Key decisions and why

| Decision | Reasoning |
|---|---|
| `scripts/demo.sh` uses the ingestion CLI inside the container, not the REST endpoint | Avoids fighting Phase 14's ingestion rate limit with ~20 individual HTTP calls; reuses the same batch-import path documented since Phase 2 rather than inventing a second one |
| A new `./data:/data:ro` bind mount, read-only | The container had no access to `data/synthetic_events/` at all before this phase; read-only because the bootstrap script only ever reads from it, never writes |
| Idempotency checked via a live API call (`total` from `GET /api/v1/incidents`), not a local marker file | A marker file could exist while the database itself was reset (e.g., `docker compose down -v`), giving a false "already loaded" reading; asking the actual system is the only check that can't drift out of sync with reality |
| `backend` does not health-depend on `ollama` | Would make the "zero required LLM dependency" pitch false at the infrastructure level, not just in prose — `MockProvider` is the real default and must work with Ollama absent entirely |
| The bootstrap script never touches `LLM_PROVIDER` or pulls a model automatically | A multi-gigabyte silent download inside a "quick demo" script would be a bad surprise; enabling real AI triage stays a deliberate, documented, separate step |
| Screenshots captured from a stack the script itself brought up, with `LLM_PROVIDER=ollama` for the AI-panel shot specifically, captioned as such | Showing a genuinely populated AI panel is more useful than showing the true zero-setup default's placeholder text, but claiming it as the default view without disclosure would be misleading — the caption states plainly which mode produced it |
| Architecture diagram reuses `docs/architecture.md`'s existing ASCII diagram rather than a new image | Matches this project's established "link, don't duplicate" convention for anything DEF.md/architecture.md already owns |
| `app.mitre.cli` added as its own bootstrap step, not folded into the ingestion loop or assumed covered by the pipeline endpoint | The pipeline endpoint's MITRE stage only links to already-loaded techniques by design (self-healing, not a bug); the loader is a genuinely separate concern and belongs at its own point in the sequence, run once before the first pipeline trigger |

## Verification performed

- `docker compose up --build --wait` from a stopped state: all four services (`postgres`, `ollama`, `backend`, `frontend`) reported `Healthy` in ~24 seconds — confirmed the new health checks actually gate readiness, not just container start.
- `./scripts/demo.sh` run from a **genuinely clean state** (containers down, `postgres` volume removed) three separate times over the course of this phase, as the MITRE gap below was found and fixed: the final, authoritative run — full stack up, migrations applied, all 20 synthetic dataset files + the multi-stage scenario loaded, MITRE dataset loaded, full pipeline run — completed in **55.7 seconds** with `LLM_PROVIDER=mock` (the actual default a fresh clone would have). Confirmed via the real API afterward: 17 alerts, 10 incidents (one genuinely reconstructing the multi-stage scenario as a single 4-alert incident, as `data/synthetic_events/scenarios/brute_force_to_lateral_movement/README.md` describes), 6 MITRE techniques loaded, that incident showing 4 real technique mappings.
- Re-ran the script immediately afterward against already-populated data: correctly detected existing incidents via the live `total` check and skipped straight to printing the dashboard URLs in ~3 seconds — no duplicates created, confirmed by re-checking the incident count was unchanged.
- **The MITRE-loading gap above was found by this exact verification process** — taking real screenshots of a freshly-bootstrapped instance and looking at them, not just checking HTTP status codes. The `/mitre` page was visibly empty on the first clean run; traced to the pipeline endpoint's self-healing-but-load-nothing MITRE stage, fixed, and re-verified clean from scratch.
- Screenshots captured with Playwright against the actual running dashboard (not mocked/hand-edited): `docs/images/overview.png`, `incidents.png`, `incident-detail.png`, `mitre.png`. The incident-detail shot specifically required its own extra pass — the first attempt used `LLM_PROVIDER=mock`, and Mock's default canned response (`"{}"`) correctly produces an `invalid`, empty-looking AI panel (the honest default behavior, not a bug), which wasn't a compelling screenshot; switched to a real local Ollama model (`qwen2.5:0.5b`, pulled for real, one full triage pass took ~5.5 minutes for 60 real LLM calls) for a clean run to capture genuinely AI-generated content — including a real, disclosed model quirk (a hallucinated "ransomware" classification, consistent with the same model's behavior observed in Phase 12) — captioned in the README as opt-in, not the default.
- Full backend and frontend test suites re-run after all Phase 15 changes: unaffected (this phase touched no application code, only `docker-compose.yml`, `scripts/demo.sh`, and documentation) — confirmed the existing suites still pass rather than assumed.

## What Phase 15 deliberately does not include

**No production-hardened deployment target** — `docker-compose.yml`'s `frontend` service still runs the `dev` target (hot-reload Vite server), not the `production` nginx stage Phase 14 hardened; wiring a genuine production compose profile (using the `production` target, real TLS termination, non-`--reload` backend) is a larger scope than "make the local demo reliable" and isn't what TODO.md's Definition of Done for this phase asks for. **No CI integration for `scripts/demo.sh`** — it's a local convenience script for a human reviewer, not a test; the existing CI jobs (lint, test, dependency scan) already cover correctness, and running a multi-minute Docker Compose bootstrap in CI would duplicate that coverage at a much higher cost for no new signal. **No automated screenshot regeneration** — the four PNGs in `docs/images/` are static, captured once against a real running instance; keeping them in sync with future UI changes is a manual step, not a build-time check, matching this project's existing practice of hand-curated (not generated) documentation assets.
