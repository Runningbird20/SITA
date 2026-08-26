# Phase 12: Performance and Evaluation — Completion Report

Status: complete. See [DEF.md § Phase 12](DEF.md#phase-12-performance-and-evaluation) for the schema/scope definitions and the implemented-status log, and [TODO.md](../TODO.md#phase-12-performance-and-evaluation) for the itemized checklist. See [docs/evaluation_methodology.md](../docs/evaluation_methodology.md) and [docs/benchmarks.md](../docs/benchmarks.md) for the full results.

## Goal

Eleven phases had produced a working, tested system, but no phase had ever asked "how fast is it" or "how correct is it against data it wasn't tuned against." TODO.md frames this phase explicitly as being about resume credibility — turning "a rule fires when it should" (true since Phase 3, but only ever checked against the same dataset the rule was written against) into a measured, defensible, held-out number. It's the last phase before Phase 13–15 (observability, hardening, deployment) start treating the system as something to ship, so it's also the last natural point to catch a rule or extractor that only *looks* correct because it's only ever been tested against its own tuning data.

## What was built

### Two packages for two different questions

`app/benchmark/` (how fast) and `app/evaluation/` (how correct) are separate packages, even though TODO.md bundles both under one phase and both ultimately feed the same results write-up. They answer genuinely different questions with different tooling — one times a large disposable load, the other scores a small, precisely-labeled dataset — and conflating them into one module would have made both harder to read.

### `data/eval/`: a generated, held-out dataset

`app/evaluation/generate_dataset.py` produces 33 detection cases (all 7 rules, 3 positive + 2 negative each, except `impossible_travel` at 2+1 due to the GeoIP stub constraint), 12 IOC cases (one positive per `IOCType` plus 3 targeted negative cases), and 2 correlation cases. Generated rather than hand-written specifically so the ground-truth labels can never drift from the event data — the same function that builds a case's events also emits its label. Every case carries a unique marker (a host, IP, or username) baked into its events, so the harness can find "this case's own events" by direct lookup rather than by parsing rule rationale text or guessing from timestamps.

Three real bugs surfaced while building this and were fixed before any number was computed: two `password_spraying` cases sharing one host (causing cross-case pooling under a different rule's host-based grouping), one positive case's user count coincidentally also crossing a *different* rule's threshold (an unintended second alert), and one IOC case's `source_type` field not matching the event shape it was actually built with (silently dropped by ingestion). All three found by running the generator and inspecting its actual output — not by reasoning about the code in the abstract. Full account in [docs/evaluation_methodology.md](../docs/evaluation_methodology.md).

### The evaluation harness, and one methodology bug caught before publishing

`app/evaluation/harness.py`'s `run_evaluation()` ingests the eval dataset, runs the real pipeline (detection → IOC extraction → correlation), and scores each case. The IOC-scoring design went through one real revision: the first version compared the full set of extracted IOCs against the full expected set across the whole dataset, and produced precision as low as 2.3% for `ipv4` — because every legitimately-extracted IOC that simply wasn't the "point" of some other case (every auth event's own `source_ip`, for instance) counted as a false positive. That's measuring "did you extract literally everything in the dataset," not "did extraction work correctly for this case" — recognized as a real methodological flaw and redesigned to per-case, per-event attribution before any number was reported.

### `app/evaluation/ai_grounding.py`: resolving the one open architectural question this phase owed

TODO.md's Architecture Decisions section had carried "How to evaluate AI-generated triage" as unresolved since Phase 7. It's resolved here in favor of automated grounding checks over manual rubric scoring, for a concrete reason rather than a preference: this project's actual workflow is an agentic session, not a staffed evaluation team, so a human 1–5 rater was never really available — stated plainly rather than skipped or faked. The check itself is two things: does AI-generated summary/hypothesis text mention a real entity or IOC identifier from the incident (a weak-but-real anti-hallucination signal), and does the AI's suggested MITRE techniques overlap with Phase 8's deterministic, rule-mapped techniques for the same incident.

This ran for real against a live Ollama instance (`qwen2.5:0.5b`) over the eval dataset's multi-stage incident, and produced a genuinely unflattering, honestly-reported result: all 6 tasks returned schema-valid output, but the grounding rate was 0.0 (none of the 5 checked text outputs mentioned a real identifier) and `attack_classification` hallucinated a `"ransomware"` category with zero supporting evidence in the data. MITRE overlap was 1.0. This is real, measured evidence for exactly the principle this project's `CLAUDE.md` states as non-negotiable — the LLM is never the sole source of truth for a security decision — not a hypothetical justification for it.

### `app/benchmark/`: throughput and latency, honestly framed

`generate_load.py` bulk-generates disposable load (deliberately not checked into git, unlike `data/eval/` — regenerated fresh every run). `harness.py`'s `run_benchmark()` times each pipeline stage as batch wall-clock time with derived throughput, explicitly not a per-event streaming latency, because the pipelines are batch jobs and reporting a fake per-event number would misrepresent the architecture. It then measures real API latency percentiles (p50/p95/p99) via FastAPI's `TestClient` against `GET /incidents`, `GET /alerts`, and `GET /iocs?search=`, which doubles as the "database query performance for common access patterns" measurement TODO.md separately asks for.

`MockProvider`'s in-process triage timing is reported but explicitly labeled as pipeline/validation overhead, not LLM latency — real per-task latency and token usage come from the same live-Ollama grounding run above (533–3906ms, ~1200–1250 prompt tokens, 58–317 completion tokens per task), reused rather than re-measured, since re-running the same live call twice for two different documents would be redundant.

## How it all connects

```
app/evaluation/generate_dataset.py
        │  (checked in, deterministic, no randomness)
        ▼
data/eval/{events,scenarios}/*.jsonl + ground_truth.json   (checked in)
        │
        ▼
app/evaluation/harness.py :: run_evaluation()
        │  ingest → detect → ioc_extraction → correlate → score each case
        ├──→ detection_by_rule / detection_overall   (precision/recall/F1)
        ├──→ ioc_by_type / ioc_overall                (precision/recall/F1)
        └──→ correlation_accuracy / correlation_failures
        │
        ▼
app/evaluation/cli.py  (isolated in-memory SQLite, never DATABASE_URL)
        │
        └──→ tests/integration/test_evaluation_harness.py  (regression-locked)

app/evaluation/ai_grounding.py :: evaluate_grounding()
        │  runs against a real triage report from run_triage() + live OllamaProvider
        └──→ grounding_rate / mitre_overlap_rate   (opportunistic, skips cleanly if unreachable)

app/benchmark/generate_load.py  (disposable, regenerated per run)
        ▼
app/benchmark/harness.py :: run_benchmark()
        │  isolated in-memory SQLite (StaticPool — TestClient shares the same DB)
        ├──→ per-stage StageResult (ingestion/detection/ioc/mitre/correlation throughput)
        ├──→ per-endpoint LatencyPercentiles (real TestClient HTTP requests)
        └──→ triage_mock_latency_ms  (orchestration overhead only, not LLM latency)
        │
        └──→ tests/integration/test_benchmark_harness.py  (smoke test only)

docs/evaluation_methodology.md   ← results + methodology write-up
docs/benchmarks.md               ← results + methodology write-up
```

## Key decisions and why

| Decision | Reasoning |
|---|---|
| Two separate packages (`app/benchmark/`, `app/evaluation/`), not one | They answer different questions with different tooling (large disposable load vs. small precisely-labeled dataset) even though TODO.md bundles them into one phase |
| Eval dataset generated by a script, checked in as static output | Guarantees ground truth can never drift from event data (same function emits both); the generator is reviewable as code, the output is what the harness actually reads, so running an evaluation never depends on regenerating data first |
| IOC evaluation redesigned to per-case attribution mid-phase | The global-set-comparison design produced misleading numbers (2.3% precision) by counting correctly-extracted-but-unlisted IOCs as false positives — caught and fixed before any number was published, not after |
| `impossible_travel`'s eval cases reuse the `StaticGeoIPResolver`'s fixed IPs | Stated as a known limitation rather than hidden — there's no way to build a genuinely independent case for that one rule without either reusing the stub or extending it, and extending it was out of scope for this phase |
| AI evaluation via automated grounding checks, not manual rubric scoring | Resolves the Phase 7-era open question with the actual constraint stated plainly: no human rater exists in this project's agentic workflow, so "manual scoring" was never really an option |
| Ran the grounding check against a real, small (`qwen2.5:0.5b`) Ollama model rather than only against Mock | `MockProvider`'s canned text isn't grounded in any specific incident, so evaluating it would measure the fixed string, not a model; the live run produced a genuine, reportable finding (0% grounding, a hallucinated category) instead of a synthetic non-result |
| Pipeline stage timing reported as batch throughput, not per-event latency | The pipelines are batch jobs, not a streaming service; a fabricated per-event latency number would misrepresent the actual architecture |
| Benchmark's `sqlite:///:memory:` engine uses `StaticPool` + `check_same_thread=False` | Without it, the FastAPI `TestClient`'s dependency-injected session opens a second, separate, empty in-memory database — the identical class of bug already solved the same way in Phase 9's API test fixture and Phase 11's CI test client |
| `app/benchmark/generate_load.py`'s output not checked into git (unlike `data/eval/`) | It's disposable load regenerated every run, not a reviewable fixture — checking it in would suggest it's meaningful to inspect by eye, which it isn't |
| Both harnesses build their own isolated `sqlite:///:memory:` engine, never `SessionLocal`/`DATABASE_URL` | Same principle as every throwaway-data concern in this project: benchmark load and eval fixtures must never be able to land in real/demo data, enforced structurally rather than by convention |
| Real per-task LLM latency/token numbers reused from the AI-grounding run rather than re-measured in the benchmark | Re-running the same category of live call twice, once for each document, would be redundant load on the same local model for no new information |

## Verification performed

- `uv run python -m app.evaluation.cli`: real run against the checked-in `data/eval/` dataset — 20/20 detection cases correct (precision 1.0, recall 1.0 overall and per rule), 9/9 positive + 3/3 negative IOC cases correct (precision 1.0, recall 1.0 overall and per type), 2/2 correlation cases correct. Locked in as a regression test (`test_evaluation_harness.py`, 3 tests, passing).
- AI grounding: run for real against a live local Ollama instance (`qwen2.5:0.5b`) over the eval dataset's multi-stage incident — 6/6 tasks schema-valid, grounding rate 0.0, MITRE overlap rate 1.0, one confirmed hallucinated classification. Not part of the automated test suite (opportunistic, requires a running Ollama instance), matching the pattern already established for `test_llm_ollama_live.py` in Phase 6.
- `uv run python -m app.benchmark.cli --events-per-source 500 --api-requests 50`: real run, completed end-to-end after fixing the `StaticPool` issue described above. Real numbers captured in `docs/benchmarks.md` — ingestion ~27.7k events/sec, detection ~18.4k events/sec, IOC extraction ~1.3k events/sec, correlation ~432 alerts/sec, API endpoints at single-digit-ms p50 / under 14ms p99. Smoke-tested by `test_benchmark_harness.py` at a small scale (asserts the harness completes and returns well-formed data, not any specific number).
- Full backend suite after all Phase 12 code landed: `uv run pytest --cov=app --cov-report=term-missing` — 342 passed, 1 skipped (the opportunistic live-Ollama test), 98% line coverage, comfortably above the Phase 11 CI floor of 95%.
- `uv run ruff check .` and `uv run ruff format .`: clean (3 files reformatted, then reconfirmed clean).

## What Phase 12 deliberately does not include

**No load/stress testing** — the benchmark measures throughput and latency at a fixed, moderate scale (1500 events); it does not push toward a breaking point, measure behavior under concurrent write load, or simulate realistic network latency to a networked database. **No Postgres-backed benchmark numbers** — both harnesses use in-memory SQLite deliberately (isolation, speed, no risk of touching real data); the API latency numbers in `docs/benchmarks.md` are explicitly framed as a floor, not a production estimate, and a real Postgres comparison is left as future work. **No benchmark of the project's actual recommended LLM** (`llama3.1:8b-instruct-q4_K_M`) — the live numbers here are from a much smaller model chosen for fast local verification; stated plainly in both docs rather than implied to be representative. **The correlation order/context-sensitivity discrepancy found while building the AI-grounding script is not root-caused** — ingesting only the `multi_stage` scenario's files in isolation produces a different correlation result than ingesting the full eval dataset; documented in DEF.md's Phase 12 status section as a real, open finding rather than silently worked around, but not investigated further given the scope already covered in this phase. **No mutation or property-based testing of the eval/benchmark harnesses themselves** — matches Phase 11's stated boundary; not asked for by TODO.md's task list.
