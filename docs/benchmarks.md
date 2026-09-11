# Benchmarks

Measured throughput and latency for SITA's pipeline stages and REST API. See [DEF.md § Phase 12](../Documentation/DEF.md#phase-12-performance-and-evaluation) for the harness design and [evaluation_methodology.md](evaluation_methodology.md) for correctness (precision/recall) numbers — this document is speed only.

## What's actually being measured

SITA's pipeline stages (ingestion, detection, IOC extraction, MITRE mapping, correlation) are **batch jobs**, not a per-event streaming service — there is no persistent worker consuming one event at a time. Reporting a single per-event "latency" number would misrepresent that architecture. Instead, each stage is measured as batch wall-clock time over a fixed load, with throughput (units/sec) derived from it — an honest reflection of how the system actually runs.

The REST API, by contrast, *is* a real per-request service, so its numbers are reported the standard way: p50/p95/p99 latency percentiles under repeated real HTTP requests through FastAPI's `TestClient`. The list/search endpoints benchmarked here (`GET /incidents`, `GET /alerts`, `GET /iocs`) double as the "database query performance for common access patterns" measurement TODO.md asks for — a separate benchmark would just be measuring the same query paths a second time.

## Setup

Run via `uv run python -m app.benchmark.cli` from `backend/`. Every run builds its own throwaway `sqlite:///:memory:` database and bulk-generates disposable load-test events on the fly (`app/benchmark/generate_load.py` — deliberately not checked into git, unlike `data/eval/`, since this is regenerated fresh every run rather than a reviewable fixture). This never touches the configured `DATABASE_URL`, for the same reason the evaluation harness doesn't: throwaway load data must never land in real/demo data.

This run: 1500 events (500 each of auth, network, endpoint), 50 requests per API endpoint, on a single developer machine (not a dedicated benchmarking environment — these are directional numbers, not SLA guarantees).

## Pipeline stage throughput

| Stage | Wall-clock | Units processed | Throughput |
|---|---|---|---|
| Ingestion | 0.0542s | 1500 events | ~27,700 events/sec |
| Detection | 0.0816s | 1500 events | ~18,373 events/sec |
| IOC extraction | 1.1896s | 1500 events | ~1,261 events/sec |
| MITRE mapping | 0.1233s | 821 alerts | ~6,657 alerts/sec |
| Correlation | 1.8993s | 821 alerts | ~432 alerts/sec |
| Triage orchestration (Mock) | 0.1394s | 16 incidents | ~1.45 ms/call overhead |

IOC extraction and correlation are the two clear cost centers, both by design rather than accident: IOC extraction runs multiple regex scans per event across every extractor type, and correlation compares each new alert against the existing open-incident window (Phase 5's weighted scoring) rather than doing simple grouping. Neither is a bottleneck at this scale (~2 seconds for a 1500-event batch), but they're the stages that would need attention first if throughput requirements grew by an order of magnitude.

`triage_orchestration_mock` measures pipeline and validation overhead only — `MockProvider` returns a canned response in-process, sub-millisecond, so this is *not* a meaningful "LLM latency" number on its own. Real per-task LLM latency (from a live Ollama run) is reported below instead.

## API latency (p50 / p95 / p99, 50 requests/endpoint)

| Endpoint | p50 | p95 | p99 |
|---|---|---|---|
| `GET /incidents?limit=25` | 2.64 ms | 8.73 ms | 13.63 ms |
| `GET /alerts?limit=25` | 1.51 ms | 1.76 ms | 4.60 ms |
| `GET /iocs?search=10.9&limit=25` | 6.44 ms | 6.65 ms | 8.76 ms |

Against SQLite, in-process, with no network hop — these numbers establish a floor, not a production SLA; expect materially higher latency (and a more meaningful test of index usage) against a real networked Postgres instance under concurrent load, which this benchmark does not simulate.

## Real LLM latency and token usage (live Ollama, opportunistic)

`MockProvider`'s in-process timing above isn't a real LLM latency number, so real numbers come from the evaluation harness's opportunistic live-Ollama run instead (see [evaluation_methodology.md](evaluation_methodology.md) for the full grounding-quality discussion — this is the latency/token slice of that same run):

| Metric | Result |
|---|---|
| Model | `qwen2.5:0.5b` (hand-verification model, not the recommended default) |
| Per-task latency | 533 – 3906 ms |
| Prompt tokens per task | ~1200 – 1251 |
| Completion tokens per task | 58 – 317 |

This is one small model on one developer machine, run opportunistically when Ollama is reachable (the pattern established in Phase 6) — not a benchmark of the project's recommended `llama3.1:8b-instruct-q4_K_M` default, which is materially larger and was not benchmarked here.

## Scaling to 10x load (post-roadmap)

The original run above (1500 events) is a "fixed, moderate scale" per this project's own earlier assessment, "never pushed toward a breaking point" — WHATNEXT.md named this explicitly. Same harness, `--events-per-source 5000` (15,000 events total, 10x the original):

| Stage | 1,500 events | 15,000 events | Throughput change |
|---|---|---|---|
| Ingestion | ~27,700 events/sec | ~29,692 events/sec | steady (as expected — a straightforward bulk insert) |
| Detection | ~18,373 events/sec | ~4,653 events/sec | ~4x worse |
| IOC extraction | ~1,261 events/sec | ~506 events/sec | ~2.5x worse |
| MITRE mapping | ~6,657 alerts/sec | ~4,245 alerts/sec | modest |
| Correlation | ~432 alerts/sec | ~77 alerts/sec | **~5.6x worse** |

Correlation is the real finding: 1.90s wall-clock at 1500 events vs. **55.9s** at 15,000 — roughly 30x slower wall-clock time for 10x the data, consistent with the super-linear (closer to quadratic than linear) scaling this project's own original benchmarks writeup predicted but had never measured ("the two stages that would need attention first if throughput requirements grew by an order of magnitude"). The cause is architectural, not a bug: `run_correlation()` compares each new alert against every open/investigating candidate incident in its scoring window (Phase 5's weighted scoring), so cost grows with the number of open incidents accumulated so far, not just the new alert count. A genuine attempt at `--events-per-source 20000` (60,000 events, 40x baseline) did not complete within 6 minutes and was killed rather than waited out further — direct, concrete evidence of where this design's real breaking point lies, not a guess. Fixing this (e.g., bounding the candidate-incident lookup window more aggressively, or indexing/pre-filtering candidates) is future work this measurement now makes concrete rather than speculative — not undertaken here, since diagnosing was this pass's scope, not re-architecting Phase 5's scoring engine.

