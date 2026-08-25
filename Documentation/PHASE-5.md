# Phase 5: Incident Correlation — Completion Report

Status: complete. This document explains what was built, how the pieces fit together, and why each decision was made. For the field-level correlation strategy, see [DEF.md § Phase 5](DEF.md#phase-5-incident-correlation) — that document is the data dictionary; this one is the narrative of how it got implemented and what tradeoffs that involved. For the checklist itself, see [TODO.md](../TODO.md#phase-5-incident-correlation).

## Goal

Phases 3 and 4 gave the system alerts and the indicators inside them. Phase 5's job was to turn a pile of alerts into a story — group the ones that are actually the same incident, and only those. TODO.md flagged this phase's strategy as something to design and document *before* writing correlation code, and for good reason: get the grouping logic wrong and the whole platform either drowns analysts in scattered alerts for one real incident, or silently merges unrelated activity into a false narrative. Both failure modes are worse than doing nothing.

## What was built

### The real obstacle, named before any code

Before scoring could be designed, a genuine problem had to be faced directly: `auth`/`endpoint` events identify a host by hostname (`"web01.internal"`); `network`/`dns` events identify it by IP (`"10.0.0.5"`). Nothing built through Phase 4 ties these two representations of the same physical host together — and this isn't an edge case, it's exactly the shape of the Phase 2 scenario, whose `ssh_brute_force` alert (targets `web01.internal`) and `port_scanning` alert (sourced from `10.0.0.5`) share no literal field at all. A real deployment resolves this with a CMDB or asset inventory. This project doesn't have one and isn't adding one as a required dependency — so, following the exact precedent Phase 3 set for `impossible_travel`'s GeoIP dependency, the resolution is a small, explicitly-labeled stub:

```python
KNOWN_HOST_ALIASES: dict[str, str] = {
    "web01.internal": "10.0.0.5",
    "ws-07.internal": "10.0.0.7",
}
```

Two entries, covering exactly the hosts this project's own scenario dataset ties together — not a general capability, and documented as such in the code, in `DEF.md`, and in `TODO.md`'s Architecture Decisions (`[[host-identity-stub]]`).

### Entity population — the debt Phase 3 and 4 deliberately deferred

Phase 1 designed `Entity` specifically "to enable correlation," but no phase populated it through Phase 4 — each explicitly deferred it as out of scope. Phase 5 is where that comes due, but only partially: **only `entity_type="host"`** gets populated. `ip`/`user`/`domain` stay unpopulated as `Entity` rows, because Phase 4's `IOC` table already covers exactly those types (`ipv4`/`ipv6`/`username`/`domain`) — building `Entity` rows for them too would be redundant infrastructure with no new correlating power. This is also *why* `TODO.md`'s "shared IP / shared user / shared domain" tasks collapse into one implementation below (shared IOC) while "shared host" needed this dedicated new population step: host is the one thing `IOC` genuinely doesn't cover.

Host extraction (`host_extraction.py`) had one subtlety worth calling out precisely, since translating the design into code caught a real inaccuracy in the original draft: `endpoint`'s `normalized` shape has **no host field at all** — only `SecurityEvent.source_host` (the top-level column every ingestion adapter populates from the raw record's `host` field) is universal across all 5 source types. Using that column directly, rather than reaching into inconsistent per-source `normalized` fields, is both simpler and correct where the original DEF.md draft (which said `endpoint.host`) was not.

### A second real bug — the same shape as Phase 4's, caught the same way

`network` events involve two hosts (`src_ip`, `dst_ip`), and the design called for restricting host-entity creation to "private/internal" addresses only — a public address there is attacker infrastructure, already an IOC, and treating it as "our host" would blur a distinction the schema keeps deliberately separate. The first implementation used Python's `ipaddress.IPv4Address.is_private` directly. Running it against the real `port_scan.jsonl` fixture immediately produced a wrong result: the attacker's address, `198.51.100.88`, got flagged as *private* and turned into a host `Entity` — because `is_private` also covers the RFC 5737 documentation ranges (`203.0.113.0/24`, `198.51.100.0/24`, `192.0.2.0/24`), and this project's synthetic datasets deliberately use those exact ranges to represent external attacker addresses, for the same reason Phase 4's datasets use `.example` domains: they're the RFC-sanctioned way to write a safe, obviously-fake-but-realistic-looking address. Same underlying pattern as Phase 4's `.example` conflict, caught the same way — by actually inspecting extraction output against real data, not by trusting an assumption. The fix: a precise RFC 1918 (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) / RFC 4193 ULA check, deliberately narrower than `is_private`, with a dedicated regression test (`test_port_scan_fixture_attacker_ip_is_not_treated_as_a_host_entity`) proving `198.51.100.88` is excluded and `10.0.0.5` (correctly alias-bridged to `web01.internal`) is included.

### Signals unify into two mechanisms, not five

