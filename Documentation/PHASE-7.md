# Phase 7: AI-Powered Triage — Completion Report

Status: complete. See [DEF.md § Phase 7](DEF.md#phase-7-ai-powered-triage) for the field-level task registry, schemas, and status log — this document is the narrative of how it got implemented and why. For the checklist itself, see [TODO.md](../TODO.md#phase-7-ai-powered-triage).

## Goal

Phase 6 proved the `LLMProvider` mechanism works — retries, structured-output validation, derived confidence — using an illustrative schema with no real content behind it. Phase 7 is where that machinery starts doing real work: six LLM-assisted reasoning tasks over every incident, each one clearly labeled as AI output and layered on top of, never replacing, the deterministic detection/correlation pipeline built in Phases 3–5. Per the project's own engineering principle, the LLM is never the sole source of truth for a security decision — severity, detection, and correlation stay entirely rule-owned; Phase 7 only adds a second, separately-attributed opinion alongside them.

## What was built

### Six tasks, one registry, one orchestrator

`backend/app/triage/pipeline.py`'s `TASKS` list pairs each of Phase 1's six `AnalysisTaskType` values with a prompt builder, a `prompt_version` tag, and a Pydantic response schema. `run_triage()` walks every targeted incident and, for each task, builds the request, calls `LLMProvider.generate()` (Phase 6's machinery, unmodified), and persists the result as an `AnalysisResult` row. This is the first code in the project that actually calls `generate()` from a real pipeline step.

### Context building: one render function, six prompts

`app/triage/context.py` walks an `Incident`'s ORM relationships (`alerts`, each alert's `detection`, `iocs`, `mitre_mappings`) into a plain `IncidentContext` dataclass, then `render_context_block()` turns it into the one deterministic text block every one of the six prompts embeds verbatim. Building this once and reusing it six times means "what the model was actually shown" is auditable from a single function, not six near-duplicate ones that could drift apart.

### Severity explanation carries its own guardrail

Every prompt in `app/triage/prompts.py` opens with a shared disclaimer that the model is assisting, not deciding. The `severity_explanation` prompt goes further: it hands the model the already-computed deterministic `Incident.severity` and each alert's `severity_factors` as given fact, and explicitly instructs it not to recompute or second-guess that number — only explain it. This is the one task where a rule violation (the LLM inventing its own severity) would be most tempting for a model to make, so it's the one task with an explicit guardrail in its own prompt text, not just the shared disclaimer.

### Idempotent by construction, not by a special-cased flag

Before calling `generate()` for a given `(incident, task_type)`, `run_triage()` checks whether an `AnalysisResult` already exists for that `incident_id`/`task_type`/`prompt_version` and skips if so. A plain re-run over unchanged incidents makes zero LLM calls and zero writes — the same "safe to run repeatedly" property Phase 4's IOC pipeline and Phase 5's correlation pipeline already have. `force=True` bypasses the check; bumping a task's `prompt_version` constant is the normal way to force just that one task to regenerate everywhere, following Phase 6's "prompt_version is a plain tag the caller owns" design.

### `investigation_steps` and `mitre_suggestion` have real side effects

Every task writes an `AnalysisResult` row; two of the six also populate other Phase 1 tables that were scaffolded but never written to before Phase 7:

- **`investigation_steps`**: each `InvestigationStep` in the validated output becomes one `Recommendation(source=llm, analysis_result_id=<this row>)`. This is a distinct code path from Phase 9's future rule-based recommendations — both share the one `Recommendation` table by design (Phase 1), separated only by `source`.
- **`mitre_suggestion`**: each suggested technique that has a matching row in the local `mitre_techniques` table becomes one `AlertMitreMapping(source=llm, analysis_result_id=<this row>)`, fanned out to every alert currently in the incident. Since `mitre_techniques` isn't populated until Phase 8 vendors real MITRE data, every suggestion fails that lookup today and no mapping rows are written — the raw suggestion is still preserved in `AnalysisResult.parsed_output` regardless, so nothing is lost while waiting on Phase 8.

### No new "disagreement" field — the schema already exposes it

`AlertMitreMapping` keeps `source='rule'` and `source='llm'` as separate rows per the original Phase 1 design. Phase 7 deliberately adds no extra "agreement"/"disagreement" flag anywhere: a consumer can already compute that by comparing the two `source` groups per alert directly from the data. Inventing a redundant field would violate the project's "provenance must be checkable from the data itself" principle by duplicating what the schema already exposes.

### A pipeline CLI, matching Phase 5/6's shape

`uv run python -m app.triage.cli [--incident-id UUID] [--since ...] [--force]` mirrors `app.correlation.cli`'s argument style. `--incident-id` scopes to one incident (useful for manual testing or targeted re-runs); `--since` filters by `Incident.last_activity_at`; `--force` bypasses idempotency. With no arguments it triages every incident using whichever provider `Settings.llm_provider` configures — `mock` by default, so running it does zero network calls out of the box.

## How it all connects

```
DEF.md § Phase 7 (task registry, idempotency rules, MITRE cross-check design — written first)
   │
   ├──→ app/triage/schemas.py     (6 response schemas — the `response_schema` per task)
   ├──→ app/triage/context.py     (build_incident_context, render_context_block)
   ├──→ app/triage/prompts.py     (6 prompt builders + PROMPT_VERSION_* tags)
   │
   ├──→ app/triage/pipeline.py :: run_triage()
   │        │  TASKS registry — one _TriageTask per AnalysisTaskType
   │        │  per incident: render context once, then per task:
   │        │    skip if AnalysisResult(incident, task, prompt_version) exists (unless force)
   │        │    else provider.generate(request, config)  ← Phase 6, unmodified
   │        │    persist AnalysisResult
   │        │    investigation_steps → Recommendation rows
   │        │    mitre_suggestion    → AlertMitreMapping rows (only for locally-known techniques)
   │        │
   │        └──→ app/llm/registry.py  (get_llm_provider(), default_llm_config() — Phase 6)
   │
   └──→ app/triage/cli.py
        (uv run python -m app.triage.cli [--incident-id] [--since] [--force])
```

`AnalysisResult`, `Recommendation`, and `AlertMitreMapping` were all designed and migrated in Phase 1 specifically for this moment — Phase 7 is the first code to actually write rows into any of them.

## Key decisions and why

| Decision | Reasoning |
|---|---|
| All six tasks are incident-scoped (`AnalysisResult.alert_id` always `None`) | Every task in TODO.md's list reasons about the incident as a whole (its alerts, IOCs, activity window) — none needed alert-level granularity, and `AnalysisResult` already supports both scopes if a future phase needs the alert-level one |
| `mitre_suggestion` fans a suggested technique out to every alert in the incident, rather than attributing it to one | The task is incident-scoped like the other five (one `AnalysisResult`, not one per alert), so there's no per-alert signal to attribute a suggestion to more precisely without inventing one; documented here as a deliberate simplification rather than hidden |
| No AlertMitreMapping rows are written until Phase 8 populates `mitre_techniques` | Same "real, tested code path, inert until Phase 8" pattern TODO.md already documents for Phase 5's shared-MITRE-technique correlation signal — the lookup-and-skip logic is exercised by tests today (`test_mitre_suggestion_without_local_technique_creates_no_mapping`), it just has nothing to match against yet |
| No "agreement"/"disagreement" field added to any schema | `AlertMitreMapping.source` already lets a consumer compute this by comparing rows — adding a redundant flag would duplicate data the schema already exposes, violating the project's own provenance principle |
| Idempotency keyed on `(incident_id, task_type, prompt_version)`, not a separate "already ran" flag | Reuses columns `AnalysisResult` already has; makes "bump the version to force regeneration" the one intentional mechanism, rather than adding a second concept alongside it |
| Confidence is not re-derived from rule-agreement for `mitre_suggestion` | DEF.md's `AnalysisResult.confidence` field mentions "agreement with rule-based signals" as a *possible* future confidence input, but there's no rule-mapped technique to agree or disagree with until Phase 8 exists — deferred rather than half-built against data that doesn't exist yet |
| Severity explanation prompt explicitly forbids recomputing severity | The one task where a model producing its own severity number would be most tempting and most damaging to the "LLM never owns a security decision" principle — worth a guardrail in the prompt text itself, not just the shared disclaimer every prompt carries |

## Verification performed

- 19 new unit tests: `test_triage_context.py` (incident/alert field mapping, IOC dedup across alerts, "none yet" rendering for empty MITRE mappings), `test_triage_prompts.py` (every prompt embeds the context block and asks for JSON, prompt versions are unique and fit the `AnalysisResult.prompt_version` column), `test_triage_pipeline.py` (one `AnalysisResult` per task type with real incidents built through the actual detection→correlation pipeline; `investigation_steps` creating the right `Recommendation` rows; `mitre_suggestion` creating no mapping when the technique doesn't exist locally and the correct mapping when it does; idempotent re-run producing zero new calls/rows; `force=True` regenerating everything; invalid/malformed output creating no `Recommendation`/`AlertMitreMapping`; `incident_id` and `since` scoping), `test_triage_cli.py` (exit codes, argument parsing).
- `ruff check` / `ruff format --check` pass clean. Full backend suite: 244 passed, 1 skipped (the live-Ollama test from Phase 6, correctly skipping in this environment), 0 failed.
- **A real bug found by live-Postgres verification, not by inspection**: every unit test above runs against in-memory SQLite (per this project's test convention), which does not enforce `VARCHAR` length. Running the pipeline against the project's actual `docker compose` Postgres container — seeding a real brute-force event burst, running it through `run_detection`/`run_correlation`, then `run_triage` with a `MockProvider` — surfaced a `StringDataRightTruncation` error: three of the six `prompt_version` tags (`triage-severity-explanation-v1`, `triage-attack-classification-v1`, `triage-investigation-hypothesis-v1`) exceeded `AnalysisResult.prompt_version`'s `VARCHAR(30)` column from Phase 1's schema. Fixed by shortening the three tags to fit, and added `test_prompt_versions_fit_the_analysis_result_column`, which reads the column's actual length from the model at test time rather than hardcoding `30`, so a future schema or tag change can't silently drift apart again. Verification was then re-run against the same live Postgres container (inside a rolled-back transaction, so nothing was left in the dev database) and confirmed clean: all 6 `AnalysisResult` rows persisted with `parsed_output` round-tripping through `JSONB` as a `dict`, 2 `Recommendation` rows from `investigation_steps`, and 1 `AlertMitreMapping` row from `mitre_suggestion` once a matching `MITRETechnique` row existed. This is the same "caught by actually running it, not by reading the code" pattern that found real bugs in Phase 4 (`.example` domains), Phase 5 (RFC 5737 ranges), and Phase 6 (the live-Ollama skip-check).
- Frontend dashboard updated to show Phase 7 as a static "Implemented" (same convention as Phase 3–6 — no REST endpoint to live-check yet). Alongside this, the dashboard's status coloring was split so live-checked "Working" phases render green and statically-asserted "Implemented" phases render yellow/amber, distinguishing "verified against a running backend just now" from "asserted from the phase's own test suite" at a glance, rather than collapsing both into the same green. `npm run lint`, `npm run format:check`, and `npm run build` all confirmed clean after both changes.

## What Phase 7 deliberately does not include

**No REST endpoint** — same Phase 9 deferral as every prior deterministic-pipeline phase; the dashboard showed Phase 7 as static "Implemented," not live-checked "Working," until Phase 9 landed (**update:** it's live now, via `GET /api/v1/analysis-results` — see [PHASE-9.md](PHASE-9.md)). **No prompt-template management system** — `prompt_version` stays a plain string tag per Phase 6's convention; there's still no need for a templating engine, just six functions returning strings. **No AlertMitreMapping rows in practice yet** — the write path is real and tested, but produces zero rows until Phase 8 vendors a local MITRE ATT&CK dataset into `mitre_techniques`; nothing is lost in the meantime since the raw suggestion stays in `AnalysisResult.parsed_output`. **No confidence adjustment from rule-agreement** — deferred to whenever Phase 8 gives `mitre_suggestion` something to actually agree or disagree with; Phase 6's retry-based confidence formula is used unmodified for all six tasks. **No UI panel** — Phase 10's job; Phase 7's "UI/API-level separation" requirement is satisfied structurally (every AI claim is an `AnalysisResult` row, distinguishable by definition from deterministic `Alert`/`Incident` fields) rather than visually, since there's no frontend surface for incidents yet.
