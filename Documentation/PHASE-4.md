# Phase 4: IOC Extraction — Completion Report

Status: complete. This document explains what was built, how the pieces fit together, and why each decision was made. For the field-level extraction contracts, see [DEF.md § Phase 4](DEF.md#phase-4-ioc-extraction) — that document is the data dictionary; this one is the narrative of how it got implemented and what tradeoffs that involved. For the checklist itself, see [TODO.md](../TODO.md#phase-4-ioc-extraction).

## Goal

Phase 3 gave the system alerts. Phase 4's job was to pull the actual indicators out of the raw events underneath them — IP addresses, domains, URLs, file hashes, emails, usernames — into a single deduplicated table an analyst (or a future correlation/dashboard phase) can query directly, instead of re-reading `raw_payload` JSON blobs every time. Like Phase 3, this had to stay entirely deterministic; the `[STRETCH]` LLM-assisted extraction task in `TODO.md` was left undone on purpose, not forgotten — see "What Phase 4 deliberately does not include" below.

## What was built

### Two extraction strategies, declared explicitly (`backend/app/ioc/field_extraction.py`)

The central design decision of this phase: a `SecurityEvent.normalized` field either **is** a structured indicator already (an ingestion adapter put it there specifically because it's an IP, or a username) or **might contain** one embedded in free text (`command_line`, `path`). Conflating these — regex-scanning every field indiscriminately — would have been both slower and less accurate. `FIELD_MAP` declares, per source type, which strategy applies to which field:

```python
FIELD_MAP = {
    SourceType.AUTH: [("source_ip", FieldStrategy.IP), ("username", FieldStrategy.USERNAME)],
    SourceType.ENDPOINT: [("command_line", FieldStrategy.SCAN), ("user", FieldStrategy.USERNAME)],
    SourceType.NETWORK: [("src_ip", FieldStrategy.IP), ("dst_ip", FieldStrategy.IP)],
    SourceType.DNS: [("query_name", FieldStrategy.DOMAIN), ("resolved_ips", FieldStrategy.IP_LIST)],
    SourceType.WEB: [("source_ip", FieldStrategy.IP), ("path", FieldStrategy.SCAN)],
}
```

Fields not listed — `dest_host`, `process_name`, `user_agent`, `status_code`, and so on — are never touched. `dest_host`/`host` specifically are skipped on purpose: they represent an `Entity` in the Phase 1 schema, not an `IOC` — a hostname isn't one of the 9 `IOCType` values, and conflating the two would blur a distinction the data model already makes deliberately.

### The 6 regex extractors (`backend/app/ioc/{ipv4,ipv6,domain,url,file_hash,email}.py`)

Each is small and does one thing: match a pattern, then apply a semantic validity check before accepting the candidate. `ipv4`/`ipv6` additionally expose a `from_field()` function (used by the structured-field strategy) alongside `scan()` (used by the free-text strategy) — the same underlying `ipaddress` validation, but with different tolerance for private/reserved addresses depending on which context found them (see below). `url`, `file_hash`, and `email` are scan-only; nothing in the field map ever labels a field as "this is definitely a URL," so there's no field strategy for them. `username` is the mirror image — field-only, no `scan()` at all, because (as `TODO.md`'s own task description puts it) a regex cannot tell "this word is a username" apart from any other word in a command line.

### Context-dependent trust for private/reserved IP addresses

The same private IP address gets treated differently depending on *how* it was found, and this is deliberate, not inconsistent:

- **Structured field** (`auth.source_ip`, `network.src_ip`/`dst_ip`, `dns.resolved_ips`) — always kept, private or not. `10.0.0.5` (the compromised host in the Phase 2 scenario) has to remain a trackable indicator, because Phase 5's correlation strategy explicitly needs to correlate alerts on shared internal IPs — filtering it out here would break that phase before it's even built.
- **Free-text scan** (`command_line`, `path`) — private, loopback, link-local, and reserved addresses are filtered out entirely. In this context they're overwhelmingly noise (version strings, unrelated internal references), and every internal IP that actually matters is already captured by the structured-field path for that same event.

This is the concrete meaning behind `TODO.md`'s "reject private/reserved ranges where relevant to context" — the context is exactly what decides the answer.

### A real bug caught by actually looking at the output

Extraction was run against real data before any test was written, per the project's habit of verifying against actual output rather than just "the tests pass." The first run produced three `domain` IOCs that were clearly wrong: `payload.bin`, `p.bin`, and `powershell.exe` — file names from a Windows path and a `.exe`, misread as domains because `.bin` and `.exe` are indistinguishable from a real TLD by a "2-24 alphabetic characters" check alone. The fix was a small denylist of common file extensions (`NON_TLD_FILE_EXTENSIONS` in `base.py`), applied only in the `domain` scanner (never in `from_field`, since a DNS `query_name` structurally can't be a file path).