`TODO.md` lists five correlation signals beyond time (shared IP, user, host, domain, IOC) and MITRE technique. In practice, four of them — IP, user, domain, and the general "shared IOC" — are the same mechanism, because `ipv4`/`ipv6`/`username`/`domain` are just `IOCType` values: any two alerts sharing an `IOC.id` (via `Alert.iocs`, already populated by Phase 4) get credit, regardless of which specific type the shared indicator happens to be. Only "shared host" needed genuinely new machinery (the `Entity` population above). MITRE technique correlation is real, tested code (`Alert.mitre_mappings` intersection) — at the time this phase was written it was **inert in practice**: no `Detection` row carried a technique mapping until Phase 8 populated `detection_mitre_mapping`, so this signal always contributed `0`. Built now, exactly like Phase 1 built the `alert_mitre_mapping` association object two phases before anything could populate it. **Update (Phase 8):** no longer inert — see [PHASE-8.md](PHASE-8.md).

### Weighted scoring, not graph clustering

`TODO.md`'s own Architecture Decisions flagged "weighted scoring vs. rule-based thresholds vs. graph-based clustering" as an open question. Weighted scoring won, for the same reason Phase 3's severity scoring did: it's explainable per-decision (every join records exactly which signals contributed how much) and consistent with a pattern the project already established, rather than introducing a second, more complex paradigm just for this one phase.

```
score = time_score + ioc_score + host_score + mitre_score
join if score >= 0.4
```

Weights (`time=0.2`, `ioc=0.4`, `host=0.3`, `mitre=0.1`) were chosen so that a shared IOC alone (`0.4`) or a shared host plus *any* time proximity (`0.3 + >0.1`) crosses the threshold, but time proximity alone (capped at `0.2`) never does on its own — pure "these happened near each other in time" is exactly the kind of weak, coincidence-prone basis for correlation that shouldn't merge two alerts by itself. The full derivation and every constant's reasoning are in `DEF.md`; what's worth restating here is that these numbers weren't reverse-engineered to force the scenario to pass — they were picked from the general design principle above, and *then* verified against the scenario (and confirmed correct via a genuine near-miss: the standalone `port_scan.jsonl` fixture targets the exact same host as the scenario, `web01.internal`, but ~2.7 hours later — shared host alone, `0.3`, correctly fails to cross `0.4` without time support, so it forms its own incident rather than merging).

### Chronological single-pass grouping, not full pairwise clustering

Alerts are processed in `first_event_at` order, each one scored against candidate incidents' **aggregate signatures** (the union of all their constituent alerts' IOCs/hosts/techniques) rather than against every individual alert already in them — this keeps the algorithm linear in the number of alerts, not quadratic. A closed or contained incident is never silently rejoined by new matching activity: an analyst's decision to close a case is a judgment call the pipeline shouldn't override automatically. A new alert that would otherwise match a closed incident starts a fresh one instead (verified by `test_closed_incident_is_not_rejoined`).

### Deterministic title generation

Per Phase 1's own description of `Incident.title` ("deterministically templated"): a single-alert incident gets `"{rule name} — {primary host or IP}"`; a multi-alert incident gets its distinct rule names, in chronological order of first appearance, joined by `" → "`. Run against the real scenario, this produces exactly the narrative its own Phase 2 README describes: `"SSH Brute Force → Suspicious Authentication Pattern → Port Scanning → Suspicious PowerShell Activity"` — not hand-tuned to say that, just the natural output of sorting real alerts by real timestamps.

## How it all connects

```
DEF.md § Phase 5 (host-identity stub, signals, scoring formula — written first)
   │
   ├──→ app/correlation/host_identity.py    (KNOWN_HOST_ALIASES stub)
   │        │
   │        └──→ app/correlation/host_extraction.py
   │                 (per-event host candidates; RFC1918/ULA-precise, alias-bridged)
   │                 │
   │                 └──→ app/correlation/entity_service.py
   │                          (upsert_host_entity, link_event, link_alert)
   │
   ├──→ app/correlation/base.py       (CorrelationConfig, AlertSignature, IncidentSignature)
   │        └──→ app/correlation/scoring.py :: score_alert_against_incident()
   │
   ├──→ app/correlation/title.py       (deterministic title from an incident's alerts)
   │
   └──→ app/correlation/pipeline.py :: run_correlation()
            │   pass 1: populate host Entities from every SecurityEvent
            │   pass 2: chronological alert grouping, scored against
            │            candidate incidents' aggregate signatures
            │
        app/correlation/cli.py
        (uv run python -m app.correlation.cli, recommended after ioc.cli)
```

Nothing here required a schema change — `Entity`, `EventEntity`, `AlertEntity`, `Incident.correlation_method` (JSONB) all already existed from Phase 1, built specifically so a phase like this one would have somewhere to write its output.

## Key decisions and why

