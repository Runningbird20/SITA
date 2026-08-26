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

## Reproducing this

```bash
cd backend
uv run python -m app.benchmark.cli --events-per-source 500 --api-requests 50
uv run pytest tests/integration/test_benchmark_harness.py -q   # smoke test only, no numbers asserted
```
