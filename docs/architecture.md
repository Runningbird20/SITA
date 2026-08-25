# Architecture

Status: stub — expand as each phase in [TODO.md](../TODO.md) lands.

## System Overview

SITA ingests simulated security events, normalizes them, runs them through a
deterministic detection engine, extracts IOCs, correlates related alerts into
incidents, maps activity to MITRE ATT&CK, and layers AI-assisted triage
(summarization, classification, investigation hypotheses) on top —
never in place of — the deterministic pipeline.

```
Event Source(s) → Ingestion → Normalization → Detection Engine → Alert
                                                     │
                                                     ▼
                                          IOC Extraction, Correlation
                                                     │
                                                     ▼
                                                 Incident
                                                     │
                                    ┌────────────────┴────────────────┐
                                    ▼                                 ▼
                          MITRE ATT&CK Mapping              AI Triage (LLMProvider)
                            (deterministic)                  (Ollama / Mock)
                                    │                                 │
                                    └────────────────┬────────────────┘
                                                     ▼
                                            REST API (FastAPI)
                                                     │
                                                     ▼
                                         Frontend Dashboard (React)
```

## Core Principle: Deterministic vs. AI-Generated

Every finding in the system is traceable to exactly one of two origins:

- **Deterministic** — produced by rule code (`app/detection`, `app/correlation`,
  `app/mitre`, `app/ioc`). Reproducible, explainable, no model involved.
- **AI-generated** — produced by an `LLMProvider` call, always recorded as an
  `AnalysisResult` row (provider, model, prompt version, latency) and never
  written into a deterministic table's fields.

See [DEF.md](../Documentation/DEF.md) for the full data model and how this separation is
enforced at the schema level.

## Event Ingestion

Every simulated event source (`auth`, `endpoint`, `network`, `dns`, `web`)
arrives in its own raw JSON Lines format and is mapped by a per-source
ingestion adapter into the shared `SecurityEvent.normalized` shape. The raw
contract and finalized normalized shape for each source type are defined in
[DEF.md § Phase 2](../Documentation/DEF.md#phase-2-event-ingestion) rather than
duplicated here. Two ingestion pathways share one validation/rejection
contract: batch `.jsonl` file import, and `POST /api/v1/events/{source_type}`
for individual/streamed events.

## Detection Engine

Seven deterministic rules (`backend/app/detection/`) read persisted
`SecurityEvent` rows and produce `Alert` rows — no LLM involved anywhere in
this phase. Every rule shares one interface (`DetectionRule.evaluate`) and
one deterministic severity-scoring formula; the full rule table (grouping
keys, thresholds, windows) is defined in
[DEF.md § Phase 3](../Documentation/DEF.md#phase-3-detection-engine) rather
than duplicated here. Run on-demand via
`uv run python -m app.detection.cli` — no REST trigger endpoint yet
(deliberately deferred to Phase 9). One rule (`impossible_travel`) depends on
a GeoIP resolver that is currently a small static stub, documented as a known
limitation rather than a real geolocation capability.

## IOC Extraction

`backend/app/ioc/` pulls indicators of compromise out of `SecurityEvent`
rows into the `IOC` table, deduplicated by `(ioc_type, value)`. Two
strategies apply per normalized field, declared explicitly rather than
inferred — structured fields (`source_ip`, `username`, `query_name`, ...)
are trusted directly; free-text fields (`command_line`, `path`) are
regex-scanned for embedded indicators. The full field map, the 6 regex
extractors, and the confidence scale are defined in
[DEF.md § Phase 4](../Documentation/DEF.md#phase-4-ioc-extraction) rather
than duplicated here. Run on-demand via `uv run python -m app.ioc.cli`,
recommended after `app.detection.cli` so its second pass can roll matched
alerts' IOCs up onto `alert_ioc` — no REST endpoint yet, same Phase-9
deferral as detection.

## Incident Correlation

`backend/app/correlation/` groups `Alert` rows into `Incident` rows using
deterministic weighted scoring (time proximity, shared IOCs, shared hosts,
shared MITRE techniques — the last currently inert until Phase 8), not
graph clustering. The full formula, weights, and grouping algorithm are
defined in
[DEF.md § Phase 5](../Documentation/DEF.md#phase-5-incident-correlation)
rather than duplicated here. Shared-host correlation needed new
infrastructure this phase: `Entity` population (deferred by every prior
phase) plus a small, explicitly-labeled hostname↔IP identity bridge
(`host_identity.py`) — the same kind of deliberate stub as Phase 3's GeoIP
resolver, standing in for a real CMDB. Run on-demand via
`uv run python -m app.correlation.cli`, recommended after `app.ioc.cli` —
no REST endpoint yet, same Phase-9 deferral as detection and IOC extraction.

## LLM Integration

`backend/app/llm/` is a provider abstraction, not a triage feature — it
exists so the AI layer is swappable, testable without Ollama running, and
never a single point of failure. `LLMProvider.generate()` is concrete on
the base class (retry/timeout handling, structured-output validation,
confidence derivation, logging), so `MockProvider` and `OllamaProvider`
differ only in `_complete()`, one unretried call to the underlying model —
`MockProvider` makes zero network calls and is the app's real default.
`generate()` never raises: every failure (timeout, connection error,
invalid output) becomes a returned `LLMResponse` with a
`validation_status`, not an exception. Confidence is derived from how many
retries validation required, never from a model's self-reported certainty.
The full interface, request/response types, retry semantics, and
confidence formula are defined in
[DEF.md § Phase 6](../Documentation/DEF.md#phase-6-local-llm-integration)
rather than duplicated here. This phase has no REST endpoint and no actual
triage prompts — it proves the machinery works against an illustrative
schema; Phase 7 writes the real prompts and persists `AnalysisResult` rows.

## Data Layer

SQLAlchemy models sit behind a single `DATABASE_URL`; the dialect (Postgres in
Docker, SQLite for fast local/dev/test) is the only thing that changes —
application code never branches on it. See `backend/app/db/session.py`.

## Configuration

All runtime configuration is centralized in `backend/app/core/config.py`
(`pydantic-settings`, sourced from `.env`). See `.env.example` at the repo
root for the full list of variables.

## Repository Layout

See the "Proposed Repository Layout" section of [TODO.md](../TODO.md).

## Open Decisions

Tracked in the "Architecture Decisions / Open Questions" section of
[TODO.md](../TODO.md) — update this document as each is resolved.
