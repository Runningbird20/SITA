# Phase 11: Testing — Completion Report

Status: complete. See [DEF.md § Phase 11](DEF.md#phase-11-testing) for the specific coverage gaps found and closed, the dual-dialect fixture design, and the status log — this document is the narrative of how it got done and why. For the checklist itself, see [TODO.md](../TODO.md#phase-11-testing).

## Goal

Ten phases of incremental, per-phase testing discipline had already produced a large suite — 311 backend tests, 98% line coverage, before this phase touched anything. TODO.md's own framing for Phase 11 is explicit about this: "largely produced incrementally in earlier phases — this phase closes gaps and raises coverage." The goal wasn't to write a test suite; it was to audit the one that already existed, measure it honestly, and fix what measurement found — plus resolve the one real architectural question TODO.md had been carrying since Phase 0: should CI test against Postgres, SQLite, or both.

## What was built

### An audit, not a guess

Every addition in this phase traces to a specific line `pytest --cov-report=term-missing` named as unexecuted, checked *before* writing anything — not a generic "let's add more tests" pass. This mattered in practice: my first instinct for the correlation-scoring gap was wrong. I assumed an incident signature with no activity window yet would score zero time-proximity — writing the test with that assertion failed immediately, because `_time_gap_seconds` actually treats "no window to conflict with" as a zero *gap*, which then scores the *full* time weight. The failing test caught my wrong assumption about the code, not a bug in the code — exactly the value of writing the test and running it rather than asserting confidence about behavior never observed.

### Failure-injection: DB unavailable and LLM unavailable, at the layer that matters

TODO.md asked for failure-case tests confirming "graceful degradation, not crashes" for both. The DB case was a genuine, single, findable gap: `GET /healthz`'s except-branch had literally never run under test (81% on that one small file). The LLM case was subtler — Phase 6 already thoroughly proved `LLMProvider.generate()` never raises, at the provider layer. What didn't exist was proof of the same claim one layer up, at `run_triage()` — the function real callers (the CLI, the pipeline-trigger endpoint) actually invoke. `TestLLMUnavailableDegradesGracefully` closes that: a `MockProvider` configured to raise on every call, run through the real pipeline, confirming not just "no exception" but that the triggering incident's deterministic data — status, severity, alert count — is exactly what detection and correlation left it, byte for byte.

### The one test that runs the whole chain against real data

Every dataset-backed integration test from Phases 3–5 stops at correlation — reasonably, since MITRE mapping and triage didn't exist yet when those tests were written. Nothing had gone back to extend the chain once they did. `test_full_pipeline_against_datasets.py` is that test now: ingest → detect → extract IOCs → MITRE-map → correlate → triage, against the real checked-in multi-stage scenario (`data/synthetic_events/scenarios/brute_force_to_lateral_movement/`), ending with genuine assertions about the fully-analyzed incident — a real rule-sourced MITRE mapping surviving all the way through, real `AnalysisResult` rows, deterministic and AI-attributed data coexisting and distinguishable by construction, not just by convention.

### API filters that were documented but never actually called

The most concerning class of gap this phase found: several Phase 9 REST API query parameters — `Alert.status`, `SecurityEvent.since`/`until`, `IOC.validation_status`, `Recommendation.alert_id`/`source`, `AnalysisResult`'s `alert_id`-scoped branch — were real, working, documented filters that no passing test had ever actually exercised. Not low coverage — zero calls. A client could have been relying on any of these while the only evidence they worked was that the code looked plausible. Each got one targeted test. `GET /alerts/{id}/mitre-techniques`'s own 404 branch (a separate `NotFoundError` raise from the plain `GET /alerts/{id}` one) was in the same state and got the same treatment.

### IOC extractors brought up to the standard `TestIPv4` already set

`TestIPv4` in `test_ioc_extractors.py` already tested the full pattern other extractors' tests hadn't caught up to: a public match, a filtered (private/reserved) match, deduplication, and malformed-input rejection. `ipv6.py` was the worst gap (79%) for an interesting reason: its existing loopback test used input (`"bound to ::1"`) that never actually reached the filtering logic at all, because a bare `::` preceded by whitespace fails the regex's own `\b` word-boundary anchor before the loopback check ever runs — confirmed by hand with a quick interactive check before writing the replacement, rather than assumed. `domain`, `email`, `file_hash`, and `url` each had exactly one untested branch (their dedup check) and got one test each, matching `TestIPv4`'s existing shape exactly rather than inventing a new pattern.

### Fixture consolidation: one real duplication, found and fixed

TODO.md asked to "avoid duplicated ad-hoc data." Auditing for this (not just assuming it was needed) found exactly one real instance: `_brute_force_events()` — a 10-event single-source auth-failure burst — defined near-identically in three files (`test_correlation_pipeline.py`, `test_mitre_pipeline.py`, `test_triage_pipeline.py`), each with its own copy of the same `NOW` constant. Consolidated into `brute_force_events`/`BRUTE_FORCE_NOW` in `tests/conftest.py`. Phase 9's `seed_full_incident()` in `tests/integration/conftest.py` was already the equivalent consolidation for API-layer tests and needed nothing further — the audit confirmed that rather than assuming it.

### `[[postgres-vs-sqlite]]`: resolved with a real, verified mechanism

This is the biggest single piece of work in the phase. The naive approach — point a new CI job's `DATABASE_URL` at Postgres and run `pytest` — would have been a lie: every existing fixture (`db_session`, the API `client` fixture, every CLI test's local engine) hardcodes `sqlite:///:memory:` and completely ignores `DATABASE_URL`. That CI job would have looked like it verified Postgres while silently testing SQLite the entire time. Caught before it shipped, by checking what the fixtures actually did rather than trusting that setting an env var would be enough.

