# Phase 2: Event Ingestion — Completion Report

Status: complete. This document explains what was built, how the pieces fit together, and why each decision was made. For the field-level contracts, see [DEF.md § Phase 2](DEF.md#phase-2-event-ingestion) — that document is the data dictionary; this one is the narrative of how it got implemented and what tradeoffs that involved. For the checklist itself, see [TODO.md](../TODO.md#phase-2-event-ingestion).

## Goal

Phase 1 gave the system a place to put events (`SecurityEvent`). Phase 2's job was to get real, plausible security events into that table — from five differently-shaped simulated sources — validated at the door, normalized into one common shape, and available through two different entry points (a batch file importer for bulk/offline loading, and a REST endpoint for individual/streamed events), so every later phase (detection, correlation, IOC extraction) has real rows to work against instead of hand-constructed test fixtures.

As with Phase 1, the contracts were fully specified in [DEF.md](DEF.md) *before* any adapter code was written — the raw shape of each source type, the finalized normalized shape, the ingestion pathway designs, and the synthetic dataset format were all nailed down first, then implemented against.

## What was built

### The adapter base class (`backend/app/ingestion/base.py`)

Every adapter shares two responsibilities that have nothing to do with source-type-specific fields: parsing the universal `timestamp`/`host` fields (DEF.md's "universal raw fields" rule), and reporting a validation failure in a structured way rather than crashing. Both live in `IngestionAdapter`, an abstract base class:

```python
class IngestionAdapter(ABC):
    source_type: ClassVar[SourceType]

    def parse(self, raw: dict) -> ParsedEvent:
        occurred_at = parse_timestamp(raw)
        host = require_str(raw, "host")
        normalized = self.normalize(raw)
        return ParsedEvent(source_type=self.source_type, occurred_at=occurred_at,
                            source_host=host, raw_payload=raw, normalized=normalized)

    @abstractmethod
    def normalize(self, raw: dict) -> dict: ...
```

Each concrete adapter (`auth.py`, `endpoint.py`, `network.py`, `dns.py`, `web.py`) implements only `normalize()` — 10–25 lines each, doing nothing but the field-by-field validation and mapping table from DEF.md § Phase 2 §1–2. By the time `normalize()` runs, `raw["host"]` is already guaranteed present and non-empty, so `auth.py` and `web.py` (the two adapters whose normalized shape includes a host-derived field) can read it directly without re-validating.

Validation failures are raised, not returned, as `IngestionValidationError(reason, field)` — a small exception class, not a Python exception used for control flow in the traditional "something went catastrophically wrong" sense. It's caught exactly once, in the ingestion service, and turned into a report entry. This keeps every adapter's `normalize()` method reading as a straight-line sequence of "validate this field, validate that field" without a parallel tree of `if not valid: return error` branches — the exception *is* the early-return mechanism, scoped tightly to one well-understood failure mode.

**Shared validation helpers** (`require_field`, `require_str`, `require_int`, `require_enum`, `optional_str`, `optional_int`, `parse_timestamp`) live in the same `base.py` module rather than being duplicated per adapter. Five adapters validating five different shapes still all need "is this a non-empty string," "is this actually an int and not a bool" (Python's `bool` is a subclass of `int`, which is why `require_int` explicitly excludes it — `isinstance(True, int)` is `True`, and a raw record with `"pid": true` would otherwise silently pass as `pid=1`), and "is this one of an allowed set of strings." Writing that once and reusing it is why the DNS adapter, the most structurally different of the five (it's the only one with an optional array field, `resolved_ips`), only needed one adapter-specific validation block instead of rebuilding string/int/enum checking from scratch.

### The five adapters

Each is a near-literal translation of its DEF.md § Phase 2 §1 raw contract and § Phase 2 §2 normalized-shape row:

| Adapter | Source-type-specific behavior worth noting |
|---|---|
| `auth.py` | Maps raw `host` → normalized `dest_host` (a rename, not a copy of identical semantics — see DEF.md's mapping notes on why `dest_host` is named for its role, not its literal source) |
| `endpoint.py` | `parent_pid`/`parent_process_name` are optional — included in `normalized` only when present in the raw record, never as an explicit `null` |
| `network.py` | `bytes_sent`/`bytes_received` optional, same omit-don't-null treatment; `protocol` is a 3-value enum |
| `dns.py` | The only adapter with a list-typed optional field (`resolved_ips`) — validated as "a list of strings, if present" with its own small check inside `normalize()` rather than a new shared helper for a shape that appears exactly once |
| `web.py` | Keeps `host` inside `normalized` *and* in `SecurityEvent.source_host` — deliberately not deduplicated, since DEF.md's mapping notes explain they're semantically distinct fields that happen to coincide in this project's simulated (non-load-balanced) web logs |

A registry (`app/ingestion/registry.py`) maps `SourceType → IngestionAdapter` instance, so the service and the API layer never need a chain of `if source_type == ...` branches — adding a sixth source type later means adding one adapter class and one registry entry, nothing else.

### The ingestion service (`backend/app/ingestion/service.py`)

`ingest_records(db, source_type, raw_records, batch_id=None) -> IngestionReport` is the one function both ingestion pathways call. It loops over the raw records, calls the right adapter's `parse()`, and for each record either adds a `SecurityEvent` row to the session or appends an `IngestionReportError`. One malformed record's `IngestionValidationError` is caught right there, in the loop — it never propagates past that one iteration, which is what makes "one bad line in a 10,000-line file doesn't fail the other 9,999" true in practice, not just in the DEF.md prose describing it.

**The service does not commit.** It calls `db.flush()` (so constraint violations would surface immediately, and so the caller can query what was just added within the same transaction) but leaves `db.commit()` to whoever called it. This matters because the two callers have different transactional needs: the REST endpoint commits once per HTTP request (standard request-scoped transaction), while the CLI commits once per file at the very end. Baking a commit into the service would have forced one of those two callers to work around it.

### The REST endpoint (`backend/app/api/events.py`)

`POST /api/v1/events/{source_type}` — a narrow, write-only endpoint. Two design choices worth calling out:

- **`source_type` is a path parameter typed as the `SourceType` enum.** FastAPI validates it automatically — a request to `/api/v1/events/not-a-real-source` gets a `422` before any application code runs, for free, rather than needing a manual "if source_type not in registry" check.
- **The body accepts either a single object or an array** (`dict[str, Any] | list[dict[str, Any]]`), normalized to a list of one item internally. This matches DEF.md's design intent for a "streaming individual events" endpoint that doesn't force a caller to wrap a single event in an array just to satisfy the schema.

This endpoint is deliberately not part of the broader queryable REST API — there's no `GET /api/v1/events` here. That's Phase 9's job, once pagination/filtering/sorting conventions are decided for the whole API surface, not just events. Building a one-off `GET` here would have meant redesigning it later anyway.

### The CLI batch importer (`backend/app/ingestion/cli.py`)

`uv run python -m app.ingestion.cli <source_type> <path/to/file.jsonl>` — reads a `.jsonl` file, generates one `uuid.uuid4()` batch ID, and calls the same `ingest_records()` the API uses. Two things worth noting:

- **It's a CLI, not a file-upload API endpoint.** DEF.md's original design left this pathway's transport open ("file import" without mandating HTTP multipart upload). A CLI was chosen over a multipart-upload endpoint because the primary use case — loading a few thousand lines of synthetic dataset during development, or re-seeding a demo environment — is fundamentally an operator action, not something an end user does through the dashboard. It also means Phase 15's "load the synthetic datasets" quick-start step is just a shell loop over this one command, with no server-side file-handling code to write and secure.
- **Its exit code reflects the outcome**: `0` if every record in the file was accepted, `1` if any were rejected. This makes it usable as a CI/regression check on its own — which is exactly what `tests/integration/test_synthetic_datasets.py` does, just through the Python function (`run_import`) rather than shelling out.

### Synthetic datasets (`data/synthetic_events/`)

Per DEF.md § Phase 2 §6's layout: a `benign.jsonl` baseline plus one attack-pattern file per source type, and a `scenarios/` folder for multi-stage stories.

- **`auth/brute_force.jsonl`** — 14 password failures against `admin@db01.internal` from one external IP in under 4 minutes, then a success. Built to exercise a future SSH-brute-force detection rule (Phase 3) in isolation.
- **`endpoint/suspicious_powershell.jsonl`** — a Word document spawning `powershell.exe` with a base64-encoded, hidden-window, execution-policy-bypassed command line, which itself spawns a second PowerShell invoking a download cradle, which spawns `rundll32.exe` against a dropped payload. A realistic macro-malware → download-and-execute chain, both in the process tree (`parent_process_name`/`parent_pid`) and the command-line content.
- **`network/port_scan.jsonl`** — one external IP hitting 12 different destination ports on one internal host within 22 seconds, each connection carrying no response traffic (`bytes_received: 0`) — the shape of a TCP connect scan, not real traffic.
- **`dns/suspicious_domain.jsonl`** — two NXDOMAIN lookups for algorithmically-random-looking domains (a DGA pattern), followed by a `TXT` record query and its `A` record follow-up for the same domain — `TXT` queries are a common DNS-tunneling C2 channel, and querying both types for one domain in quick succession is a recognizable beacon pattern.
- **`web/suspicious_requests.jsonl`** — SQL-injection-pattern paths, a path-traversal attempt, and scanner user agents (`sqlmap`, `Nikto`) against endpoints that don't exist (404s) or reject the request (401/403).

**The multi-stage scenario** (`scenarios/brute_force_to_lateral_movement/`) is the centerpiece: one continuous, four-source-type narrative — SSH brute force against `web01.internal` → compromise → an internal port scan pivoting from `web01.internal`'s own IP to `ws-07.internal` → a PowerShell download-and-execute chain on `ws-07.internal` → a DNS beacon from that same host. It was built with the *correlating entities deliberately shared across files* — `web01.internal`/`10.0.0.5` ties the `auth` file to the `network` file, `ws-07.internal`/`10.0.0.7` ties the `network` file to the `endpoint` and `dns` files — because this dataset's second job (beyond exercising Phase 3's rules) is to be the concrete target for Phase 5's correlation engine: four independently-ingested files that a correlation engine with no knowledge of "this is one scenario" should still reconstruct as one incident. The scenario's own `README.md` documents the full timeline, which detection rules and MITRE techniques each stage is expected to trigger, and the load commands to bring it in.

`tests/integration/test_synthetic_datasets.py::test_scenario_events_share_correlating_entities` asserts those shared-entity claims directly against the file contents — so if a future edit to the scenario data accidentally breaks the story (e.g., changes `ws-07.internal`'s IP in one file but not another), a test fails immediately rather than the breakage only surfacing much later when Phase 5's correlation engine mysteriously fails to reconstruct the incident.

### Tests

- **`test_ingestion_adapters.py`** — one "valid record parses correctly" test and one-to-three rejection tests per adapter (missing field, wrong enum value, wrong type), asserting not just that an error was raised but that it names the *correct* field — the same precision DEF.md's rejection contract calls for.
- **`test_ingestion_service.py`** — a mixed batch (two valid records, one missing a required field) proving the core claim: `accepted=2`, `rejected=1`, the correct record index and field named, and — critically — that only the two valid `SecurityEvent` rows actually got persisted, queried back from the database, not just asserted from the report object.
- **`test_ingestion_cli.py`** — `load_jsonl` skips blank lines; `run_import` assigns one shared `batch_id` to every accepted row from one file; `main()`'s exit code is `0` when everything's accepted and `1` when anything's rejected.
- **`test_events_api.py`** — the REST endpoint accepts a single object, accepts an array with one bad record and reports it at the right index, and returns `422` for an invalid `source_type` path segment.
- **`test_synthetic_datasets.py`** — walks `data/synthetic_events/` for real, loads every `.jsonl` file (including every file in the scenario), runs it through the actual `ingest_records()` service, and asserts zero rejections for every single one. This is the test that would fail if a dataset file and the adapter code it's meant to exercise ever drifted apart — it validates the *content* of the checked-in fixtures, not just the code that would process hypothetical fixtures.

## How it all connects

```
DEF.md § Phase 2 (raw contracts, normalized shape, pathway design — written first)
   │
   ├──→ app/ingestion/base.py         (shared validation + IngestionAdapter contract)
   │        │
   │        ├──→ app/ingestion/{auth,endpoint,network,dns,web}.py
   │        │        (one normalize() each, per the DEF.md field tables)
   │        │
   │        └──→ app/ingestion/registry.py   (SourceType → adapter instance)
   │                 │
   │                 └──→ app/ingestion/service.py :: ingest_records()
   │                          │            (the one place raw records become SecurityEvent rows)
   │                          │
   │              ┌───────────┴───────────┐
   │              ▼                       ▼
   │     app/ingestion/cli.py    app/api/events.py
   │     (batch .jsonl import,    (POST /api/v1/events/{source_type},
   │      one shared batch_id)     batch_id always null)
   │
   └──→ data/synthetic_events/   (the real data both pathways were proven against)
            │
            └──→ tests/integration/test_synthetic_datasets.py
                     (loads every real file through the real service, asserts zero rejections)
```

Nothing about the Postgres/SQLite abstraction from Phase 0/1 needed to change for this phase — `ingest_records()` takes a plain SQLAlchemy `Session` and calls `db.add(SecurityEvent(...))`, exactly like the Phase 1 model tests do. The same CLI command that was run against local SQLite during development was also proven, unmodified, against a live containerized Postgres instance (see Verification below) — the data layer abstraction from earlier phases held up under a real, non-trivial write workload without any ingestion-specific code needing to know which database it's talking to.

## Key decisions and why

| Decision | Reasoning |
|---|---|
| One `IngestionAdapter` base class with shared universal-field validation, five thin `normalize()` overrides | The five source types differ in their fields, not in how "is this record well-formed" should be reported — factoring that shared concern out is what let the DNS adapter (the structurally oddest one) stay a single small method instead of re-deriving string/int/enum validation from scratch |
| Validation failures as a raised exception (`IngestionValidationError`), caught once in the service loop | Keeps every adapter's `normalize()` a flat sequence of validation calls with no branching per-field error handling; the "don't crash on one bad record" guarantee lives in exactly one place (the service), not duplicated in every adapter |
| Optional fields omitted from `normalized` rather than written as `null` | Matches DEF.md's mapping notes exactly — downstream consumers (Phase 3 detection rules, Phase 4 IOC extraction) can use plain `dict.get(...)` without a null-vs-missing distinction to special-case |
| `ingest_records()` flushes but never commits | The REST endpoint and the CLI have different natural transaction boundaries (per-request vs. per-file); baking a commit into the shared service would have forced one of them into an awkward pattern |
| Batch CLI importer instead of a multipart file-upload endpoint | The primary use case (loading synthetic datasets, re-seeding demo data) is an operator action, not an end-user-facing feature — a CLI avoids writing and securing server-side file-upload handling for something the dashboard was never going to expose anyway |
| `source_type` as a typed path parameter on the REST endpoint | Free `422` validation from FastAPI for an invalid source type, instead of a manual check duplicated from the CLI's `argparse` choices list |
| Multi-stage scenario built with deliberately shared, consistent entity values (`web01.internal`/`10.0.0.5`, `ws-07.internal`/`10.0.0.7`) across four separately-ingested files | The scenario's whole purpose is to be Phase 5's correlation test target — a story that's obviously connected to a human reader but arrives as four independent ingestion calls is exactly the situation the correlation engine needs to handle, and it's the shared entities (not any explicit "these files are one scenario" marker) that a real correlation engine would have to notice |
| `test_synthetic_datasets.py` loads the actual checked-in files, not separately-constructed test fixtures | Directly ties the dataset's correctness to the adapter code's correctness — a change to either one that breaks the other fails a test immediately, rather than surfacing only when Phase 3 or Phase 5 tries to use the data and gets a confusing result |

## Verification performed

- Every adapter's happy path and 1–3 failure paths are covered by dedicated unit tests (`test_ingestion_adapters.py`) — 52 tests pass in total across the whole backend suite after this phase.
- `test_ingestion_service.py` proves the batch behavior end-to-end against a real (in-memory SQLite) database: mixed valid/invalid records, correct accept/reject counts, correct persisted row count, correct `ingestion_batch_id` stamping (and correctly `null` for the no-batch streaming path).
- `test_events_api.py` exercises the actual FastAPI route through `TestClient`, with a real (in-memory, `StaticPool`-backed so it survives across the test client's request thread) SQLite database wired in via a `get_db` dependency override — not a mocked service layer.
- `test_synthetic_datasets.py` loads and ingests **every** file under `data/synthetic_events/`, including all four scenario files, and asserts zero rejections for each — this is a full, automated regression check that the checked-in dataset content actually conforms to the schema it's meant to demonstrate.
- Beyond the automated suite, the CLI was run manually against every dataset file with a real (file-backed) SQLite database, after applying the Phase 1 Alembic migration fresh: all 10 files across the 5 source types, plus all 4 scenario files, ingested with **zero rejections**, for a total of **116 persisted `SecurityEvent` rows** (confirmed via a direct `sqlite3` query grouping by `source_type`).
- The REST endpoint was exercised live against a running `uvicorn` instance: a single-object POST, an array POST with one deliberately malformed record (correctly reporting `accepted: 1, rejected: 1` with the right field name), and an invalid `source_type` path segment (correctly returning `422`) — plus a `/docs` check confirming the new endpoint is present in the auto-generated OpenAPI schema.
- The backend Docker image was rebuilt after this phase's code was added and built successfully with no changes needed to the `Dockerfile` — no new dependencies were introduced, so the existing `uv.lock`-based dependency layer was untouched.
- `ruff check .` and `ruff format --check .` both pass clean across every new file.

## A testing infrastructure fix that came out of this phase

The `db_session` pytest fixture (in-memory SQLite with foreign keys turned on) was originally defined in `tests/unit/conftest.py` during Phase 1, scoped — by pytest's directory-based conftest discovery — to only the `tests/unit/` suite. This phase's first integration tests (`tests/integration/test_synthetic_datasets.py`) needed the same fixture and initially failed with `no such table: security_events`, because pytest was correctly *not* finding a fixture that was never visible to that directory in the first place. The fix was to move `conftest.py` up to `tests/conftest.py`, making the fixture available to both `unit/` and `integration/` suites. A related, separate issue surfaced in `test_events_api.py`: `create_engine("sqlite:///:memory:")` without `poolclass=StaticPool` gives each new connection its own private in-memory database, so the connection that ran `Base.metadata.create_all()` and the connection FastAPI's `TestClient` used for the actual request were talking to two different, unrelated empty databases. Both are standard SQLAlchemy/pytest gotchas, not defects in Phase 1's original design — but worth recording here since they'll bite again if a future phase adds `tests/integration/conftest.py` fixtures that shadow rather than reuse the shared one, or spins up another in-memory SQLite engine without `StaticPool`.

## What Phase 2 deliberately does not include

No detection logic — the datasets are *designed* to be detectable (a brute force pattern, a port scan pattern, an obfuscated PowerShell command), but nothing in this phase decides that they're suspicious. That's Phase 3, reading from the `SecurityEvent` rows this phase produces. No IOC extraction (Phase 4), no correlation (Phase 5) — though the scenario dataset's shared-entity design is deliberately ready for it. No `GET` endpoints for querying ingested events back out (Phase 9). No LLM-assisted ingestion of any kind — every adapter here is 100% deterministic, matching the project's founding principle that ingestion, like detection, is not a place the LLM has any role.