## Concurrent write load — SQLite vs. Postgres (post-roadmap)

The numbers above measure sequential throughput against a single connection — never pushed toward a breaking point or tested under concurrent write load, a real gap this project's own WHATNEXT.md named explicitly. `app/benchmark/concurrent_load.py` (`uv run python -m app.benchmark.concurrent_load_cli`) fires N threads at `POST /api/v1/events/auth` concurrently through a real ASGI `TestClient`, against either a throwaway in-memory SQLite database (the shape every solo-dev/demo deployment of this project actually uses) or a real, disposable Postgres database (created and dropped for this run, never the configured `DATABASE_URL` or `sita-postgres-1`'s real `sita` database) — the same comparison this project's own architecture already assumes (SQLite for solo local dev, Postgres for anything shared) but had never actually measured.

| Database | Concurrency | Requests | Successful | Failed | Events/sec |
|---|---|---|---|---|---|
| SQLite | 1 | 3 | 3 | 0 | ~1,577 |
| SQLite | 10 | 30 | 3 | **27** | ~382 |
| Postgres | 1 | 3 | 3 | 0 | ~1,815 |
| Postgres | 10 | 30 | **30** | 0 | ~1,654 |

At concurrency 10 — both runs comfortably under the 30/minute strict rate limit, so this isolates database-layer behavior specifically, not rate limiting — SQLite fails 27 of 30 concurrent write requests outright (`sqlite3.OperationalError: cannot commit transaction - SQL statements in progress`, and in another run, `sqlite3.InterfaceError: bad parameter or other API misuse` — different symptoms of the same root cause: Python's `sqlite3` driver is not safe for genuinely simultaneous multi-threaded use against one shared connection, which is exactly what `StaticPool`'s single shared `:memory:` connection is). Postgres, with a real connection pool, handles the identical load at 100% success. This is a real, concrete confirmation of a decision this project already made for other reasons (Postgres in `docker-compose.yml`, SQLite only for the zero-setup local-dev path) — not a new problem, but the first time it's been actually measured rather than assumed. At concurrency 50 (150 requests), both databases show most requests failing, but for a different, non-database reason: 150 requests within a few hundred milliseconds exceeds `RATE_LIMIT_STRICT_PER_MINUTE`'s default of 30, so the rate limiter — not the database — is the first thing to reject load at that volume, a reassuring finding about defense-in-depth rather than a new gap.

**Not measured**: real concurrent load against a networked (non-`127.0.0.1`) Postgres instance, or against `docker-compose.prod.yml`'s multi-worker backend specifically (this harness runs in-process, single Python process, regardless of which database it targets).

## Reproducing this

```bash
cd backend
uv run python -m app.benchmark.cli --events-per-source 500 --api-requests 50
uv run pytest tests/integration/test_benchmark_harness.py -q   # smoke test only, no numbers asserted

# Concurrent write-load stress test (post-roadmap)
uv run python -m app.benchmark.concurrent_load_cli --concurrency 10 --requests-per-worker 3
# Against a real, disposable Postgres database instead of throwaway SQLite:
uv run python -m app.benchmark.concurrent_load_cli --concurrency 10 --requests-per-worker 3 \
  --database-url postgresql+psycopg://sita:sita@127.0.0.1:5432/sita_stress_test
uv run pytest tests/integration/test_concurrent_load.py -q   # smoke test only, no numbers asserted
```