The real fix: `db_session` in `tests/conftest.py` now branches on a *new*, distinct environment variable, `TEST_POSTGRES_URL` — never `DATABASE_URL`, so a developer's ordinary `.env` can never accidentally redirect the test suite at a real database. When set, it connects to that Postgres instance and wraps each test in `Session(bind=connection, join_transaction_mode="create_savepoint")` — SQLAlchemy 2.0's built-in support for exactly this pattern, a `SAVEPOINT` per test so a test's own `db_session.commit()` calls never escape the outer transaction, which is rolled back after the test regardless of outcome. Before trusting this in CI, it was run against a disposable scratch database created for exactly this purpose (`sita_test`, on the local docker-compose Postgres, dropped immediately after): 254 tests passed for real against Postgres, and the tables were queried directly afterward to confirm zero leftover rows — the isolation claim was checked, not assumed.

## How it all connects

```
pytest --cov=app --cov-report=term-missing   (run first, gaps identified)
        │
        ├──→ app/api/health.py's except-branch      → test_health_api.py
        ├──→ run_triage() + LLM failure               → TestLLMUnavailableDegradesGracefully
        ├──→ no full-chain dataset test               → test_full_pipeline_against_datasets.py
        ├──→ untested API filters/404s                → targeted additions, Phase 9 test files
        ├──→ IOC extractor branches                   → test_ioc_extractors.py, TestIPv4 parity
        ├──→ correlation scoring/title/host-extraction → targeted additions
        └──→ duplicated _brute_force_events()          → tests/conftest.py :: brute_force_events

tests/conftest.py :: db_session
        │  TEST_POSTGRES_URL unset → sqlite:///:memory: (unchanged default)
        │  TEST_POSTGRES_URL set   → real Postgres, SAVEPOINT-per-test
        ▼
.github/workflows/ci.yml
        ├── backend-test           (SQLite, --cov-fail-under=95, step summary)
        ├── backend-test-postgres  (TEST_POSTGRES_URL set, same suite)
        └── frontend               (+ npm run test, previously missing)
```

## Key decisions and why

