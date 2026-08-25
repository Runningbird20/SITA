# Phase 9: REST API — Completion Report

Status: complete. See [DEF.md § Phase 9](DEF.md#phase-9-rest-api) for the field-level pagination/filtering/sorting/error conventions and the full endpoint reference — this document is the narrative of how it got implemented and why. For the checklist itself, see [TODO.md](../TODO.md#phase-9-rest-api).

## Goal

Every `*Read` Pydantic schema this project needed has existed since Phase 1 — `app/schemas/__init__.py` has said "Create/Update variants are added in Phase 9 alongside the endpoints that actually need them" since it was written, eight phases ago. Phase 9 is the payoff of that discipline: wire all of it into a consistent, paginated, filterable, sortable, well-documented REST surface, so the frontend (Phase 10) and any external tooling have one real way to reach every domain object this project has built.

## What was built

### Three shared concerns, built once, used by every resource

Rather than each of the 8 resource routers inventing its own pagination/sorting/error handling, three small pieces of shared infrastructure carry that weight:

- **`Page[T]`** (`app/schemas/pagination.py`) — the one envelope every list endpoint returns (`items`, `total`, `limit`, `offset`), using PEP 695 generic syntax (`class Page[T](BaseModel)`), the modern equivalent `typing.Generic[T]` that this project's `ruff` config actively prefers.
- **`apply_sort()`** (`app/api/deps.py`) — takes a `sort` query param, a per-resource whitelist dict (`{"created_at": Model.created_at, ...}`), and a default; raises `InvalidQueryParameterError` for anything not in the whitelist. No resource ever lets a raw string reach `ORDER BY` unchecked, and no resource has to hand-roll its own validation.
- **`pagination_params()`** — a `Depends()`-injected dataclass for `limit`/`offset`, bounds-checked by FastAPI's own `Query(ge=..., le=...)`.

### Errors: one envelope, two custom exceptions, one override

`NotFoundError` and `InvalidQueryParameterError` (`app/core/exceptions.py`) are plain Python exceptions a route handler raises directly — no per-endpoint try/except, no manual `JSONResponse` construction at the call site. Three handlers registered in `app/main.py` catch them (plus FastAPI's own `RequestValidationError`, for malformed query params or bad path-param types) and reshape all three into the same `{"error": {"code", "message", "details"}}` shape. A client checking `response.json()["error"]["code"]` never has to know whether a given 422 came from a hand-written check or FastAPI's own Pydantic validation — this was worth confirming directly, not assumed: `test_invalid_sort_field_returns_422` and `test_invalid_limit_returns_structured_422` in `test_events_api.py` hit both paths and check the same envelope shape.

### The nested `IncidentDetail` — the one endpoint that isn't a thin passthrough

Every other `GET /{id}` endpoint returns its ORM row through `response_model`'s automatic `from_attributes` conversion with no extra code. `GET /incidents/{id}` is different: TODO.md asked for "nested alerts/IOCs/AI analyses," and an `Incident` has no direct `iocs` relationship — only `alerts`, each of which has its own `iocs`. The handler builds the deduplicated union itself (`{ioc.id: ioc for alert in incident.alerts for ioc in alert.iocs}`) and calls Phase 8's `incident_technique_rollup()` for the `mitre_techniques` field, then constructs `IncidentDetail` explicitly rather than relying on ORM auto-conversion. One thing worth noting about the mechanism, not just this one endpoint: passing raw ORM objects (or dataclasses, for the MITRE rollup) directly into fields typed as nested Pydantic models works because those nested schema types themselves carry `from_attributes=True` — verified directly (`python -c` round-trip check) before relying on it, since this is exactly the kind of "assumed to work" detail Phase 6/7/8's verification discipline exists to catch instead of assume.

### The pipeline-trigger endpoint composes, it doesn't reimplement

`POST /api/v1/pipeline/run` calls `run_detection`, `run_ioc_extraction`, `run_mitre_mapping`, `run_correlation`, `run_triage` — the exact same functions every CLI since Phase 3 has called — in the same order their own docstrings have documented since Phase 8, then commits once and returns one `PipelineRunReport` bundling each stage's existing report schema unchanged. No new pipeline logic exists anywhere in this endpoint; it is entirely orchestration glue over already-built, already-tested code.

### OpenAPI polish

`openapi_tags` in `app/main.py` gives every resource tag a one-line description (including a pointed one for `analysis-results`, calling out the deterministic/AI distinction directly in the docs a reviewer might open), and the app-level `description` states the same distinction up front. Every endpoint function has a docstring, which FastAPI surfaces as that operation's description in both `/docs` and `/openapi.json` — confirmed rendering by hitting `/docs` and `/redoc` directly against the live stack, not assumed from the code alone.

## How it all connects

```
app/schemas/*Read (Phase 1)  +  app/mitre/rollup.py (Phase 8)  +  app/schemas/*_run.py (Phases 3-8)
        │
        ▼
app/schemas/pagination.py :: Page[T]         app/core/exceptions.py :: NotFoundError, InvalidQueryParameterError
        │                                              │
        ▼                                              ▼
app/api/deps.py :: pagination_params(), apply_sort()   app/main.py :: exception_handler(...)
        │                                              │
        └──────────────────┬───────────────────────────┘
                            ▼
    app/api/{events,alerts,incidents,iocs,detections,
             analysis_results,recommendations,mitre}.py
                 GET list  →  Page[XRead]
                 GET {id}  →  XRead | XDetail
                            │
                            ▼
                app/api/pipeline.py :: POST /pipeline/run
                     run_detection → run_ioc_extraction → run_mitre_mapping
                        → run_correlation → run_triage
                            │
                            ▼
                     app/main.py :: app.include_router(...) × 9
```

## Key decisions and why

| Decision | Reasoning |
|---|---|
| Offset pagination, not cursor-based | No infinite-scroll consumer exists yet; offset is the simpler contract for the tabular list views Phase 10 will build, and cursor pagination solves a problem (stable pagination under concurrent writes) this project doesn't currently have |
| Sort whitelists explicitly exclude `Severity`/enum-typed fields | They're stored as plain `VARCHAR`; a naive SQL sort would order alphabetically (`critical` < `high` < `low` < `medium`), not by actual rank. Building a `CASE`-based severity ordering for a feature nothing has asked for yet would be exactly the ahead-of-need work this project avoids — left undone and documented, rather than shipped silently wrong |
| No Create/Update/Delete on any of the 8 resources | Every task in TODO.md's list was phrased "list/filter/get"; nothing downstream yet mutates these objects through the API. `Recommendation.status` (open/acknowledged/dismissed/completed) is the most obvious future PATCH target, but its only real consumer is Phase 10's dashboard, which doesn't exist yet |
| `POST /pipeline/run` is synchronous, no job queue | This project's synthetic datasets run the whole chain in well under a second; a background-task/polling-status abstraction would solve a latency problem that doesn't exist here |
| `{id}` path params are always the internal UUID, never `MITRETechnique.technique_id` | Consistency with every other resource beats convenience for the one resource where a human-readable natural key exists; `technique_id` is still filterable and visible in every response body |
| `IncidentDetail` built by explicit construction, not relying on `from_attributes` alone | The IOC rollup (dedup across alerts) and MITRE rollup (Phase 8's grouping logic) aren't things a flat ORM-attribute walk can produce — they need real code, so the handler writes it rather than pretending a single `response_model=` declaration could |
| Shared `tests/integration/conftest.py` extracted from the pre-existing `test_events_api.py` | Nine new API test files all needed the same TestClient/DB-override wiring; duplicating it nine times would have been exactly the kind of repetition this project's own `code-review`/`simplify` conventions flag |

## Verification performed

- 51 integration tests total (48 net-new) across `tests/integration/test_{events,alerts,incidents,iocs,detections,analysis_results,recommendations,mitre,pipeline}_api.py` — every documented filter and sort field, the pagination envelope's `total`/`limit`/`offset` arithmetic, both flavors of 422 (custom whitelist violations and FastAPI-native validation) sharing one error shape, 404s for every single-resource `GET`, the `AnalysisResult` exactly-one-of `incident_id`/`alert_id` requirement (missing and both-provided cases), the nested `IncidentDetail` payload checked field-by-field against a real fully-linked object graph built through `seed_full_incident()`, and the pipeline endpoint's report structure with and without a request body.
- `ruff check`/`ruff format --check` pass clean. Full backend suite: 310 passed, 1 skipped (Phase 6's live-Ollama test), 0 failed.
- Verified against the live `docker compose` stack (real Postgres, picked up automatically via the bind-mounted `backend/app` and `uvicorn --reload`): every list/get endpoint, the `rule_key` join filter on `/alerts`, the nested `IncidentDetail` payload against real persisted data (correct `JSONB` round-trip for `correlation_method`, correct IOC dedup across a real alert), and both error envelope shapes, all confirmed via direct `curl` against `127.0.0.1:8000`. `/docs` and `/redoc` both confirmed rendering (`200`). `POST /pipeline/run` was deliberately not exercised over this live, persistent stack, since (unlike the GET endpoints) it commits and there was no way to roll that transaction back through a live HTTP server — its correctness rests on the SQLite integration tests exercising identical orchestration code, plus every stage it calls already having its own dedicated Postgres verification from Phases 3–8.
- Frontend: confirmed `frontend/src/data/phases.ts`'s updated `liveCheck` predicates are served live by the bind-mounted Vite dev server (`curl http://127.0.0.1:5173/src/data/phases.ts`). **Not verified**: an actual rendered screenshot of the dashboard turning green for phases 3/4/5/7/8/9 — same "no browser tool available" limitation as every prior frontend change in this project, flagged explicitly rather than claimed. `npm run lint`/`format:check`/`build` all confirmed clean.

## What Phase 9 deliberately does not include

**No Create/Update/Delete** on any resource — every task was scoped "list/filter/get"; the first real mutation surface (`Recommendation.status`, most likely) is Phase 10's job, once there's an actual UI consumer to design it against. **No authentication** — matches every endpoint built so far; Phase 14's job. **No severity-aware sorting** — deliberately left undone rather than shipped wrong; see the key-decisions table. **No background job queue for `POST /pipeline/run`** — nothing in this project's scope needs it yet. **No rate limiting, request logging middleware, or API versioning beyond the existing `/api/v1` prefix** — none of these were asked for in TODO.md's task list, and adding them speculatively would be exactly the kind of ahead-of-need infrastructure this project avoids.
