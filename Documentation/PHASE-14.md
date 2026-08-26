# Phase 14: Security Hardening — Completion Report

Status: complete. See [DEF.md § Phase 14](DEF.md#phase-14-security-hardening) for the field-level design of each mechanism and the implemented-status log, and [TODO.md](../TODO.md#phase-14-security-hardening) for the itemized checklist.

## Goal

TODO.md frames this phase directly: "since this is a security-focused project, its own security posture is part of the pitch." Thirteen phases had built a real detection/triage pipeline with a real API and a real dashboard, but almost none of the standard hardening a SOC-tool reviewer would look for — auth, rate limiting, security headers, a documented prompt-injection threat model — existed yet. This phase closes that gap across eight independent tasks, each with its own mitigation and its own honest limits.

## What was built

### Input validation: the two real gaps, not a restatement of what already existed

Every ingestion adapter and every API request body was already Pydantic-validated before this phase (Phase 2, Phase 9) — restating that wouldn't be new work. Two real gaps got closed: no cap existed anywhere on request body size (a `Content-Length`-checking middleware now rejects oversized bodies with `413` before they're even read), and the six Phase 7 LLM output schemas used Pydantic's default `extra="ignore"` behavior, silently dropping fields outside the contract rather than rejecting them — tightened to `extra="forbid"` via a shared `_StrictOutput` base, including on nested list-item schemas (`InvestigationStep`, `MitreTechniqueSuggestion`), so a response carrying anything unexpected is now `INVALID`, not silently trimmed.

### Prompt injection resistance, and why the delimiters aren't the real defense

Every Phase 7 prompt embeds a rendered incident context block built from alert rationale, IOC values, and other event-derived text — in a real (non-synthetic) deployment, an attacker who can shape logged activity could shape that text. `render_context_block()` now wraps it in explicit `===BEGIN INCIDENT DATA (untrusted)===` / `===END INCIDENT DATA===` markers, and the shared prompt disclaimer explicitly instructs the model to treat anything inside as data, never as instructions to obey.

This is stated as best-effort, not a solved problem — a determined attacker could embed the closing delimiter itself, and no delimiter scheme reliably defeats every adversarial phrasing a sufficiently capable model might be swayed by. The load-bearing mitigation is the schema tightening above: even a fully successful injection can only ever produce text that still has to pass `_StrictOutput` validation, and there is no field a manipulated response could populate that reaches severity, detection, correlation, or an automated action — those stay exclusively deterministic, unchanged since Phase 1. This is the concrete difference between "hardened" and "solved," stated as such rather than oversold.

### Authentication: resolves the one real open question this phase owed

TODO.md's Architecture Decisions section had carried "authentication approach for the dashboard/API" as an open question since it was first written. Resolved here in favor of a single shared bearer token (`API_AUTH_TOKEN`), not user accounts — this project's data model has no multi-tenant concept anywhere in it, so building real user accounts would be pure over-engineering for what's actually a single-operator local tool.

The default is auth *disabled* (empty token) — a deliberate choice, checked against the alternative before deciding: making auth mandatory-on by default would break every existing quick-start command, every Phase 9–13 integration test's `TestClient` call, and CI, none of which send an `Authorization` header. `require_auth` (a FastAPI dependency added to every `/api/v1/*` router at `include_router(..., dependencies=[Depends(require_auth)])`, not touching individual endpoint signatures) is a no-op when unset and does a constant-time comparison (`hmac.compare_digest`) when set — a token is a real secret, not a feature flag, and a naive `==` comparison would leak timing information about how many leading characters matched. `/healthz` and `/metrics` stay unauthenticated regardless, by the same "network-restricted, not app-gated" convention health/metrics endpoints conventionally follow.

The frontend gained a real `AuthGate` component (`src/components/AuthGate.tsx`) wrapping the dashboard routes — not `/status`, which stays reachable the same way `/healthz` does. It probes with one cheap authenticated call on mount; a `401` shows a token-entry form instead of the dashboard, storing the token in `localStorage` (wrapped in try/catch — private-window/blocked-storage browsers degrade to "just send the request unauthenticated and let the backend 401 it," not a crash) via `apiFetch`'s now-automatic `Authorization` header attachment. When no token is configured backend-side (the default), the probe always succeeds and the gate never renders — zero friction for the default path, verified both by an automated test and against a real running Docker backend with the token unset.

