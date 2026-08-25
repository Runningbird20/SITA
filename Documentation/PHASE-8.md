# Phase 8: MITRE ATT&CK Integration — Completion Report

Status: complete. See [DEF.md § Phase 8](DEF.md#phase-8-mitre-attck-integration) for the field-level dataset, rule-mapping table, and status log — this document is the narrative of how it got implemented and why. For the checklist itself, see [TODO.md](../TODO.md#phase-8-mitre-attck-integration).

## Goal

`MITRETechnique` and both its junction tables were designed and migrated all the way back in Phase 1. Phase 5's correlation scoring has read `alert.mitre_mappings` since it was written, and Phase 7's `mitre_suggestion` task has written to `AlertMitreMapping` since it was written — but `mitre_techniques` has been empty the entire time, so every one of those code paths has been running against nothing. Phase 8 is the phase that makes that data real: ground the system in a recognized security framework using local data, with zero runtime dependency on attack.mitre.org or any ATT&CK API, and in doing so switch on two features that were already built and waiting.

## What was built

### A curated 6-technique dataset, not a full Enterprise vendor

`data/mitre/techniques.json` covers exactly the 7 existing detection rules — `T1110`/`T1110.001`/`T1110.003` (Brute Force and two sub-techniques), `T1078` (Valid Accounts), `T1046` (Network Service Discovery), `T1059.001` (PowerShell). This resolves the `[[mitre-data-source]]` open question in favor of "curated subset matching implemented detection rules" over a full Enterprise-matrix snapshot — the same "don't build ahead of what's needed" principle that shaped Phase 1's schemas and Phase 2's CLI-vs-endpoint choice. Refreshing it is manual: add an entry to the JSON file and re-run the loader whenever a new rule needs a technique not yet vendored.

### Rules declare their techniques the same way they declare everything else

`DetectionRule` gained one new `ClassVar`, `mitre_technique_ids: ClassVar[tuple[str, ...]] = ()`, set directly on each of the 7 rule classes alongside their existing `category`/`default_severity`/`default_config`. No separate mapping table to keep in sync with the rule registry — the mapping lives where the rest of a rule's metadata already lives, and `ensure_detections_seeded()` (Phase 3) already treats rule classes as the source of truth for everything about a `Detection` row.

### Two sync passes, each idempotent and order-independent

`run_mitre_mapping()` in `app/mitre/pipeline.py`:

1. **Detection ↔ MITRETechnique**: links each rule's declared techniques onto its `Detection` row, skipping any `technique_id` not yet present in the local table.
2. **Alert ↔ MITRETechnique (`source='rule'`)**: for every `Alert`, links whatever techniques its `Detection` now carries — this is the pass that actually makes Phase 5's `alert.mitre_mappings` non-empty for the first time.

Both passes are written to self-heal regardless of what order things run in: if `run_mitre_mapping()` runs before the loader has ever populated `mitre_techniques`, it does nothing and moves on; running it again after the loader catches everything up on the next call. This was written deliberately and verified directly (`test_self_heals_once_techniques_are_loaded_late`) rather than assumed, since the same property was asserted-but-inert for Phase 5's correlation signal until this phase.

### The technique display model

TODO.md's task list asked for a model with "technique ID, name, tactic, evidence (which alert/event triggered it), confidence, and source (`rule` vs `llm`)." `app/mitre/rollup.py::incident_technique_rollup()` groups an incident's `AlertMitreMapping` rows by technique into one `IncidentTechniqueEntry` per technique, each carrying a list of `TechniqueEvidence` (which alert, which source, and — only for `source='llm'` — the confidence of the `AnalysisResult` that produced it). No separate agreement/disagreement flag: `entry.sources` is a `{'rule'}`/`{'llm'}`/`{'rule', 'llm'}` set built directly from the evidence, so a consumer can already tell whether the rule layer and the LLM agree without a redundant computed field — the same reasoning Phase 7 used for the identical junction table. `techniques_by_tactic()` (the `[STRETCH]` task) is a plain groupby for the eventual Phase 10 ATT&CK-matrix view.

### One CLI, because the two steps are never run independently

`uv run python -m app.mitre.cli [--since ...]` runs the loader and both mapping passes in one call. There's no real scenario where loading techniques without syncing the mapping, or vice versa, is useful — so this is one combined command rather than the two-CLI split some earlier phases used for genuinely separable concerns.

## How it all connects

```
data/mitre/techniques.json (vendored, checked into the repo)
   │
   ▼
app/mitre/loader.py :: load_techniques()
   │  upserts MITRETechnique rows, by technique_id
   ▼
app/mitre/pipeline.py :: run_mitre_mapping()
   │
   ├─ pass 1: Detection.mitre_techniques  ←  DetectionRule.mitre_technique_ids (Phase 3 rule classes)
   │
   └─ pass 2: AlertMitreMapping(source='rule')  ←  each Alert's Detection.mitre_techniques
              │
              ▼
   app/correlation/pipeline.py :: _build_alert_signature()   (Phase 5, unmodified)
        reads alert.mitre_mappings → AlertSignature.technique_ids → mitre_score
              │
              ▼
   app/mitre/rollup.py :: incident_technique_rollup()
        groups AlertMitreMapping across an incident's alerts (source='rule' AND source='llm', the latter from Phase 7's mitre_suggestion task)
```

## Key decisions and why

| Decision | Reasoning |
|---|---|
| Curated 6-technique subset, not a full Enterprise snapshot | Resolves `[[mitre-data-source]]`; matches this project's established "no abstraction/data ahead of what's needed" pattern rather than vendoring hundreds of techniques nothing in the system references |
| `tactic` stores one value per technique row, even for techniques (like `T1078`) that canonically span multiple tactics | Phase 1's schema already fixed `tactic` as a single `VARCHAR`; each row uses whichever tactic is most relevant to *how this project's rules actually use the technique*, documented as a deliberate simplification rather than silently picking one |
| `repeated_auth_failures` maps to parent `T1110`, not a sub-technique | The rule's own signal (distributed volume, no username/password evidence) doesn't justify claiming Password Guessing or Password Spraying specifically — mapping to the more specific sub-technique the rule can't actually back up would overclaim |
| `mitre_technique_ids` declared on the rule class, not a separate lookup table | Consistent with every other piece of rule metadata (`category`, `default_severity`, `default_config`) already living on the class; avoids a second place that can drift out of sync with the rule registry |
| Both sync passes silently skip techniques not yet in the local table, rather than raising | Makes the passes order-independent and self-healing — the same property Phase 4's IOC pipeline and Phase 7's `mitre_suggestion` already rely on for their own "runs against partial state" cases |
| No new "agreement/disagreement" field on the display model | `AlertMitreMapping.source` already distinguishes rule- from LLM-sourced rows; `IncidentTechniqueEntry.sources` computes agreement directly from that, matching Phase 7's identical decision for the same table |
| One combined CLI (load + map) instead of two | The two steps are always run together in practice; splitting them would be an abstraction with no real use case behind it |
| Correlation code (`app/correlation/`) was not touched | Phase 5 already reads `alert.mitre_mappings` — Phase 8's job was only to make that data real, not to change how it's used; verified directly rather than assumed (see below) |

## Verification performed

- 18 new unit tests: `test_mitre_loader.py` (loads the real vendored dataset with correct counts, idempotent re-run, create/update against a custom temp dataset), `test_mitre_rule_mapping.py` (every rule declares at least one technique, every declared `technique_id` exists in the real vendored file), `test_mitre_pipeline.py` (both sync passes against a real detection-pipeline-produced alert, no mappings created before the loader runs, self-healing once it does, idempotent re-run, `since` scoping, and a dedicated regression confirming Phase 5's unmodified scoring function now returns a nonzero `mitre_score`), `test_mitre_rollup.py` (grouping by technique, rule+LLM sources on the same technique both showing up with correct per-evidence confidence, empty-rollup and tactic-grouping cases), `test_mitre_cli.py` (exit codes, argument parsing).
- `ruff check`/`ruff format --check` pass clean. Full backend suite: 262 passed, 1 skipped (Phase 6's live-Ollama test), 0 failed.
- Verified against a live Postgres container, run from the host via `uv run` with `DATABASE_URL` pointed at the docker-compose Postgres's published port (the backend container itself only bind-mounts `backend/app`, not the repo-root `data/` directory the loader reads — the same reason `app.ingestion.cli` is already a host-run command, not a `docker compose exec` one; not a new finding, just confirming the existing convention holds for this phase's CLI too). Inside a rolled-back transaction: `load_techniques` created all 6 rows, `run_mitre_mapping` produced real `AlertMitreMapping(source='rule')` rows against a genuine detection-pipeline alert, and — the specific claim this phase exists to make true — Phase 5's untouched `score_alert_against_incident` returned a nonzero `mitre_score` (`0.1`, the full configured weight) against that real data, where it had returned `0.0` on every prior phase's verification since nothing had ever populated `alert.mitre_mappings` before.

## What Phase 8 deliberately does not include

**No REST endpoint** — same Phase 9 deferral as every prior deterministic-pipeline phase; the dashboard showed Phase 8 as static "Implemented," not live-checked "Working," until Phase 9 landed (**update:** it's live now, via `GET /api/v1/mitre-techniques` — see [PHASE-9.md](PHASE-9.md)). **No full ATT&CK Enterprise matrix** — a deliberate 6-technique curated subset instead, per the resolved open question; expanding it is a one-line JSON addition whenever a new rule needs a technique not yet vendored. **No automatic re-vendoring/update job** — the dataset is a hand-curated local file, refreshed manually, not synced from any upstream source at build or runtime. **No UI matrix view** — `techniques_by_tactic()` exists as the grouping primitive Phase 10's eventual ATT&CK-matrix visualization will need, but there's no frontend surface to render it yet. **No confidence adjustment to LLM `mitre_suggestion` results based on rule agreement** — Phase 7 explicitly deferred this until Phase 8 gave it something real to compare against; that comparison is now possible via `incident_technique_rollup()`'s `sources` field, but wiring it back into `AnalysisResult.confidence` would mean revisiting Phase 7's code under a phase boundary that isn't Phase 7's, so it's left as a documented follow-up rather than done here.