| Decision | Reasoning |
|---|---|
| `KNOWN_HOST_ALIASES` as a small, explicit stub | Same reasoning as Phase 3's GeoIP resolver: no real CMDB, no paid API, and honesty about the limitation beats silently failing to solve the scenario or silently overclaiming a general capability |
| Only `entity_type="host"` populated this phase | `IOC` already covers ip/user/domain; duplicating them as `Entity` rows too would be redundant infrastructure with zero new correlating power |
| `SecurityEvent.source_host` used directly instead of per-source `normalized` fields | `endpoint`'s `normalized` shape has no host key at all — the original design draft was wrong about this, caught while implementing, fixed in the spec before the code shipped |
| RFC 1918/ULA-precise internal-address check instead of `ipaddress.is_private` | `is_private` also flags the RFC 5737 documentation ranges this project's own datasets use for attacker addresses — the same class of self-defeating conflict as Phase 4's `.example` issue, caught by inspecting real extraction output |
| Weighted scoring, not graph clustering | Explainable per-decision, consistent with Phase 3's severity-scoring precedent; avoids introducing a second correlation paradigm for one phase |
| Weights chosen from a stated design principle, then verified — not reverse-engineered to force the scenario to pass | The near-miss test (`port_scan.jsonl`, same host as the scenario, 2.7 hours later, correctly stays separate) is what actually validates the weights are doing real work, not just fitting one example |
| Aggregate incident *signatures* scored against, not pairwise alert comparison | Keeps the algorithm linear in alert count, not quadratic |
| Closed/contained incidents excluded from automatic rejoining | An analyst's decision to close a case is a judgment call the pipeline shouldn't silently override |
| No REST endpoint | Same Phase 9 deferral as Phase 3/4 — and the same honest dashboard consequence: static "Implemented," not live-checked "Working," until Phase 9 landed. **Update:** live now, via `GET /api/v1/incidents` — see [PHASE-9.md](PHASE-9.md) |

## Verification performed

- 30 new unit tests across scoring (`test_correlation_scoring.py` — time decay, IOC/host saturation, the specific threshold-crossing claims the weight table makes), host extraction (alias bridging, the RFC 5737 regression case), entity service (dedup, role-tagged linking), title generation (ordering, deduplication), the pipeline (merge, split, closed-incident, re-run idempotency of *processing* — new alerts only), and the CLI.
- `tests/integration/test_correlation_against_datasets.py` — the real pipeline (detect → extract IOCs → correlate) against the real scenario dataset: all 4 alerts land in one incident with the exact expected title; a second test proves the unrelated standalone `brute_force.jsonl` alert forms its own separate incident; a third is the RFC 5737 regression test described above, run against the real `port_scan.jsonl` fixture, not a synthetic-for-the-test-only case.
- Beyond the automated suite: the full combined dataset (every file across all 5 source types plus the scenario) was run through the complete `ingest → detect → extract → correlate` pipeline via the CLIs, producing 17 alerts grouped into 10 incidents. The resulting host `Entity` table was inspected directly — confirmed to contain only genuine internal hostnames and RFC 1918 addresses, zero attacker/documentation-range IPs. The standalone `port_scan.jsonl` incident (same target host as the scenario, ~2.7 hours later) was confirmed to have stayed separate from the scenario's incident, a real near-miss validating the weight tuning rather than a trivially-obvious split case.
- The same verification was repeated against a **live Postgres container**: `run_correlation()` executed directly against existing data, with the resulting `incidents`, `entities`, `event_entity`, and `alert_entity` rows confirmed via direct `psql` queries, not just application-level assertions.
- `ruff check`/`ruff format --check` pass clean; all 192 backend tests pass together (157 pre-existing + 30 new correlation tests + 5 pre-existing tests re-verified after a small shared-utility refactor — see below).

## A small shared-code cleanup that came out of this phase

Phase 4's `upsert_ioc()` had a private `_aware()` helper working around SQLite's known tzinfo-loss-on-reload behavior (documented in `PHASE-4.md`). Phase 5's `upsert_host_entity()` needed the exact same handling. Rather than copy-pasting a second private copy, the helper was promoted to `backend/app/core/time.py` (`as_aware_utc`) and `ioc/service.py` was refactored to import it — a small, low-risk cleanup made in passing because the duplication became obvious while writing the second copy, not a planned task.

## What Phase 5 deliberately does not include

**No REST endpoint** — same Phase 9 deferral as Phase 3/4. **No `ip`/`user`/`domain` `Entity` population** — deliberately left to `IOC` (see above); if a future phase needs `Entity` rows for those types for some reason `IOC` can't serve, that's a decision for whoever needs it, not assumed here. **No re-scoring of already-correlated alerts** — once an alert has an `incident_id`, later pipeline runs never reconsider it, even if new evidence (a later IOC, a later alert) would have changed the original decision; this matches Phase 3/4's "new work only" re-run semantics rather than introducing a different one just for this phase. **No manual incident merge/split API** — an analyst overriding the automated grouping (splitting an incorrectly-merged incident, merging two the algorithm missed) is a Phase 9/10 concern once there's an API and UI to do it through.
