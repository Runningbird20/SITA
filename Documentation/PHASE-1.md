# Phase 1: Core Data Model — Completion Report

Status: complete. This document explains what was built, how the pieces fit together, and why each decision was made. For the field-level schema reference, see [DEF.md](../DEF.md) — that document is the data dictionary; this one is the narrative of how it got implemented and what tradeoffs that involved. For the checklist itself, see [TODO.md](../TODO.md#phase-1-core-data-model).

## Goal

Phase 0 proved the system boots. Phase 1's job was to give it something real to persist: every core entity the rest of the roadmap depends on — events, alerts, incidents, IOCs, entities, detections, MITRE techniques, AI analysis results, and recommendations — as actual database tables, with the relationships between them enforced by the database itself, not just assumed by application code. This phase also had to prove, concretely, that the Postgres/SQLite abstraction from Phase 0 wasn't just a config option that happened to work for an empty database — it had to survive a real schema with foreign keys, check constraints, and JSON columns.

Two design principles drove every decision in this phase, both carried over from the project's founding requirements:

1. **The LLM is never the source of truth for a security decision.** This has to be true at the *schema* level, not just enforced by convention in application code — otherwise nothing stops a future bug from writing an LLM guess into a field a human analyst would read as ground truth.
2. **Every provenance claim must be checkable from the row itself.** Given any `Alert`, `Incident`, `Recommendation`, or MITRE mapping, it should be possible to answer "was this decided by a rule or by a model?" without external context — the answer lives in the data.

## What was built

### The data dictionary first (`DEF.md`)

Before any code was written, every entity was fully specified — field names, types, nullability, relationships, indexes, and enum values — in [DEF.md](../DEF.md). This was intentional sequencing: designing the schema on paper first (or rather, in Markdown) surfaces relationship questions (does an IOC belong to one event or many? does a Recommendation always need an incident, or can it stand alone against just an alert?) that are much cheaper to get wrong in a document than in a migration that's already been applied. The DEF.md conventions section also establishes the two rules every model had to follow:

- IDs are UUIDs everywhere, never auto-increment integers exposed over an API.
- Enums are stored as `VARCHAR`, validated at the application level — not native Postgres enum types — specifically so SQLite (used for fast local dev and tests) stays schema-compatible with Postgres without special-casing.

### SQLAlchemy models (`backend/app/models/`)

One module per entity, matching DEF.md's structure exactly:

| Table | Module | Notes |
|---|---|---|
| `entities` | `entity.py` | Deduplicated by `(entity_type, identifier)` |
| `detections` | `detection.py` | Rule *definitions*, distinct from firings |
| `mitre_techniques` | `mitre.py` | Local, static ATT&CK subset |
| `security_events` | `event.py` | The atomic normalized observation |
| `alerts` | `alert.py` | One detection-rule firing |
| `incidents` | `incident.py` | A correlated group of alerts |
| `iocs` | `ioc.py` | Deduplicated by `(ioc_type, value)` |
| `analysis_results` | `analysis_result.py` | The **only** place LLM output is recorded |
| `recommendations` | `recommendation.py` | Rule-based or LLM-sourced, always labeled |

Plus `enums.py` (every enum, as `StrEnum` subclasses), `base.py` (shared `UUIDPKMixin`, `CreatedAtMixin`, `TimestampMixin`), and `associations.py` for every many-to-many relationship.

**Junction tables come in two shapes**, and the split was deliberate:

- **Plain `Table` objects** (`alert_event`, `event_ioc`, `alert_ioc`, `detection_mitre_mapping`) — used wherever the relationship needs no data of its own beyond the two foreign keys. SQLAlchemy's `relationship(secondary=...)` handles these transparently.
- **Association-object mapped classes** (`EventEntity`, `AlertEntity`, `AlertMitreMapping`) — used wherever the relationship itself carries meaning. An event doesn't just *reference* an entity, it references it in a `role` (source, target, or actor) — that's data that belongs on the junction, not on either side of it. `AlertMitreMapping` is the most important instance of this pattern in the whole schema: it's what lets a single alert have *both* a rule-derived MITRE mapping and an LLM-suggested one, coexisting as separate rows distinguished by `source`, rather than forcing one to overwrite the other.

**Dialect-portable types were centralized in one place** (`app/db/types.py`), not scattered across models:

```python
JSONVariant = JSON().with_variant(JSONB(), "postgresql")
```

Every JSON-shaped column (`raw_payload`, `normalized`, `severity_factors`, `correlation_method`, `config`, `parsed_output`, `entity_metadata`) uses this single type. On Postgres it's genuinely `JSONB` (indexable, queryable); on SQLite it's plain `JSON`. This is the *only* place a Postgres/SQLite difference is allowed to leak into model code — every model file itself is dialect-agnostic. The same discipline applies to UUIDs: SQLAlchemy 2.0's generic `Uuid` type (used via `Mapped[uuid.UUID]`, resolved automatically through its default type-annotation map) renders as a native `uuid` column on Postgres and a portable string form on SQLite, again with zero per-model special-casing.

**Two database-level check constraints encode the provenance rules directly**, not just in docstrings:

```sql
-- analysis_results: must be scoped to exactly one of incident or alert, never both, never neither
CHECK ((incident_id IS NOT NULL AND alert_id IS NULL) OR (incident_id IS NULL AND alert_id IS NOT NULL))

-- recommendations: an LLM-sourced recommendation must point at the AnalysisResult that produced it;
-- a rule-based one must not (there's nothing to point at)
CHECK ((source = 'llm' AND analysis_result_id IS NOT NULL) OR (source = 'rule_based' AND analysis_result_id IS NULL))
```

These were written into the models and verified as actual constraints in both SQLite and Postgres (see Verification below) — not left as an application-level "please remember to check this" comment.

### The `entity_metadata` naming exception

DEF.md specifies a field simply named `metadata` on `Entity`. In code it's `entity_metadata`. This isn't a deviation for its own sake: `metadata` is a reserved attribute name on SQLAlchemy's declarative `Base` — it's already the `MetaData` object that holds the whole schema — so a column can't reuse it. This is documented both in DEF.md's status section and here, rather than silently renamed with no trace.

### Avoiding circular imports without losing lint coverage

Nine entity modules that reference each other (`Alert` needs `Detection`, `Incident`, `SecurityEvent`...; `Incident` needs `Alert`...; and so on) can't all `import` each other directly without a circular-import error. SQLAlchemy's own answer to this is to reference the *other side* of a relationship as a string — `Mapped["Detection"]` instead of `Mapped[Detection]` — which SQLAlchemy resolves lazily via its mapper registry once every model has been imported once (which `app/models/__init__.py` guarantees). That solves the runtime problem, but static tools like Ruff's pyflakes checks can't tell a lazily-resolved string reference from a genuine typo, and flagged every one of them as an undefined name (`F821`).

The fix applied — rather than silencing the check — was to add `if TYPE_CHECKING: from app.models.x import Y` blocks to every model file that needs one. These imports never execute at runtime (so no circular-import risk), but they make the string forward-references resolvable to both Ruff and any IDE/type-checker a future contributor uses. This is the pattern SQLAlchemy's own documentation recommends for exactly this situation, and it means `uv run ruff check .` genuinely passes clean rather than passing because a rule got turned off.

### Alembic migrations (`backend/alembic/`)

`alembic init alembic` was run, then `alembic/env.py` was rewired so the migration environment's database URL comes from the same `get_settings().database_url` every other part of the app uses — not a separately hardcoded value in `alembic.ini`. This matters because it makes it structurally impossible for the migration tooling and the running application to disagree about which database they're pointed at; there's exactly one source of truth for `DATABASE_URL`, inherited from the Phase 0 configuration discipline.

`target_metadata = Base.metadata` is set after importing `app.models` (which imports every entity module), so `alembic revision --autogenerate` sees the complete schema. The generated initial migration (`6224f8f082fb_initial_schema.py`) creates all 16 tables (9 entities + 4 plain junctions + 3 association-object junctions) correctly on the first attempt — the only manual fix needed was adding a missing `Text` import that Alembic's autogenerate tooling omits from its own boilerplate when rendering a `JSONB(astext_type=...)` default, a known quirk of the tool rather than a modeling mistake.

`compare_type=True` was added to both the online and offline migration contexts so future `alembic revision --autogenerate` runs catch type changes (e.g., widening a `String(20)` to `String(50)`), not just added/removed columns.

### Pydantic schemas (`backend/app/schemas/`)

One `*Read` schema per entity (`EntityRead`, `AlertRead`, `IncidentRead`, ...), each using `ConfigDict(from_attributes=True)` so it can validate directly from an ORM instance. **Deliberately not built:** `Create`/`Update` variants. There are no API endpoints yet to receive them — Phase 9 builds the actual REST routes, and that's when it will be clear what a "create an alert" payload should even look like (probably nothing, since alerts are system-generated, not user-submitted — a question that's premature to answer now). Building unused Create/Update schemas today would be exactly the kind of speculative, requirements-anticipating work the project's engineering principles call out as something to avoid.

