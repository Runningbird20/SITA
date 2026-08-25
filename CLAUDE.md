# CLAUDE.md

Project instructions for Claude Code working in this repository. Read this before starting any work.

## What this project is

SITA (Local Security Incident Triage Agent) is a local-first security incident triage platform: ingest simulated security events → normalize → detect (deterministic rules) → extract IOCs → correlate into incidents → map to MITRE ATT&CK → AI-assisted triage (local LLM via Ollama, always clearly separated from deterministic output) → REST API → dashboard. No paid APIs, no required cloud dependency. See [README.md](README.md) for the pitch and quick-start, [TODO.md](TODO.md) for the full phased roadmap.

## Mandatory documentation workflow

This project tracks its own build process as a first-class deliverable — the phase-by-phase narrative is as much a part of the portfolio as the code. Because of that, **the following is not optional and not something to ask permission for** — it is a required part of finishing any unit of work, the same way running the tests before calling something done is required.

### The three documents that must stay current

1. **[TODO.md](TODO.md)** — the roadmap and checklist. Check off tasks as they're actually done (not before), with a short note on what was built or a link to where it's defined/documented. Never mark a task done that wasn't verified.
2. **[Documentation/DEF.md](Documentation/DEF.md)** — the running, cross-phase data dictionary. Every schema, contract, interface, or format that a phase introduces gets defined here, organized in one section per phase, **before or alongside** the code that implements it (see "Definitions before code" below). Update the relevant phase's status note (`defined, not yet implemented` → `implemented`) once the code lands.
3. **[Documentation/PHASE-N.md](Documentation/)** — one file per phase (`PHASE-0.md`, `PHASE-1.md`, `PHASE-2.md`, ...). See the required structure below.

### When to update them

**Whenever you complete a phase, materially progress a phase that's already in flight, or start meaningful work on a new phase**, before considering that unit of work finished:

- [ ] Update **`README.md`** if the change affects: the stack table, quick-start steps (new required commands, new services, new env vars), or the `## Status` section's phase-completion summary.
- [ ] Update **`Documentation/DEF.md`** with any new/changed schema, contract, or interface definitions for the phase — keep it a living document, not a historical snapshot. If a later phase's implementation reveals that an earlier phase's definition needs to change (a renamed field, a corrected relationship), update the original section and note the change rather than silently drifting from it.
- [ ] Write or update **`Documentation/PHASE-N.md`** for every phase that is **completed or in progress** — not just fully-finished ones. A phase that's underway gets a PHASE-N.md reflecting what's done so far and what's still open; when it completes, that same file is updated to its final state (don't create a second file for "the rest of" a phase).
- [ ] Update the corresponding checklist items in **`TODO.md`**, checked off only for what's actually verified working, with a note or link pointing at where it's defined (DEF.md) and documented (PHASE-N.md).

If a task is small enough that it doesn't correspond to any phase in TODO.md (a typo fix, a dependency bump), none of this applies — use judgment. The bar is: "did this change what a phase's completion report or the data dictionary claims is true?"

### Required structure for `Documentation/PHASE-N.md`

Follow the pattern established by `PHASE-0.md` through `PHASE-2.md` — don't reinvent it per phase:

- **Header** — status line (`complete`, or `in progress` with what remains), links back to the relevant `DEF.md` section and `TODO.md` phase.
- **Goal** — why this phase exists, in the context of the phases before and after it.
- **What was built** — one subsection per major component, explaining what it does and any non-obvious implementation choices (not a restatement of the code — explain what a reader can't get from `git diff` alone).
- **How it all connects** — a diagram or short flow showing how this phase's pieces link to each other and to prior phases.
- **Key decisions and why** — a table: decision, reasoning. Every deliberate deviation from an earlier plan (DEF.md, TODO.md, or a prior phase's stated approach) belongs here, explained, not silently done.
- **Verification performed** — what was actually run and confirmed, not assumed. Distinguish "verified" from "written but not yet run" explicitly (see Phase 0's CI/pre-commit example) — never claim something works without having run it.
- **What this phase deliberately does not include** — scope boundary, so a future phase doesn't have to guess whether something was forgotten or intentionally deferred.

### Definitions before code

This project's established pattern (Phase 1, Phase 2) is: write the field-level schema/contract in `Documentation/DEF.md` first, then implement against it. Keep doing this for new phases — it's cheaper to fix a relationship or a field name in a Markdown table than after a migration or an adapter exists. When asked to "define Phase N" without implementing yet, that means: write the `DEF.md` section only, check off the pure "definition" TODO.md tasks (not the "implement X" ones), and don't write implementation code.

## Engineering principles (do not violate)

- **The LLM is never the sole source of truth for a security decision.** Deterministic rules own severity scoring, IOC validation, detection, correlation IDs, and baseline MITRE mappings. The LLM assists with summarization, explanation, classification, and investigation suggestions — always recorded as an `AnalysisResult` (or equivalent), always distinguishable from deterministic output, never merged into a deterministic field.
- **No paid APIs or required cloud dependency**, ever, without an explicit ask from the user.
- **Provenance must be checkable from the data itself** — given any alert, incident, recommendation, or MITRE mapping, it should be answerable whether a rule or a model produced it without needing external context.
- Don't build ahead of what's needed. No Create/Update schemas for endpoints that don't exist yet, no abstractions for hypothetical future requirements — this repo's history (Phase 1's schemas, Phase 2's CLI-vs-endpoint choice) has explicit examples of scope deliberately deferred; follow that pattern rather than second-guessing it.

## Key commands

```bash
# Backend (from backend/)
uv sync                              # install deps
uv run alembic upgrade head          # apply migrations (required before running/testing against a fresh DB)
uv run uvicorn app.main:app --reload # run dev server
uv run pytest                        # run tests
uv run ruff check .                  # lint
uv run ruff format .                 # format
uv run python -m app.ingestion.cli <source_type> <path.jsonl>  # batch-import synthetic events

# Frontend (from frontend/)
npm run dev
npm run lint
npm run format:check
npm run build

# Full stack
docker compose up --build
docker compose exec backend uv run alembic upgrade head
```

## Repository map

- `backend/app/` — FastAPI app: `api/` (routes), `core/` (config, logging), `db/` (session, dialect-portable types), `models/` (SQLAlchemy ORM), `schemas/` (Pydantic I/O), `ingestion/` (Phase 2 adapters/service/CLI), and one package per future phase (`detection/`, `correlation/`, `mitre/`, `llm/`, `triage/`, `recommendations/`, `ioc/`).
- `backend/alembic/` — migrations, wired to read `DATABASE_URL` from `app.core.config`, never hardcoded.
- `data/synthetic_events/` — checked-in synthetic datasets (per-source-type + multi-stage scenarios), validated by `backend/tests/integration/test_synthetic_datasets.py`.
- `frontend/` — React + TypeScript + Vite.
- `Documentation/` — `DEF.md` (data dictionary) and `PHASE-N.md` (per-phase reports). See above.
- `docs/architecture.md` — living, high-level system overview; expand incrementally, don't duplicate `DEF.md`'s field-level content into it — link instead.
- `TODO.md` — the roadmap, plus an "Architecture Decisions / Open Questions" section at the bottom tracking things still undecided (e.g., recommended local model, correlation scoring strategy).
