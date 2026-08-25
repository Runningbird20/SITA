# Frontend: Build Status Dashboard — Completion Report

Status: complete. This document explains what was built, how the pieces fit together, and why each decision was made — same format as the `PHASE-N.md` reports, but this isn't one of them: it's not a numbered phase from [TODO.md](../TODO.md). It's a cross-cutting meta-tool, requested directly rather than derived from the roadmap, and it will be **replaced** (not extended into) by the real Phase 10 frontend once that phase starts. See [README.md](../README.md#loading-synthetic-security-event-data) for the user-facing description and [CLAUDE.md](../CLAUDE.md#repository-map) for the maintenance rule this component comes with.

## Goal

By this point the project had three completed backend phases (0–2) and zero frontend code beyond the unmodified Vite template. The ask was direct: make the frontend show, at a glance, what's actually working — separated by phase, with a gray/green/red status dot per phase. The constraint that shaped every decision below: the dot colors had to mean something *real*. A dashboard that hardcodes "Phase 2: green" the day it's written and never updates again is worse than no dashboard — it actively misleads. So the design goal became: every phase's status must be either a live check against the running backend, or honestly `not_implemented`, with no third option where a status is asserted without evidence.

## What was built

### The phase manifest (`frontend/src/data/phases.ts`)

One entry per roadmap phase (0–15), each an object with `id`, `title`, `goal` (pulled directly from that phase's `**Goal:**` line in `TODO.md`, kept in sync so the dashboard and the roadmap never describe a phase differently), and an `evaluate` function:

```ts
export type PhaseStatusValue = "implemented" | "not_implemented" | "broken" | "checking";

export interface Phase {
  id: number;
  title: string;
  goal: string;
  evaluate: (status: BackendStatus) => PhaseStatusValue;
}
```

Two kinds of `evaluate` function exist, and the manifest is explicit about which each phase uses:

- **`liveCheck(isWorking)`** — wraps a phase-specific predicate with shared "loading" and "backend unreachable" handling, so each live-checked phase only has to state what "working" means for it, not re-derive the loading/unreachable states every time.
- **`notImplemented`** — a constant function that always returns `"not_implemented"`, used for every phase (3–15) that has no built backend surface yet.

Phases 0–2 use `liveCheck`; phases 3–15 use `notImplemented`. No phase is hardcoded to `"implemented"` anywhere in the codebase — that status value is only ever reached by a live check succeeding.

### The live checks themselves

| Phase | What "working" means | How it's checked |
|---|---|---|
| 0 — Project Foundation | The backend process is up and answering at all | `/healthz` returns any response |
| 1 — Core Data Model | The database layer is actually connected, not just the process | `/healthz`'s `database` field equals `"ok"` |
| 2 — Event Ingestion | The ingestion route is genuinely registered on the running server, not just present in source | `/api/v1/events/{source_type}` exists as a key in the live `/openapi.json` schema, **and** the database check above also passes |

The Phase 2 check is the one worth explaining: it would have been easy to just check "does `/healthz` return 200" and call that good enough for every phase, but that wouldn't actually distinguish "Phase 2's ingestion endpoint exists" from "the server happens to be up." Reading the live OpenAPI schema and checking for the specific route is a genuine test that the ingestion router is mounted in the running process — not a static assumption, and not a destructive test either (it doesn't POST fake data just to prove the endpoint exists). **No backend code changes were required** to support this — FastAPI already auto-generates `/openapi.json`, and `/healthz` already existed from Phase 0.

### The backend status hook (`frontend/src/hooks/useBackendStatus.ts`)

`useBackendStatus(pollIntervalMs)` is the one place that actually talks to the network. It fetches `/healthz` and `/openapi.json` in parallel (`Promise.all`), on mount and then every 15 seconds, each request bounded by a 5-second `AbortController` timeout so a hung backend can't leave the dashboard stuck showing "checking" forever — it fails over to `"broken"` within 5 seconds instead. It exposes a single `BackendStatus` object (`loading`, `reachable`, `healthz`, `openApiPaths`, `error`, `checkedAt`, `refresh`) that every phase's `evaluate` function reads from — one fetch cycle, sixteen phases evaluated against it, not sixteen independent network calls.

### The API client (`frontend/src/api/client.ts`)

A thin wrapper: `API_BASE_URL` (read from `import.meta.env.VITE_API_BASE_URL`, falling back to `http://localhost:8000` for native `npm run dev` where that env var isn't set), `fetchHealthz()`, and `fetchOpenApiPaths()` (which fetches `/openapi.json` and reduces it to a `Set<string>` of route paths — the dashboard only ever needs "does this path exist," not the full schema). Kept deliberately separate from the hook so the fetch logic is independently testable and reusable once Phase 10 needs its own API client for real domain data.

### The status dot and phase row (`frontend/src/components/`)

`StatusDot` renders the colored dot plus a text label (`Working` / `Not implemented` / `Broken` / `Checking…`), driven entirely by a `data-status` attribute so all the color logic lives in CSS, not inline styles or conditional class names in the component. The "checking" state reuses the gray dot with a pulse animation rather than introducing a fourth color — the ask was specifically for three colors (gray/green/red), so the transient loading state had to be a variation on one of those, not a new one. `PhaseRow` lays out one phase's number, title, one-line goal, and status dot; a phase's border color also shifts subtly (green/red tint) so a scan down the list doesn't rely on the small dot alone.

### The dashboard shell (`frontend/src/App.tsx`)

Header (title, subtitle, overall backend-connectivity indicator with the API base URL and last-checked time, manual refresh button), a summary bar (counts of working/broken/not-implemented), the phase list itself, and a footer stating outright which phases are live-checked and which aren't — so nobody has to infer that from the dot color alone. The whole Vite template (counter button, hero image, docs/social links) was removed, along with its now-unused assets (`hero.png`, `react.svg`, `vite.svg`, `public/icons.svg`).

### Styling (`frontend/src/index.css`, `App.css`, per-component `.css` files)

A dark, monospace-accented theme (CSS custom properties for the palette: `--color-green`/`--color-red`/`--color-gray` plus glow/border variants), matching the direction TODO.md's Phase 10 already specifies for the eventual real dashboard ("dark-mode-friendly SOC aesthetic") — not because this *is* that dashboard, but so replacing it later doesn't mean starting the visual language from zero.

## How it all connects

```
TODO.md phase Goal lines ──→ data/phases.ts (title + goal text kept in sync)
                                    │
                                    ├─→ evaluate: liveCheck(...)  [phases 0–2]
                                    │        reads BackendStatus from:
                                    │
                                    │    hooks/useBackendStatus.ts
                                    │        │  (polls every 15s, 5s timeout)
                                    │        ▼
                                    │    api/client.ts
                                    │        │  fetchHealthz()      → GET /healthz
                                    │        │  fetchOpenApiPaths() → GET /openapi.json
                                    │        ▼
                                    │    (the real, running FastAPI backend)
                                    │
                                    └─→ evaluate: notImplemented  [phases 3–15]
                                             (no network call — nothing to check yet)

App.tsx ──→ for each phase: PhaseRow(phase, phase.evaluate(backendStatus))
                                             │
                                             ▼
                                        StatusDot (color driven by data-status)
```

Nothing in this component talks to any backend endpoint beyond `/healthz` and `/openapi.json` — no domain data (events, alerts, incidents) is fetched or displayed here, since none of that has a stable API shape yet (that's Phase 9, then Phase 10 proper).

## Key decisions and why

| Decision | Reasoning |
|---|---|
| Every phase status is either a live check or explicitly `not_implemented` — never a hardcoded `"implemented"` | The entire point of the dashboard is that its claims are trustworthy; a hardcoded green dot is exactly the kind of thing that goes stale and starts lying |
| Phase 2's check reads the live `/openapi.json` for the specific route, not just a generic health ping | Distinguishes "this phase's actual surface is mounted" from "the server process happens to be running" — a meaningfully stronger claim |
| No backend changes made to support this | `/healthz` and `/openapi.json` already existed; building a bespoke "phase status" API would have been backend work explicitly out of scope for a frontend-only request |
| "Checking" reuses the gray dot with a pulse animation instead of adding a fourth color | The user asked for three colors specifically (gray/green/red); a transient loading state had to be a variation on one of those, not a new one |
| One shared `useBackendStatus` hook feeds all sixteen phases, rather than each phase fetching independently | One fetch cycle serves every phase's evaluation; avoids sixteen redundant network calls on every poll tick |
| 5-second `AbortController` timeout per request | A hung backend must resolve to `"broken"` within a bounded time, not leave the dashboard showing "checking" indefinitely |
| `CLAUDE.md` updated to require updating `phases.ts` when a phase's implementation status changes | Matches the project's existing "keep the documentation honest" discipline (README/DEF.md/PHASE-N.md) — a dashboard that goes stale is worse than the TODO.md checklist going stale, since it visually asserts correctness |
| Old Vite template assets deleted rather than left unused | Dead files that used to be referenced by now-deleted markup are just clutter; nothing else in the project references them |

## Verification performed

- `npm run build` (`tsc -b && vite build`) succeeds with zero TypeScript errors.
- `npm run lint` (ESLint, flat config, typescript-eslint + react-hooks/react-refresh) passes clean.
- `npm run format:check` (Prettier) passes clean.
- Every new source file was fetched directly through the running Vite dev server (`curl http://localhost:5173/src/...`) and returned `200` for each — confirms Vite's transform pipeline (esbuild/React plugin) accepts every file with no syntax or transform errors, not just that `tsc` is satisfied.
- The live backend was queried directly (`curl /healthz`, `curl /openapi.json`) and the actual responses (`{"status":"ok","database":"ok"}`, paths including `/api/v1/events/{source_type}`) were traced by hand through each phase's `evaluate` function, confirming phases 0–2 resolve to `"implemented"` and phases 3–15 resolve to `"not_implemented"` given real data — not assumed behavior.
- The Docker frontend image was rebuilt and the container confirmed serving the new code (`docker compose up -d --build frontend`, `curl http://localhost:5173/` → `200`).
- **Not verified**: an actual rendered screenshot. This environment has no browser or screenshot tool available, so the visual result (layout, color rendering, animation) was not directly observed — only the build, lint, transform pipeline, and underlying data logic were confirmed. Flagged explicitly rather than claimed.

## Addendum: a third status tier (static green "Implemented")

The original design (above) had exactly two live outcomes — green `"implemented"` or red `"broken"` — plus gray `"not_implemented"` for anything unbuilt, on the theory that a status should either be verified live or honestly unclaimed. Phase 3 broke that binary in a way worth recording: it shipped fully complete (7 rules, 99 passing tests, verified against both SQLite and Postgres — see [PHASE-3.md](PHASE-3.md)) but deliberately without a REST endpoint, since Phase 9 owns the API surface and building one early just for the dashboard would have meant redoing it later. That left no HTTP surface for `liveCheck` to check — and the original two-tier model had no honest way to represent "this is done, but nothing pings it right now." Falling back to gray would have been just as misleading as the hardcoded-green anti-pattern the original design was built to avoid, in the opposite direction: gray reads as "not built," which was no longer true.

The fix was a third `PhaseStatusValue`, `"implemented_static"` — same green dot as a live `"implemented"`, but labeled "Implemented" instead of "Working," and asserted from a phase's own completion report rather than computed from a runtime response. `frontend/src/data/phases.ts` now documents the distinction directly on the `Phase.evaluate` type: use `liveCheck(...)` whenever a real HTTP surface exists (always preferred), use the new `staticImplemented` helper only for a phase that's genuinely complete per its own `PHASE-N.md`, and never for partial or in-progress work — the gray/not-implemented default still applies until a phase is actually done. `CLAUDE.md`'s maintenance rule was updated to describe all three outcomes explicitly, so a future session extending this manifest doesn't have to rediscover the reasoning from the diff.

Verified: `npm run build`, `npm run lint`, and `npm run format:check` all pass clean with the new status value threaded through `StatusDot`'s label map and CSS (`data-status="implemented_static"` styled identically to `"implemented"`), `PhaseRow`'s border-color selector, and `App.tsx`'s summary counts (which merge `implemented` + `implemented_static` into one "N implemented" tally, since both are green). The running Docker frontend container (bind-mounted `src/`, so no rebuild needed) was confirmed serving the updated `phases.ts` and page shell via `curl`.

## What this deliberately does not include

No real domain data (events, alerts, incidents, IOCs) — this dashboard only ever asks "is a phase's backend surface present and healthy," never "show me the data." No historical status tracking (each load/poll is a fresh check; nothing is persisted). No auth (matches the rest of the project pre-Phase-14). No live checks for phases 4–15 (Phase 3 is the one static-green exception, see the addendum above) — deliberately not guessed at, since guessing a route name that later implementation doesn't match would produce a false negative (or worse, a false positive against an unrelated coincidental route) that's harder to notice than an honest gray dot. When each of those phases is actually built, its `evaluate` function should be added to `phases.ts` as part of that phase's own completion work, per the rule recorded in `CLAUDE.md`.