Fixing that surfaced a second, more interesting issue: the domain scanner's RFC 2606 reserved-TLD filter (`.internal`, `.local`, `.test`, `.example`, `.invalid`, `.localhost`) was *also* filtering out `.example` — which this project's own Phase 2 datasets use extensively, by the same RFC's convention, to represent externally-hosted malicious domains without pointing at a real one (`cdn-update-service.example` in `dns/suspicious_domain.jsonl`, now joined by `malicious-redirect.example` in this phase's own new web fixture). Filtering `.example` meant Phase 4 couldn't detect the exact kind of domain its own test data was built to represent — a genuine, self-defeating conflict between the dataset design and the extractor design, not a corner case. The resolution: `.example` was deliberately removed from `RESERVED_TLDS`, with the reasoning recorded directly in `base.py`'s comment, in `DEF.md`, and here — a project-specific decision, not a general claim that `.example` is always safe to trust in a real deployment.

### Deduplication and the two-pass pipeline (`backend/app/ioc/service.py`, `pipeline.py`)

`upsert_ioc()` looks up an existing `IOC` row by `(ioc_type, value)`; if found, it widens `first_seen`/`last_seen` to cover the new sighting and raises `confidence` if the new sighting is more certain (a field-strategy sighting of an IP that was previously only seen via a lower-confidence scan should end up at the higher confidence) — never lowers it. `run_ioc_extraction()` runs in two passes:

1. For every `SecurityEvent` (optionally `occurred_at >= since`), extract candidates, upsert, and link `event_ioc`.
2. For every `Alert`, union the IOCs already linked to its matched events onto `alert_ioc`.

Pass 2 runs over **every** alert on **every** call, not just ones touched by pass 1 in that run — which is what makes it self-healing regardless of whether extraction or detection ran first. Run extraction before any alerts exist, and `alert_ioc` stays empty; run it again after Phase 3's pipeline creates alerts, and pass 2 backfills the links retroactively, at no cost beyond a second pass over already-deduplicated data. This mirrors Phase 3's own "re-running is safe, but ordering affects completeness" shape rather than inventing a new kind of caveat.

### A second real bug, this one about SQLite specifically