| Decision | Reasoning |
|---|---|
| Coverage measured before deciding what to test, not after | The whole point of an audit phase is that the gaps come from evidence, not intuition — several assumptions about what "must already be tested" (the DB failure path, several API filters) turned out to be wrong |
| `TEST_POSTGRES_URL`, a variable distinct from `DATABASE_URL` | The one property that makes this safe: it must be structurally impossible for a developer's normal environment to accidentally point the test suite at a real database. A shared variable name would have made that one `.env` line away from happening |
| SAVEPOINT-per-test via SQLAlchemy 2.0's `join_transaction_mode`, not a fresh schema per test | Standard, well-understood pattern for isolating tests against a real database without the cost of recreating schema per test; verified directly against a scratch database before being trusted in CI, not assumed to work because it's documented behavior |
| Verified the rollback claim by querying tables afterward, not by trusting the pattern | "Isolation should work" and "isolation does work, confirmed by direct query" are different claims; only the second one is something this project's own verification discipline (established since Phase 4) would accept |
| Not every coverage gap was chased — CLI `if __name__` guards left alone | Diminishing returns: covering `sys.exit(main())` guard lines requires subprocess-level invocation for near-zero value; the phase stopped at genuinely meaningful branches (failure paths, filters, extractor edge cases), not 100% for its own sake |
| `backend-test-postgres` doesn't claim to cover the whole suite | Tests with their own hardcoded engines (CLI tests, API `TestClient` tests) still run in that job but still hit SQLite — stated plainly in both the CI comments and here, rather than left to imply broader coverage than actually exists |
| Frontend `npm run test` added to CI even though Phase 11's task list is backend-only | Found during the same "audit what's actually covered" pass this phase is built around; Phase 10 added a real Vitest suite that nothing was running in CI — leaving it unrun once discovered would have contradicted the phase's own purpose |

## Verification performed

- Full backend suite: 338 passed, 1 skipped (the opportunistic live-Ollama test), 99.06% line coverage (`pytest --cov=app --cov-report=term-missing`), `ruff check`/`ruff format --check` clean.
- The same suite's `db_session`-based subset (254 tests: most of `tests/unit/` plus the dataset-backed integration tests) run for real against a live Postgres instance via `TEST_POSTGRES_URL`, using a disposable scratch database created and dropped specifically for this verification — all 254 passed, and a direct `SELECT count(*)` against several tables afterward confirmed zero leftover rows.
- The exact CI recipe (`--cov-fail-under=95`, `--cov-report=xml`) run locally and confirmed to both pass and correctly enforce the threshold (`Required test coverage of 95% reached. Total coverage: 99.06%`).
- `.github/workflows/ci.yml` validated as well-formed YAML and its job graph confirmed (`backend-lint`, `backend-test`, `backend-test-postgres`, `frontend`) — not run through actual GitHub Actions in this environment, so the job succeeding on GitHub's runners specifically is inferred from the identical commands succeeding locally, not independently confirmed.
- Frontend: `npm run test` (11 passed), `npm run lint`, `npm run format:check`, `npm run build` all clean.

## What Phase 11 deliberately does not include

**Not 100% line coverage** — the remaining ~1% is almost entirely `if __name__ == "__main__":` CLI guard lines, where the cost (subprocess-level test invocation) vastly exceeds the value for a handful of one-line guards. **No dialect coverage for tests with their own hardcoded engine construction** (CLI tests, API `TestClient` tests) — extending `TEST_POSTGRES_URL` support to those would mean touching ~10 more fixture-construction sites for a smaller marginal return than the `db_session`-based subset already provides; left as a known, stated boundary rather than silently claimed. **No mutation testing or property-based testing** — not asked for in TODO.md's task list, and would be a meaningfully larger scope addition than "close gaps and raise coverage." **No load/performance testing** — that's Phase 12's job. **No frontend coverage threshold in CI** — Phase 10's Vitest suite now runs in CI, but TODO.md's coverage-threshold task was specifically about the backend; adding a frontend threshold wasn't asked for and the current frontend suite (11 tests, mostly pure functions and small components) doesn't yet have enough surface for a threshold number to mean much.
