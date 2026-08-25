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
