# Phase 13: Observability — Completion Report

Status: complete. See [DEF.md § Phase 13](DEF.md#phase-13-observability) for the metric/log field definitions and the implemented-status log, and [TODO.md](../TODO.md#phase-13-observability) for the itemized checklist.

## Goal

Twelve phases had produced a working, measured system, but almost nothing in it actually logged what it was doing — Phase 0 built a structured-JSON logging *configuration*, but by this phase only `main.py`, `app/llm/base.py`, and `app/api/health.py` had ever called into it. `ingestion/service.py`, `detection/pipeline.py`, and `correlation/pipeline.py` — three of the five layers TODO.md names — had no logging at all. This phase's goal, per TODO.md, is "production-style visibility into what the system is doing": close that gap, make every request traceable end-to-end, and give the system real metrics rather than only structured logs to read after the fact.

## What was built

### Structured logging, actually used everywhere it was supposed to be

`ingestion/service.py`, `detection/pipeline.py`, and `correlation/pipeline.py` each gained a module logger and one structured summary log line per run (accepted/rejected counts, alerts-by-rule, incidents created/joined) — closing the gap described above rather than adding logging as decoration. `app/llm/base.py` already logged per-attempt; this phase only added metric emission there, since the logging itself was already solid (Phase 6's work).

### Request IDs, via a ContextVar, and the bug that comes with getting the ordering wrong

`app/core/request_context.py` is a single `ContextVar[str | None]` plus a `logging.Filter` that stamps every `LogRecord` with the current request ID — attached once in `configure_logging()`, so every logger in the app gets it for free. A middleware in `app/main.py` sets the contextvar per request (honoring an inbound `X-Request-ID` header, generating a UUID otherwise) and echoes it back as a response header.

The first version of this middleware reset the contextvar in a `finally` scoped only to the `call_next()` call — before the "request completed" log line and the metrics-recording code that ran after it. Every completion log line was silently stamped `request_id: null`, while the start log line correctly showed the real ID. The test suite as originally written didn't catch this, because the original tests checked the HTTP response header (set from a local variable, unaffected by the contextvar bug) rather than the log output itself. It was caught by starting the real dev server and reading its own JSON logs directly — the same "run it for real, don't just trust the tests" discipline this project has applied in every phase since Phase 4's IOC extractor bugs and Phase 11's Postgres verification. Fixed by widening the `finally` to wrap the entire middleware body, and locked in with a regression test that reads the actual log record via `caplog` rather than only the response.

### Metrics: one registry, prometheus_client, `GET /metrics`

`app/core/metrics.py` declares every counter and histogram once, at import time — ingestion counts, detection-rule firings and duration, incidents created/updated, LLM calls and duration (labeled by provider/model/task_type/status), and HTTP request counts and duration. `app/api/metrics.py` exposes it at `GET /metrics` in standard Prometheus text format. This is real, standard exposition format — any actual Prometheus instance can scrape it as-is — but the bundled Grafana dashboard and docker-compose profile TODO.md's stretch item also names were not built; that's additional shipped infrastructure beyond "expose metrics," and nothing in this project currently depends on it existing.

### Error tracking: one catch-all handler

`app/main.py` gained an `@app.exception_handler(Exception)` that logs any otherwise-unhandled exception with a full traceback (request-ID-tagged, via the filter above) and returns the same `{"error": {"code": ..., "message": ..., "details": ...}}` envelope shape every other API error already uses, instead of FastAPI's default unstructured 500. Verified against a genuine unhandled exception (an unmigrated throwaway database, hit by accident while smoke-testing) — the client got a clean structured 500, and the server log had the full traceback tagged with the exact request ID that triggered it.

### Health check: LLM reachability, without slowing down the common case

`GET /healthz` gained an `llm` field. For the default `mock` provider it reports `"not_configured"` and makes no network call at all — this endpoint is polled frequently, and there's nothing to reach for Mock. For `ollama`, one short-timeout (2s) `GET /api/tags` call (not a real generation request) reports `"ok"` or `"unavailable"`, and the overall `status` degrades if either the database or a configured LLM check fails.

### The frontend's status page gets a real Phase 13 check, and two backfilled ones

Phase 13 introduces `/metrics`, so it gets a real `liveCheck` — `useBackendStatus` now also fetches `/metrics` and checks for a metric that's always present from process start (an unlabeled counter, emitted even before any pipeline activity), never allowed to fail the whole status poll (a `/metrics` hiccup marks only Phase 13 broken, not every phase, since it's fetched with its own try/catch rather than joining the existing `Promise.all`'s failure path). While making this change, found that Phase 11 and Phase 12 were still wired to `notImplemented` in `src/data/phases.ts` even though both were already complete — a real instance of exactly the staleness `CLAUDE.md` warns the dashboard must never have. Fixed alongside this phase's own work rather than left for later, since it's the same "keep the manifest honest" obligation this phase's own new entry has to meet.

## How it all connects

```
app/core/request_context.py (ContextVar + RequestIdFilter)
        │
        ▼
app/core/logging.py :: configure_logging()   — filter attached once, here
        │
        ▼
app/main.py :: request_id_and_metrics middleware
        │  sets contextvar → logs "request started" → call_next() →
        │  logs "request completed" → records HTTP metrics → resets contextvar
        │
        ├──→ every logger.info/.warning/.exception call anywhere in the app,
        │    for the lifetime of this request, is stamped with the same ID
        │    (ingestion/service.py, detection/pipeline.py,
        │    correlation/pipeline.py, llm/base.py included)
        │
        └──→ on an unhandled exception: app.exception_handler(Exception)
             logs the traceback (request-ID-tagged) and returns the
             standard structured error envelope

app/core/metrics.py (registry, declared once)
        │
        ├──← events_ingested_total / ingestion_errors_total   (ingestion/service.py)
        ├──← alerts_created_total / detection_rule_duration_seconds (detection/pipeline.py)
        ├──← incidents_created_total / incidents_updated_total (correlation/pipeline.py)
        ├──← llm_calls_total / llm_call_duration_seconds       (llm/base.py, per attempt)
        └──← http_requests_total / http_request_duration_seconds (main.py middleware)
        │
        ▼
app/api/metrics.py :: GET /metrics   (Prometheus text exposition format)
        │
        ▼
frontend useBackendStatus() :: fetchMetricsAvailable()
        │
        ▼
src/data/phases.ts Phase 13 :: liveCheck(status.metricsAvailable)
```

## Key decisions and why

| Decision | Reasoning |
|---|---|
| A ContextVar + logging.Filter, not a request_id parameter threaded through every function | Every logger in the app picks it up for free; a threaded parameter would mean touching every pipeline function's signature for a cross-cutting concern that isn't part of any function's actual logic |
| Request-ID propagation through the pipeline-trigger endpoint needs no extra plumbing | `POST /api/v1/pipeline/run` runs the pipeline synchronously inside the request — the contextvar is already in scope. Documented explicitly that a genuinely async/background job queue in a later phase would need to carry it across that boundary deliberately, since contextvars don't cross threads/processes automatically |
| `prometheus_client`, in-process, not a custom metrics format | Small, pure-Python, no network dependency — consistent with "no paid APIs, no required cloud dependency." Standard exposition format means any real Prometheus/Grafana can use it as-is, without this project needing to build a custom ingestion side |
| Stretch item done half — format yes, bundled Grafana/compose profile no | Stated plainly rather than silently skipped: the dashboard/compose profile is materially more shipped infrastructure than "expose metrics" requires, and nothing reviewer-facing currently depends on it |
| `sita_llm_calls_total` counts per network attempt, not per logical task | A task that retries twice before succeeding produces three attempt-level metric points, which is the more useful shape for "success/failure rate" than collapsing retries into one outcome — matches how `llm/base.py` already logged per-attempt before this phase |
| `/healthz`'s LLM check makes zero network calls for Mock | This endpoint is polled frequently by orchestration/Docker health checks; there's nothing to reach for Mock, and adding a call would only add latency for the project's actual default configuration |
| The request-ID contextvar reset moved to wrap the whole middleware body, not just `call_next()` | Found by running the server for real and reading its own logs — the original placement reset the ID before the "request completed" log line and the metrics code that followed it, so every completion log line lost its ID. Fixed and regression-tested via `caplog`, not just re-checked by eye |
| Phase 11 and 12's dashboard entries fixed to `staticImplemented` alongside this phase | Found stale (`notImplemented`) while wiring Phase 13's own entry — the same obligation Phase 13's own new entry has to meet ("don't let the dashboard lie about what's built"), so fixed immediately rather than deferred |

## Verification performed

- Full backend suite after this phase: 363 passed, 1 skipped (the opportunistic live-Ollama test), 98% line coverage — every new/modified core module (`app/main.py`, `app/api/health.py`, `app/api/metrics.py`, `app/core/logging.py`, `app/core/metrics.py`, `app/core/request_context.py`) at 100%. `ruff check`/`ruff format --check` clean.
- Live server verification, not just the test suite: `GET /healthz` and `GET /metrics` over real HTTP with real output; a genuine unhandled exception (hit by accident against an unmigrated throwaway SQLite file) producing a full traceback in the server logs, correctly request-ID-tagged, while the client received the same clean structured 500 envelope every other API error uses; a real `ingest → POST /api/v1/pipeline/run` run against a migrated database, confirming `sita_alerts_created_total`, `sita_incidents_created_total`, and `sita_detection_rule_duration_seconds` reflect real pipeline activity, and that `detection run completed`/`correlation run completed` log lines emitted mid-request carry the same `request_id` as the HTTP access log lines around them. This is how the request-ID reset-ordering bug above was actually found.
- Frontend: `npm run lint`, `npm run test -- --run` (11 passed, no test file needed changes since none previously touched `HealthzResponse`/`BackendStatus`), `npm run build` all clean. Confirmed live: `/metrics`'s real output matches what `fetchMetricsAvailable`'s substring check expects.

## What Phase 13 deliberately does not include

**No bundled Grafana dashboard or docker-compose metrics profile** — the stretch item's format half is real and standard; the dashboard/profile half is additional shipped infrastructure not built, stated plainly rather than silently dropped. **No multi-worker/multi-process metric aggregation** — `prometheus_client`'s default registry is in-process memory, correct for this project's documented single-`uvicorn`-process run mode, but would under-count across multiple worker processes without a push-gateway or shared registry; noted as a real limitation, only relevant if Phase 15's deployment story grows beyond one backend process. **No propagation of request IDs across a background job queue** — there isn't one in this project; if a later phase adds genuinely async/background pipeline processing, carrying the ID across that boundary would need explicit handling, since contextvars don't cross threads/processes automatically. **No distributed tracing (OpenTelemetry spans, etc.)** — not asked for by TODO.md's task list; request IDs plus structured logs are the traceability mechanism here, proportionate to a single-process local-first app. **No log aggregation/shipping** — logs go to stdout as structured JSON, matching container-log conventions, but nothing ships them anywhere; that's a deployment concern, not this phase's.