### Rate limiting: two tiers, and the process-global test-pollution bug caught before it shipped

`app/core/rate_limit.py` is an in-memory, fixed-window limiter — no Redis, matching the same "in-process, single-worker, documented limitation" pattern Phase 13's metrics registry already established. Two tiers: general (300/min default) for most `/api/v1/*` routes, strict (30/min default) for the two routes TODO.md calls out by name — `POST /api/v1/events/{source_type}` (ingestion) and `POST /api/v1/pipeline/run` (LLM-triggering).

Building this surfaced a real design bug, caught before any test was written against it: the first version constructed both limiters once at import time, reading `settings.rate_limit_*_per_minute` into a frozen `limit` field — meaning a test monkeypatching settings to lower the threshold had no actual effect, since the limiter never re-read it. Fixed by making `RateLimiter.check(key, limit)` accept the limit as a parameter, read fresh from `get_settings()` on every call — the same "no cached config" discipline `require_auth` already followed, which is what made it possible to test at all.

A second, separate bug surfaced immediately after fixing the first: the limiter is genuinely process-global state, and running it against the real test suite tripped the strict-tier limit for unrelated, later tests that happened to call an ingestion endpoint after enough earlier tests had already spent that budget — three real test failures, not hypothetical. Fixed with an autouse `pytest` fixture (`tests/conftest.py`) that resets both limiters before every test. Verified this doesn't just hide the problem: the real backend, hit with 35 real HTTP requests in a row against a live Docker container, returned `201` for the first 30 and `429` for the rest — exactly the configured threshold, confirmed against a running server, not just the mocked test path.

### Container security: the backend was already solid; the frontend's production stage wasn't