`upsert_ioc()`'s "update if newer/wider" logic compares `seen_at` against `existing.first_seen`/`last_seen` — and the first version of that comparison raised `TypeError: can't compare offset-naive and offset-aware datetimes` the moment a test exercised the update path (not the create path) within the same session. The cause: SQLite doesn't preserve `tzinfo` through a flush/refresh round-trip the way Postgres's `TIMESTAMPTZ` does — a datetime written as timezone-aware comes back naive after SQLAlchemy re-reads it post-flush. This is a known SQLite/SQLAlchemy limitation, not a logic bug, and it hadn't surfaced in any earlier phase because nothing before this compared a freshly-flushed-then-reloaded datetime column against a fresh Python datetime in the same breath. The fix is a small `_aware()` helper that treats a naive value as UTC (this project's timestamp convention throughout) before comparing — worth remembering for any future phase that does the same "flush, then immediately compare the reloaded column" pattern.

### The CLI (`backend/app/ioc/cli.py`)

`uv run python -m app.ioc.cli [--since ...]` — same shape as Phase 3's, same reasoning for not having a REST endpoint (Phase 9 owns that surface). The module docstring states the recommended order directly: run after `app.detection.cli`, so pass 2's alert rollup has something to roll up into.

### Three new synthetic datasets

Existing Phase 2/3 fixtures already exercised `ipv4`, `username`, and `domain` heavily (via `auth`/`network` structured fields and `dns.query_name`). Three new files closed the remaining gaps, each in a fresh file rather than an edit to an existing one — so Phase 3's already-verified detection-rule behavior can't be disturbed by IOC-focused additions:

- `network/ipv6_traffic.jsonl` — no prior dataset had a single IPv6 address.
- `endpoint/ioc_rich_activity.jsonl` — a realistic incident-response-style pair of commands: a `Invoke-WebRequest` download (embeds an IPv4 and a URL) followed by a `Get-FileHash` comparison against a literal SHA256 value (embeds the hash) — exercises `url` and `file_hash_sha256` extraction from `command_line`.
- `web/ioc_rich_requests.jsonl` — a password-reset path embedding an email, and an open-redirect-style path embedding a full external URL — exercises `email` and `url` extraction from `path`.

## How it all connects

```
DEF.md § Phase 4 (field map, extractor rules, confidence scale — written first)
   │
   ├──→ app/ioc/{ipv4,ipv6,domain,url,file_hash,email,username}.py
   │        (one scan()/from_field() pair or single each, per DEF.md's table)
   │
   ├──→ app/ioc/field_extraction.py :: extract_from_event()
   │        (dispatches each normalized field to the right strategy)
   │
   └──→ app/ioc/service.py :: upsert_ioc(), link_event()
            │
            └──→ app/ioc/pipeline.py :: run_ioc_extraction()
                     │   pass 1: SecurityEvent → IOC (dedup) → event_ioc
                     │   pass 2: Alert.events' IOCs → alert_ioc (self-healing)
                     │
                 app/ioc/cli.py
                 (uv run python -m app.ioc.cli, recommended after detection)
```

Nothing here required a schema change — `IOC`, `event_ioc`, `alert_ioc`, and the `(ioc_type, value)` unique constraint all already existed from Phase 1, built specifically so a phase like this one would have somewhere to write its output.

## Key decisions and why

| Decision | Reasoning |
|---|---|
| Field strategy declared explicitly per source type, not inferred from field name or content | A field like `dest_host` could superficially "look like" it should be scanned; declaring the map explicitly means there's one place to check "does this field get extraction at all," not an implicit heuristic someone has to reverse-engineer |
| `username` extraction is field-only, never regex-scanned | A regex can validate that a string is *shaped like* a username (if that were even meaningful), but can't determine that a word *is* one — only the field's own labeled meaning can |
| Private/reserved IPs kept from structured fields, filtered from free-text scans | The same address is trustworthy in one context and noise in the other — Phase 5's correlation strategy needs internal IPs from structured fields; free-text mentions of `10.0.0.x` are essentially never a real external indicator |
| `.example` removed from the reserved-TLD filter, file-extension denylist added | Both were real bugs caught by inspecting actual extraction output against real data, not assumptions — see the dedicated section above |
| `upsert_ioc` raises confidence on a better sighting but never lowers it | A value's *best* evidence should stick — a single low-confidence scan sighting shouldn't erase an earlier high-confidence structured-field sighting of the same value |
| Pass 2 (`alert_ioc` rollup) runs over every alert on every call, not scoped by `since` | Makes the pipeline's correctness independent of run order (extraction before or after detection), at the cost of a full alert scan each run — a reasonable tradeoff at this project's scale |
| Confidence graded by extraction strategy and type specificity, refining Phase 1's original flat 1.0 | A structured-field IP and a scan-matched domain in arbitrary text carry genuinely different certainty; collapsing that to one constant would have thrown away real signal. Phase 1's original description was explicitly updated to point here rather than left silently stale |

## Verification performed

- 25 extractor-level unit tests (`tests/unit/test_ioc_extractors.py`) — every regex extractor has true-positive and true-negative cases, including the two bugs described above (file-extension exclusion, reserved-TLD exclusion) as explicit regression tests.
- `tests/unit/test_ioc_field_extraction.py` — the dispatcher correctly routes each source type's fields, confirms `user_agent` is never scanned (not in the field map), and confirms a missing field doesn't raise.
- `tests/unit/test_ioc_service.py` — dedup behavior (create vs. update), `first_seen`/`last_seen` widening in both directions, confidence-only-rises behavior, and that different `ioc_type`s with the same string `value` are correctly distinct rows.
- `tests/unit/test_ioc_pipeline.py` — end-to-end against an in-memory database, including the composition test: a brute-force pattern that triggers both Phase 3's `ssh_brute_force` rule and Phase 4's IP extraction, proving `alert_ioc` rollup actually links across the two phases' output, not just asserting each phase in isolation.
- `tests/integration/test_ioc_extraction_against_datasets.py` — the real pipeline against real checked-in datasets: all 9 `IOCType` values reached through genuine data (not synthetic-for-the-test-only fixtures), benign datasets produce zero `url`/`hash`/`email` IOCs, and the multi-stage scenario's `ssh_brute_force` alert is confirmed linked to the attacker's actual IP via `alert_ioc`.
- Beyond the automated suite: every dataset was loaded via the CLI into a fresh SQLite database, `app.detection.cli` then `app.ioc.cli` were run in sequence, and the resulting IOC table was inspected directly — all 9 types present, the two previously-buggy file-extension matches confirmed absent, `.example` domains confirmed present and correctly attributed (field-based at confidence `1.0`, scan-based at `0.6`).
- The same combined run was repeated against a **live Postgres container** (existing data from earlier phases' verification), with `event_ioc`/`alert_ioc` row counts and IOC values confirmed via direct `psql` queries, not just application-level assertions.
- `ruff check`/`ruff format --check` pass clean; all 157 backend tests pass together (99 pre-existing + 58 new).

## What Phase 4 deliberately does not include

**LLM-assisted extraction** (`TODO.md`'s `[STRETCH]` task) — not implemented. The regex layer already covers every IOC type the project's synthetic datasets exercise; adding an LLM-assisted secondary pass now, with no free-text field the regex layer demonstrably can't parse, would have been speculative work with no evidence it's needed. **No REST endpoint** — same Phase 9 deferral as Phase 3, and the same honest consequence: the frontend dashboard shows Phase 4 as a static yellow "Implemented," not a live-checked "Working," until Phase 9 exposes IOCs over the API. **No entity linking** — IOCs link to events and alerts, but not to `Entity` rows (still unpopulated by any phase, per Phase 3's own note); that remains for whichever of Phase 5 or a later refinement ends up owning entity extraction. **No threat-intelligence enrichment** — an extracted IOC is exactly what it says: a value that matched a pattern and passed format validation, nothing about known-malicious reputation, since this project has no threat-intel feed and isn't adding one as a required dependency.