### Tests (`backend/tests/unit/test_models.py`, `test_schemas.py`)

An in-memory SQLite database, built directly from `Base.metadata.create_all()` (not through Alembic — that's intentionally a separate check, see Verification), with foreign-key enforcement explicitly turned on via a `PRAGMA foreign_keys=ON` connect-event listener (SQLite doesn't enforce FKs by default, unlike Postgres — the test setup accounts for that rather than getting a false sense of safety from a database that isn't actually checking anything).

Eleven test cases, grouped by what they prove:

- **`TestFullGraphPersists`** — builds one complete, realistically-connected object graph (a detection with a MITRE mapping, an entity, an event, an alert linking to all of them, an IOC, an incident, an `AnalysisResult`, and a `Recommendation`) and confirms it round-trips through a commit and a fresh query. This is the test that proves the relationships actually work end-to-end, not just that each table can be created in isolation.
- **`TestUniqueConstraints`** — `Entity(entity_type, identifier)`, `IOC(ioc_type, value)`, and `Detection.rule_key` each reject a duplicate insert.
- **`TestRequiredFields`** — a `NOT NULL` column (`Detection.rule_key`) rejects `None`.
- **`TestForeignKeyIntegrity`** — an `Alert` pointing at a nonexistent `Detection` is rejected.
- **`TestAnalysisResultScopeConstraint`** — the "exactly one of incident/alert" check constraint is verified in both failure directions (both set, neither set).
- **`TestRecommendationProvenanceConstraint`** — the "LLM source requires an analysis_result_id, rule-based source forbids one" check constraint, also verified in both directions.

## How it all connects

```
DEF.md (schema design, written first)
   │
   ├──→ app/models/*.py  (SQLAlchemy models — the schema, enforced)
   │        │
   │        ├──→ app/models/__init__.py imports everything,
   │        │     populating Base.metadata and resolving every
   │        │     TYPE_CHECKING-guarded forward reference
   │        │
   │        ├──→ alembic/env.py reads Base.metadata + get_settings().database_url
   │        │     → alembic/versions/..._initial_schema.py
   │        │        → applied identically against SQLite (native dev) and
   │        │          Postgres (docker-compose) — same migration, two databases
   │        │
   │        └──→ app/schemas/*.py mirror the models for future API responses
   │                (Phase 9 will build the FastAPI routes that return these)
   │
   └──→ tests/unit/test_models.py exercises the constraints directly against
         an in-memory SQLite DB, independent of Alembic
```

The practical proof that Phase 0's data-layer abstraction claim was real, not aspirational: the exact same model code, with zero conditional branches on database type anywhere in `app/models/`, was migrated and round-tripped against both SQLite and a live Postgres container in this phase. Where a Postgres/SQLite difference genuinely exists (JSONB vs JSON, native UUID vs portable UUID), it's contained to exactly one file (`app/db/types.py` and SQLAlchemy's own `Uuid` type) rather than leaking into entity definitions.

## Key decisions and why

| Decision | Reasoning |
|---|---|
| Write DEF.md before any model code | Relationship questions (cardinality, ownership, nullability) are cheap to fix in a document, expensive to fix after a migration exists |
| Enums as `VARCHAR` + app-level `StrEnum`, not native Postgres enum types | Keeps SQLite dev/test parity with Postgres; extending an enum value later is a normal code change + migration, not an `ALTER TYPE` |
| Association-object classes for junctions that carry data (`role`, `source`) vs. plain tables for junctions that don't | `secondary=` has no attribute of its own to hold extra data — using it where a `role` or `source` needs to live would have silently lost that information |
| `AlertMitreMapping` as its own table rather than a `source` column on `alert_mitre_mapping` merged into `Alert` | Lets a rule-derived and an LLM-suggested MITRE mapping coexist as separate, independently-queryable rows instead of one overwriting the other — directly serves the "AI conclusions must stay distinguishable from deterministic ones" requirement |
| Two DB-level `CHECK` constraints (`AnalysisResult` scope, `Recommendation` provenance) instead of only application-level validation | A schema-level constraint can't be bypassed by a future bug in application code the way a Python-level check can; provenance is exactly the kind of invariant that should be impossible to violate, not just discouraged |
| `entity_metadata` instead of DEF.md's `metadata` | `metadata` is reserved by SQLAlchemy's `Base`; documented explicitly rather than silently diverging from the spec |
| `TYPE_CHECKING` imports instead of disabling `F821` for the models package | Keeps real lint coverage on the models directory instead of trading it away for convenience; matches SQLAlchemy's own recommended pattern for cross-referencing split model files |
| Alembic's `sqlalchemy.url` sourced from `get_settings()`, not `alembic.ini` | One source of truth for `DATABASE_URL`; migrations and the running app can never disagree about which database they mean |
| Only `*Read` Pydantic schemas, no `Create`/`Update` yet | No endpoints exist to consume them yet (Phase 9); building them now would be guessing at a shape that isn't knowable until the actual routes are designed |
| In-memory SQLite with `PRAGMA foreign_keys=ON` for unit tests, separate from the Alembic-applied migration check | Two different failure modes worth catching separately: "do the constraints behave correctly" (unit tests, fast, run on every commit) vs. "does the migration file itself apply cleanly" (verified manually against both real dialects this phase; CI now also runs an Alembic smoke-check against both) |

## Verification performed

- `configure_mappers()` was run standalone to confirm every relationship resolves — this is what would fail loudly if a `TYPE_CHECKING` import were missing or a `back_populates` name were mistyped.
- The initial migration was generated via `alembic revision --autogenerate`, inspected, and applied against a fresh SQLite file — table list confirmed to match all 16 expected tables.
- The same migration was applied against a real `postgres:16-alpine` container (via `docker compose`). Column types were inspected directly with `\d`: `config` came back as genuinely `jsonb`, `id` as native `uuid`, and the `ck_recommendation_llm_requires_analysis_result` check constraint was present and correctly worded in Postgres's own constraint listing — not just assumed correct because the Python code looked right.
- `alembic check` was run after the migration was applied, confirming zero drift between the current models and the applied migration — i.e., nothing was defined in code that the migration doesn't also create.
- The full test suite (12 tests including the one from Phase 0) passes; `ruff check .` and `ruff format --check .` both pass clean across every new file.
- The Docker image was rebuilt after Alembic was wired in (the `Dockerfile` had deliberately deferred copying `alembic/` until this phase, since it didn't exist in Phase 0), and `alembic upgrade head` was run *inside* the running backend container against the containerized Postgres, confirmed via `/healthz` afterward.
- CI (`.github/workflows/ci.yml`) was extended with a dedicated Postgres-backed job that runs `alembic upgrade head` against a real `postgres` service container — so the "works on both dialects" claim is checked on every push, not just asserted once locally.

## What Phase 1 deliberately does not include

No API endpoints beyond the Phase 0 health check — the schemas exist, but nothing serves them yet (Phase 9). No actual ingestion, detection, correlation, or LLM logic — those are Phases 2 through 7, and now have real tables to write into. No seed/fixture data beyond what the unit tests construct inline. No `Create`/`Update` Pydantic schemas, for the reasons above.