`backend/Dockerfile` needed nothing new — already a slim base image, an existing non-root `appuser`, only `EXPOSE 8000`. `frontend/Dockerfile`'s `production` stage (not currently used by `docker-compose.yml`, which runs the `dev` target for hot-reload, but present for Phase 15) ran as root on the privileged port 80. Hardened to run as the image's built-in unprivileged `nginx` user on port 8080, with a new `nginx.conf` redirecting the pid file and temp paths to `/tmp` (the standard "unprivileged nginx" pattern — the default config paths aren't writable by a non-root user). Verified for real: built the `production` target, ran the container, confirmed `whoami` inside it reports `nginx` and a request to the static bundle returns `200`.

### Dependency scanning: blocking, because it's currently clean

`pip-audit` (backend, added as a dev dependency) and `npm audit --audit-level=high` (frontend) both run as new, blocking CI steps — checked locally before deciding blocking was safe: both report zero known vulnerabilities against this project's actual dependency set today. The asymmetry between backend (blocks on anything) and frontend (blocks on high/critical only) is deliberate, not an oversight — npm's ecosystem routinely carries low/moderate advisories in dev-only build tooling that this project has no realistic path to fixing on its own timeline; gating on high+ keeps the signal meaningful without chasing noise outside this project's control.

### Security headers

A small addition to the existing Phase 13 request middleware (not a new one — the middleware already touched every response on its way out, so this is the natural place): `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` on every response, and `Content-Security-Policy: default-src 'none'` on everything except `/docs`/`/redoc` — a strict CSP there would break FastAPI's own Swagger/ReDoc UI, which loads its assets from a CDN. Verified live: present on both a normal `200` and a `404` error response (the middleware wraps every response, including ones produced by the exception handlers), and confirmed absent specifically on `/docs`.

## How it all connects

```
app/core/config.py — api_auth_token, rate_limit_*_per_minute, max_request_body_bytes
        │
        ├──→ app/api/deps.py :: require_auth
        │        │  Depends() on every /api/v1/* router's include_router() call
        │        │  no-op when api_auth_token is empty (the default)
        │        └──→ raises UnauthorizedError → 401, WWW-Authenticate: Bearer
        │
        ├──→ app/main.py :: security_gate middleware
        │        │  Content-Length > max_request_body_bytes → 413
        │        └──→ app/core/rate_limit.py :: check_rate_limit()
        │                 strict tier: POST /events/{source_type}, POST /pipeline/run
        │                 general tier: everything else under /api/v1/*
        │                 → 429 + Retry-After, or falls through to routing
        │
        └──→ app/main.py :: request_id_and_metrics middleware (Phase 13, extended)
                 _apply_security_headers() on every response, including
                 401/413/429/404/500 — this runs outermost, after the
                 response (from any layer) has already been built

app/triage/schemas.py — _StrictOutput (extra="forbid")
        │
        └──← app/llm/validation.py :: validate_structured_output()
                 the single choke point every LLM response passes before
                 persistence — unchanged mechanism (Phase 6), tightened contract

app/triage/context.py :: render_context_block()
        │  wraps untrusted incident data in BEGIN/END markers
        └──← app/triage/prompts.py :: _DISCLAIMER
                 instructs the model to treat delimited content as data only

frontend/src/api/client.ts :: apiFetch()
        │  attaches Authorization: Bearer <token> from localStorage
        └──← frontend/src/components/AuthGate.tsx
                 wraps the dashboard routes (not /status); shows a token
                 form on a 401 probe, otherwise renders immediately
```

## Key decisions and why

| Decision | Reasoning |
|---|---|
| Auth disabled by default (empty `API_AUTH_TOKEN`) | Mandatory-on would break every existing quick-start command and test client; opt-in matches this project's "no required cloud dependency, clone and run" pitch while still being real, verified protection when a reviewer turns it on |
| Single shared bearer token, not user accounts | Resolves the TODO.md open question in the direction proportionate to a single-operator local tool with no multi-tenant concept anywhere in its data model |
| `hmac.compare_digest` for the token check | A token is a real secret; a naive `==` string comparison leaks timing information about how many characters matched |
| `require_auth` wired via `include_router(..., dependencies=...)`, not per-endpoint | Zero changes to any of the ~40 existing endpoint functions; the auth boundary is declared once, at the router level, where it's also trivially auditable (see main.py's include_router block) |
| `RateLimiter.check(key, limit)` reads settings fresh per call, not frozen at construction | The first version froze the limit at import time, silently making it untestable — caught before any test was written against it, not after a test mysteriously failed |
| Autouse rate-limiter reset fixture in `tests/conftest.py` | The limiter is real process-global state; without a reset, three real (not hypothetical) test failures resulted from unrelated earlier tests spending a later test's rate budget |
| Prompt-injection delimiters framed explicitly as best-effort, with schema enforcement named as the real backstop | Overclaiming "prompt injection resistant" would be dishonest — no delimiter scheme reliably defeats adversarial phrasing; what actually bounds the damage is that manipulated output still can't populate a field that reaches a deterministic or automated system |
| `npm audit --audit-level=high`, but `pip-audit` fully blocking | Not an inconsistency — npm's ecosystem carries far more low/moderate dev-tooling advisories outside this project's control than the backend's; gating each at the threshold that keeps its own signal meaningful, not blindly applying the same rule to both |
| Frontend production Dockerfile hardened even though `docker-compose.yml` doesn't use that target | It's the stage that would actually get deployed (Phase 15); leaving it running as root because "nothing uses it yet" would just be deferring a known gap into a future phase's blind spot |
| ASVS self-review as a table in this document, not a new top-level doc | Matches this project's established pattern (Phase 5's correlation strategy, Phase 8's MITRE source) of keeping phase-specific analysis inside that phase's own report rather than proliferating `docs/*.md` files |

## `[STRETCH]` Self-review against an OWASP ASVS subset

