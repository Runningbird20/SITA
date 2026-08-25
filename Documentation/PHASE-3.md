# Phase 3: Detection Engine — Completion Report

Status: complete. This document explains what was built, how the pieces fit together, and why each decision was made. For the field-level rule contracts, see [DEF.md § Phase 3](DEF.md#phase-3-detection-engine) — that document is the data dictionary; this one is the narrative of how it got implemented and what tradeoffs that involved. For the checklist itself, see [TODO.md](../TODO.md#phase-3-detection-engine).

## Goal

Phase 2 gave the system real events. Phase 3's job was to make something of them without touching the LLM at all — the project's founding principle that the AI is never the sole source of truth for a security decision has to be true structurally, and the cleanest way to make it true is to build the entire detection layer first, prove it works on its own, and only let Phase 6/7 layer AI reasoning on top of results this phase already produced deterministically. Every one of the 7 rules required by the roadmap had to be genuinely explainable — a human reading an `Alert.rationale` should see exactly why the rule fired, in terms of the actual matched data, not a black-box score.

## What was built

### The rule engine interface (`backend/app/detection/base.py`)

```python
class DetectionRule(ABC):
    rule_key: ClassVar[str]
    source_types: ClassVar[tuple[SourceType, ...]]
    default_config: ClassVar[dict]

    def evaluate(self, db: Session, events: Sequence[SecurityEvent], config: dict) -> list[RuleFinding]:
        ...
```

Rule instances are stateless — `evaluate()` is a pure function of its arguments (`events`, `config`), so one instance per rule is created once at import time (in the registry) and reused for every pipeline run. The pipeline pre-filters `events` to the rule's declared `source_types` before calling it, so a rule never has to filter irrelevant source types itself. `db` is passed through too, deliberately — two rules (`suspicious_auth_pattern`, and implicitly the design pattern any future history-dependent rule would follow) need context beyond the current candidate window, and threading the session through the interface from the start avoided having to redesign it later just for those two.

### Deterministic severity scoring (`score_severity()` in `base.py`)

A rule's `default_severity` is a starting point, not the final answer:

```
score = min(1.0, rule_weight + volume_factor + asset_sensitivity)
```

where `rule_weight` comes from the rule's baseline severity, `volume_factor` grows (capped at `0.3`) with how far over threshold the finding is, and `asset_sensitivity` is a reserved `0.0` placeholder — there's no asset-criticality data anywhere in the system yet (no phase has built it), so the field exists in the formula and in every `severity_factors` JSON blob now, ready for a future phase to populate without a schema change. This is the same formula for all 7 rules — one place to reason about "why is this alert rated the way it is," not seven ad hoc scoring schemes.

### The 7 rules

Each rule file is small (40–90 lines) and does exactly one thing:

- **`ssh_brute_force.py`** — groups auth failures by `(source_ip, dest_host)`, uses a sliding time window to find the densest cluster, and — the one piece of cross-event reasoning worth calling out — checks whether a success from the *same* source/target follows shortly after the failure burst. If so, the alert escalates straight to `critical` and the success event itself gets pulled into `matched_event_ids`, because "14 failed logins" and "14 failed logins followed by a successful one" are not the same severity of problem.
- **`password_spraying.py`** — groups by `source_ip` alone and counts *distinct usernames*, not raw attempt count — the opposite shape from brute force. A source IP hammering one account 20 times is brute force; a source IP trying 6 different accounts once each is spraying. Getting the grouping key wrong here would have made this rule indistinguishable from the one above it.
- **`suspicious_auth_pattern.py`** — the one rule with two independent sub-checks (off-hours login; new source IP for an established user) and the only rule besides `impossible_travel` that queries the database for context beyond the events it was handed — specifically, a user's *entire* prior successful-login history, since "is this IP new for this user" is meaningless without knowing what IPs aren't new.
- **`port_scanning.py`** — same sliding-window-plus-distinct-count shape as password spraying, but over `dst_port` instead of `username`.
- **`suspicious_powershell.py`** — the only stateless, single-event rule: four regex categories (encoded command, hidden window, execution-policy bypass, download cradle) checked against `command_line`, with confidence scaling by how many distinct categories matched. One indicator is worth flagging; four together (which is exactly what the Phase 2 `suspicious_powershell.jsonl` and scenario `endpoint.jsonl` fixtures contain) pushes the severity to `critical` through the same formula every other rule uses, not a special case.
- **`impossible_travel.py`** — the most architecturally interesting rule, discussed in its own section below.
- **`repeated_auth_failures.py`** — groups by `dest_host` alone and explicitly requires failures from at least 3 distinct source IPs. This is the rule most likely to be confused with `ssh_brute_force`, so it was built and tested specifically to *not* fire on a single noisy source (that's brute force's job) and only fire on genuinely distributed noise.

### A shared windowing helper (`backend/app/detection/windowing.py`)

`densest_window(sorted_timestamps, window_seconds)` — a two-pointer sliding-window scan that finds the sub-range with the most events within any `window_seconds` span — is used by both `ssh_brute_force` and `repeated_auth_failures`, the two rules whose match criterion is "raw count within a time window." `password_spraying` and `port_scanning` needed a variant that tracks *distinct* values within the window rather than raw count, so they implement their own two-pointer loop rather than reusing `densest_window` directly — factoring out only the genuinely shared logic rather than forcing a one-size-fits-all abstraction onto four rules with three different match criteria.

### The GeoIP dependency and `impossible_travel.py`

Real impossible-travel detection needs to know where an IP address actually is. This project has no paid geolocation API and won't add one as a required dependency — so the rule is built against a `GeoIPResolver` interface with exactly one implementation, `StaticGeoIPResolver`: a hardcoded dict covering only the specific IP addresses that appear in this project's own synthetic datasets. Given two resolved locations and a haversine (great-circle) distance calculation, the rule computes implied travel speed and compares it against a plausibility threshold (900 km/h — faster than any commercial flight covers real distances). This is real, working, tested code — the haversine math, the speed threshold, the whole detection logic is genuine — sitting behind a deliberately fake data source. That distinction (real algorithm, stub data) is the honest way to build a feature that depends on infrastructure the project doesn't have yet, and it's called out explicitly in three places: `geoip.py`'s own docstring, `DEF.md`, and `TODO.md`'s Architecture Decisions section (`[[geoip-resolver-stub]]`) — not left for someone to discover by reading the dict and wondering why Moscow and Tokyo have suspiciously round coordinates.

### Seeding, the pipeline, and the CLI

`ensure_detections_seeded(db)` upserts one `Detection` row per registered rule (by `rule_key`) — idempotent, called automatically at the start of every pipeline run, so there's no separate "run this migration-like seed script first" step to forget. `run_detection(db, since=None)` is the actual pipeline: seed, then for each enabled rule, load its relevant events, call `evaluate()`, and turn every `RuleFinding` into a persisted `Alert` linked to its matched events via the `alert_event` junction table Phase 1 already built. It doesn't commit — same caller-owns-the-transaction convention Phase 2's `ingest_records()` established, so the CLI (`app/detection/cli.py`) commits once per run and any future caller (a test, eventually a Phase 9 endpoint) controls its own transaction boundary.

**No REST endpoint was added.** TODO.md's own Phase 9 task list already anticipates "an endpoint to trigger/re-run the pipeline" — adding one now would mean redoing it once Phase 9's actual API conventions (auth, response envelopes, whatever pattern the rest of the REST surface settles on) exist. The CLI is a complete, testable, on-demand trigger in the meantime.

## How it all connects

```
DEF.md § Phase 3 (rule contracts, severity formula — written first)
   │
   ├──→ app/detection/base.py        (DetectionRule contract, score_severity)
   │        │
   │        ├──→ app/detection/{7 rule files}.py
   │        │        (each: group/filter events per DEF.md's table, emit RuleFinding)
   │        │
   │        └──→ app/detection/registry.py    (rule_key → instance)
   │                 │
   │                 ├──→ app/detection/seed.py
   │                 │        (idempotent Detection row upsert, by rule_key)
   │                 │
   │                 └──→ app/detection/pipeline.py :: run_detection()
   │                          │   loads SecurityEvent rows per rule.source_types,
   │                          │   calls rule.evaluate(), persists Alert + alert_event links
   │                          │
   │              ┌───────────┴───────────┐
   │              ▼                       ▼
   │     app/detection/cli.py     (tests call run_detection() directly)
   │     (uv run python -m app.detection.cli)
   │
   └──→ data/synthetic_events/    (4 new files, exercised by the integration tests)
            │
            └──→ tests/integration/test_detection_against_datasets.py
                     (real files, real pipeline, true positives + true negatives)
```

Nothing here required a schema change from Phase 1 — `Detection`, `Alert`, `alert_event`, `severity_factors` (JSONB) all already existed, built and verified two phases ago specifically so a phase like this one would have somewhere to write its output.

## Key decisions and why

| Decision | Reasoning |
|---|---|
| `evaluate(db, events, config)` — three arguments, not just `events` | Two rules genuinely need database access beyond their candidate window (auth history for `suspicious_auth_pattern`); threading `db` through from the start avoided a breaking interface change later just for those two |
| One shared `score_severity()` formula for all 7 rules | A single, auditable place to reason about "why is this severity what it is," instead of seven independent scoring schemes that would each need separate review |
| `password_spraying` groups by source IP alone (distinct usernames); `ssh_brute_force` groups by (source IP, target host) (raw failure count) | These are genuinely different attack shapes — conflating the grouping keys would make one rule a strict subset of the other rather than two complementary detections |
| `repeated_auth_failures` requires ≥3 distinct source IPs, not just a raw failure count over threshold | Without this, it would just re-detect every `ssh_brute_force` finding under a different name; the distinct-source requirement is what makes it catch something brute force structurally can't (distributed, low-per-source noise) |
| `impossible_travel`'s GeoIP resolver is a documented stub, not a real geolocation database | No paid/rate-limited API, per the project's founding rule — but a stub is only honest if it's *labeled* as one everywhere someone might reasonably look (code docstring, DEF.md, TODO.md open questions), which was done deliberately rather than left implicit |
| No REST endpoint for triggering the pipeline | Phase 9 owns the REST API surface and its own conventions (auth, envelopes, pagination) that don't exist yet; building a one-off endpoint now would mean rebuilding it later against those conventions |
| Detection run is not idempotent (documented, not silently accepted) | True idempotency needs either a fingerprint column (a schema change) or a stricter dedup strategy — decided against rushing a heuristic into place; tracked as an explicit open question (`[[detection-run-idempotency]]`) rather than quietly shipped as "good enough" |
| 4 new synthetic dataset files, one per rule not already exercised by Phase 2's fixtures | `ssh_brute_force`, `port_scanning`, and `suspicious_powershell` already had Phase 2 fixtures built for them; the other 4 rules needed their own data specifically shaped to cross their threshold and stay under every other rule's, so each new file is a true positive for exactly one rule |
| The frontend dashboard showed Phase 3 as a static "Implemented," not a live-checked "Working," until Phase 9 | Consequence of the no-REST-endpoint decision above, made explicit rather than worked around — see [FRONTEND.md](FRONTEND.md). The dashboard distinguishes "verified live, right now" from "asserted complete, from this phase's own tests and report" rather than collapsing both into one green, or falling back to a misleading gray for a phase that's actually done. **Update (Phase 9):** live now, via `GET /api/v1/detections` — see [PHASE-9.md](PHASE-9.md) |

## Verification performed

- 24 rule-level unit tests (`tests/unit/test_detection_rules.py`) — every rule has at least one true-positive test at its documented threshold and at least one true-negative test just below it (e.g., 9 failures doesn't trigger `ssh_brute_force`, 10 does), plus rule-specific edge cases (an unresolvable IP is silently skipped by `impossible_travel`; a single source IP with 20 failures does *not* trigger `repeated_auth_failures`, confirming the distinct-IP requirement actually works).
- `tests/unit/test_detection_seed.py` — seeding is idempotent (calling twice doesn't duplicate `Detection` rows) and seeded rows carry the rule's real metadata and `default_config`.
- `tests/unit/test_detection_pipeline.py` — `run_detection()` end-to-end against an in-memory database: the persisted `Alert` links to exactly its matched `SecurityEvent` rows, `incident_id` stays `NULL` (Phase 5's job), `since` correctly excludes out-of-range events.
- `tests/unit/test_detection_cli.py` — the CLI runs against a monkeypatched database and prints a correct JSON report.
- `tests/integration/test_detection_against_datasets.py` — the real pipeline against the real checked-in dataset files, not synthetic test-only fixtures: every attack-pattern file (`brute_force.jsonl`, `password_spraying.jsonl`, `suspicious_pattern.jsonl`, `impossible_travel.jsonl`, `distributed_failures.jsonl`, `port_scan.jsonl`, `suspicious_powershell.jsonl`) triggers exactly the rule it was built for; every `benign.jsonl` (auth, network, endpoint) triggers zero alerts; the Phase 2 multi-stage scenario triggers all 3 rules its own README documents as expected (`ssh_brute_force`, `port_scanning`, `suspicious_powershell`).
- Beyond the automated suite: every real dataset file was loaded via the CLI into a fresh, migrated SQLite database, and `uv run python -m app.detection.cli` was run against the full combined dataset — **12 alerts across all 7 rule types, zero false positives**. The actual `rationale` text for every alert was inspected directly from the database (not just asserted in a test) and reads as genuinely explainable analyst-facing text, e.g.: *"14 failed authentication attempts against 'db01.internal' from '198.51.100.23' within 195s. Followed by a successful login from the same source at 2026-01-15T05:03:30 — likely compromised."*
- The same brute-force pattern was inserted directly and detected against a **live Postgres container** (not just SQLite) — confirmed via direct `psql` inspection that `severity_factors` landed as genuine `jsonb` and the `alert_event` junction correctly linked all 10 matched events, not just asserted from the Python side.

## What Phase 3 deliberately does not include

No `AlertEntity` / entity linking — `Entity` rows aren't populated by any phase yet (Phase 2 doesn't create them, and Phase 3 doesn't either); that's left for whichever of Phase 4 or Phase 5 ends up owning entity extraction, so alerts currently link to their matched events but not to `Entity` rows. No MITRE technique mapping — `Detection` rows are seeded with no `mitre_techniques` association; that's explicitly Phase 8's job, using the `detection_mitre_mapping` table Phase 1 already built for exactly this purpose. No REST endpoint (discussed above — deferred to Phase 9). No idempotent re-run protection (discussed above — tracked as an open question). No real GeoIP data source (discussed above — tracked as an open question). No incident correlation — every `Alert.incident_id` is `NULL`; Phase 5 is what turns a pile of alerts into incidents.