| Area | Posture | Evidence |
|---|---|---|
| Authentication | Single shared bearer token, opt-in, constant-time comparison | `app/api/deps.py::require_auth`, `TestAuthEnabled`/`TestAuthDisabledByDefault` |
| Session management | N/A — stateless bearer token, no server-side session state to fixate or hijack | — |
| Input validation | Every request body schema-validated (Phase 9); LLM output now `extra="forbid"` (this phase); request body size capped | `app/triage/schemas.py`, `security_gate` middleware |
| Output encoding | FastAPI/Pydantic JSON serialization throughout; no raw HTML rendering anywhere in the API surface, so XSS via API responses isn't a live vector | — |
| Error handling | Every error path (404, 422, 401, 413, 429, 500) returns the same structured envelope; the 500 path logs a full traceback server-side but never leaks internals to the client (`"Internal server error"`, not the exception message) | `app/main.py` exception handlers |
| Logging | Structured JSON throughout (Phase 13), request-ID-correlated; no secrets logged (`api_auth_token` never appears in any log line — checked directly, not assumed) | `app/core/logging.py`, `app/core/request_context.py` |
| Dependency management | `pip-audit` and `npm audit` now block CI on any/high-severity finding respectively | `.github/workflows/ci.yml` |
| Secrets management | `.env`/`.env.*` gitignored, `.env.example` carries only placeholder values, every setting flows through one audited `config.py` surface | `.gitignore`, `app/core/config.py` |
| Rate limiting / resource exhaustion | Two-tier in-memory limiter; request body size cap; verified live against a running server | `app/core/rate_limit.py` |
| Transport security | **Explicit gap, not hidden**: this project runs plain HTTP for local/demo use — no TLS anywhere in `docker-compose.yml`. Accepted as a local-only limitation; TLS termination is a real deployment's job (a reverse proxy, a real host), out of scope for a `docker compose up` local demo | `docker-compose.yml` |

## Verification performed

- Full backend suite after this phase: 383 passed, 1 skipped (the opportunistic live-Ollama test), 98% line coverage — every new/modified module (`app/api/deps.py`, `app/core/exceptions.py`, `app/core/rate_limit.py`, `app/main.py`) at 100%. `ruff check`/`ruff format --check` clean.
- Frontend: 20 tests passing (9 new — `AuthGate.test.tsx`, `client.test.ts`), `npm run lint`, `npm run format:check`, `npm run build` clean. (A real, unrelated-to-this-phase environment quirk was hit and fixed along the way: Node 20+'s own experimental global `localStorage` shadows jsdom's working one under `vitest`, silently breaking every test that touched storage — fixed by disabling it for the test runner's own process via `NODE_OPTIONS=--no-experimental-webstorage` in `package.json`'s `test` script, not something that affects the app in a real browser.)
- `pip-audit` and `npm audit --audit-level=high` both run clean locally before being wired into CI as blocking steps.
- Frontend production Docker image built and run for real: confirmed `whoami` inside the container reports the unprivileged `nginx` user, and a request to the served bundle returns `200` on port 8080.
- Live smoke test against the actual running Docker backend (not just `pytest`): security headers present on every response including `/healthz`; auth correctly rejects a missing/wrong token and accepts the right one when `API_AUTH_TOKEN` is set, and imposes no friction at all when it's unset (the default); 35 real HTTP requests against the strict-tier ingestion endpoint returned `201` for the first 30 and `429` for the remaining 5 — the configured threshold, confirmed against a live process.

## What Phase 14 deliberately does not include

**No TLS** — plain HTTP throughout, an explicit, documented limitation rather than a hidden gap (see the ASVS table above); appropriate for a local `docker compose up` demo, not a claim this is production-ready as shipped. **No user accounts, roles, or permissions** — a single shared token is the proportionate choice for a project with no multi-tenant concept anywhere in its data model; revisit only if that changes. **No CSRF protection** — this is a token-authenticated JSON API with no cookie-based session and no browser-form-based state-changing requests, so CSRF (which relies on ambient cookie auth) isn't a live vector here. **No WAF-style request inspection, IP allowlisting, or anomaly detection** — out of scope for an application-layer hardening pass; that's infrastructure a real deployment would layer on top, not something this codebase should reimplement. **No solved prompt-injection defense** — stated plainly in the "What was built" section above, not a gap discovered later: the delimiters are best-effort structural hardening, and the schema-enforcement backstop is what actually bounds the damage, not a claim that injection is impossible. **No mutation testing of the new security code** — matches Phase 11's stated boundary on this; ordinary test coverage (100% on every new module) is the bar this project has consistently used elsewhere.
