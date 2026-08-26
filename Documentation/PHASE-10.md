# Phase 10: Frontend — Completion Report

Status: complete. See [DEF.md § Phase 10](DEF.md#phase-10-frontend) for the routing table, typed-client conventions, and status log — this document is the narrative of how it got implemented and why. For the checklist itself, see [TODO.md](../TODO.md#phase-10-frontend). For the pre-existing build-status page this phase relocates rather than deletes, see [FRONTEND.md](FRONTEND.md).

## Goal

Nine phases of deterministic pipeline and REST API work have had no visual home beyond `/openapi.json` and a build-status meta-tool. Phase 10 is the payoff: a real SOC-style dashboard a reviewer can actually click through — overview, alerts, incidents, incident detail with a genuinely distinct AI analysis panel, IOC exploration, detection rules, and a MITRE technique library — all sourced from Phase 9's live API, nothing hardcoded or mocked.

## What was built

### The build-status page didn't get deleted — it moved

`/status` is the unmodified Phases-0-9 build-status page (`StatusPage.tsx`, moved from the old `App.tsx`), still answering a question the real dashboard can't: "is each backend phase actually live right now, independent of whether it has any data." `App.tsx` becomes the route table instead, and `/` through `/mitre` are the genuine product. This was a direct instruction, not a default — the alternative (replacing `/` and throwing the status page away) would have lost a real diagnostic tool for a cosmetic win.

### One new dependency, chosen deliberately

`react-router-dom` is the only new runtime dependency this phase adds. Every other piece — the typed API client, the data-fetching hook, the charts — is hand-rolled, continuing this project's pattern from the LLM provider abstraction and the original API client (`fetchHealthz`/`fetchOpenApiPaths`). Multi-page routing with deep links, browser history, and nested layouts is a genuinely solved problem, not a portfolio-signal opportunity the way the LLM provider was — so it gets a real dependency instead of a hand-rolled router.

### A hand-mirrored typed client, not generated

`api/types.ts` mirrors every Pydantic schema Phase 9 exposes by hand. No OpenAPI codegen tooling was added — the schema surface is small (8 resources, mostly flat `Read` shapes) and stable enough that hand-mirroring costs less than wiring up and maintaining a generator, and it keeps the "own the code that matters" signal this project has kept everywhere else. `api/resources.ts` has one typed function per endpoint, and `client.ts` gained `apiFetch`/`ApiError`, which decodes Phase 9's `{"error": {code, message, details}}` envelope into a real typed error every page can render — the original `fetchJson`/`fetchHealthz`/`fetchOpenApiPaths` were left untouched, since `/status` still needs exactly what they already did.

### One data-fetching hook, not a query library

`useApiQuery<T>(fetcher, deps)` is used by every one of the 8 pages, mirroring the `loading`/`data`/`error`/`refetch` shape `useBackendStatus` already established for the status page. No `react-query`/SWR-style cache library — this dashboard has independent views that each fetch once per navigation, not the shared-cache/background-refetch problem those libraries solve. Getting this hook right took two iterations: the first version mutated a ref during render and called `setState` synchronously at the top of the effect body, both of which `eslint-plugin-react-hooks` v7's stricter (React Compiler-era) rules correctly flag as real hazards, not style nitpicks — the ref write moved into its own effect, and the loading/error resets moved inside the async function the effect kicks off, so nothing runs directly in the effect's synchronous top level.

### The AI panel: one visual treatment, applied everywhere, backed by real provenance

TODO.md's `[HIGH VALUE]` requirement was unmistakable visual separation for AI-generated content. The mechanism is the same one the backend already enforces: every AI claim is only ever attached to a `source`/`analysis_result_id`-carrying row (`AnalysisResult`, an LLM-sourced `Recommendation`, an LLM-sourced `AlertMitreMapping`), so the frontend's job was purely to render that existing distinction consistently, never to infer or guess it. One CSS treatment (`--color-ai`, a violet accent with a left border and an "AI-generated" badge) is applied in exactly three places: the incident detail page's AI analysis cards, LLM-sourced recommendations, and LLM-sourced entries in the MITRE technique list — the same component (`<AiBadge />`) in all three, so there's no risk of the treatment drifting between call sites.

### Incident detail: the centerpiece, built from real nested data

`GET /incidents/{id}` already returns everything the page needs in one call (Phase 9's `IncidentDetail`, extended this phase with `alert_count` and `entities`). The one piece of real logic on this page is `renderAnalysisBody()`, which switches on `AnalysisResult.task_type` to render each of Phase 7's six structured output shapes appropriately (a summary, a list of hypotheses, prioritized steps, MITRE suggestions, etc.) rather than dumping raw JSON — and falls back to an honest "did not validate" message when `validation_status !== "valid"`, which turned out to be the common case in verification (see below).

### MITRE page: a technique library, not a live "observed" matrix — a documented boundary, not a silent gap

TODO.md asked for "a matrix-style view highlighting techniques observed in the environment." Phase 9 exposes the vendored technique list and per-incident/per-alert rollups, but no environment-wide "which techniques has anything ever mapped to" aggregate — building one would mean either a new backend endpoint or an N+1 client-side fetch of every incident's rollup. Neither was built speculatively; `/mitre` instead renders the technique library grouped by tactic (Phase 8's `techniques_by_tactic()` concept, reimplemented client-side over the flat list). Recorded here explicitly rather than silently shipped as if it were the "observed" view TODO.md described.

### Small, honest Phase 9 amendments, not scope creep

Four fields Phase 9 didn't anticipate because no UI consumer existed yet to reveal the need: `IncidentRead.alert_count` (computed via an aggregated `GROUP BY`, not a per-row lazy-load — the incident list page needs it without an N+1), `IncidentDetail.entities` (TODO.md's own incident-detail task asks for entities; Phase 5's `Entity` model already existed, it just never had a nested field), and `IOCRead.alert_ids`/`.event_ids` plus a `search` query param on `GET /iocs` (the IOC explorer's "links back to source alerts/events" and "searchable" requirements). All four are documented in-place in DEF.md's Phase 9 endpoint reference, not silently changed out from under what that section already claimed.

## How it all connects

```
Phase 9 REST API (/api/v1/*)
   │
   ▼
api/types.ts (hand-mirrored schemas)  +  api/client.ts (apiFetch, ApiError, buildQuery)
   │
   ▼
api/resources.ts (fetchAlerts, fetchIncident, runPipeline, ...)
   │
   ▼
hooks/useApiQuery.ts  ←── every page calls this, never fetch() directly
   │
   ▼
pages/{Overview,Alerts,Incidents,IncidentDetail,Iocs,Detections,Mitre}Page.tsx
   │        (components/ui/{QueryState,Badges,Pagination}.tsx, styles/dashboard.css)
   ▼
App.tsx routes  ──→  components/Layout.tsx (nav + "Run pipeline" button)
   │
   └── /status  ──→  pages/StatusPage.tsx (unchanged Phases 0-9 build-status page)
```

## Key decisions and why

| Decision | Reasoning |
|---|---|
| `/status` moved, not deleted | Explicit instruction; it also still answers a real question ("is each phase's backend surface live right now") the new dashboard was never designed to answer |
| `react-router-dom` added; typed client and data-fetching hook still hand-rolled | Routing is a solved problem this project gains nothing hand-rolling; the API client and query logic are small, stable, and part of the same "own the code" signal as the LLM provider abstraction |
| No query-caching library | ~8 independent views, each fetching once per navigation — not the shared-cache/background-refetch problem those libraries exist to solve |
| MITRE page shows the technique library grouped by tactic, not a live "observed" cross-reference | No environment-wide aggregate endpoint exists, and building one (or N+1-fetching every incident's rollup client-side) wasn't justified by what TODO.md actually needs demonstrated; documented as a boundary, not hidden |
| `alert_count`/`entities`/`alert_ids`/`event_ids`/`search` added to Phase 9's schemas this phase, not deferred | Each is a small, directly TODO.md-driven need with an obvious, low-risk implementation (an aggregate query, a dedup rollup identical in shape to the existing IOC one, explicit schema construction) — deferring them would have meant shipping pages that visibly couldn't do what their own task description asked for |
| One `<AiBadge />` component, reused verbatim in all three AI-attribution call sites | Prevents the visual treatment from drifting between the incident AI panel, recommendations, and MITRE evidence — a single source of truth for "this is what AI-generated content looks like" |

## Verification performed

- `npm run build` (`tsc -b && vite build`), `npm run lint` (ESLint, including the stricter React Compiler-era hook rules), and `npm run format:check` (Prettier) all pass clean.
- 11 new Vitest unit/component tests (`npm run test`): `lib/aggregate.test.ts` (day-bucketing and tactic-grouping, including empty-input cases), `components/ui/Badges.test.tsx`, `components/ui/Pagination.test.tsx` (including the boundary cases — first page, last/partial page, empty result set).
- Verified against the live `docker compose` stack, and a real bug was caught doing so, not assumed away: `npm run build` passing on the host does not mean the running container can serve the new code, since only `frontend/src` is bind-mounted, not `node_modules` — every route-importing file 500'd in the container ("Failed to resolve import react-router-dom") until `docker compose up -d --build frontend` picked up the new dependency. After the rebuild, every route (`/`, `/incidents`, a deep-linked `/incidents/{id}`, `/alerts`, `/iocs`, `/detections`, `/mitre`, `/status`) was confirmed serving `200` directly via `curl`, including through Vite's dev-server SPA fallback for client-side routes.
- The MITRE loader (`app.mitre.cli`, run from the host per the established convention — the container doesn't mount `data/`) and `POST /pipeline/run` were both run for real against the live Postgres stack, and the resulting `GET /incidents/{id}` response was inspected directly: 2 correlated alerts, real correlation scoring signals (nonzero `mitre_score`, confirming Phase 8's integration is still live), 2 deduplicated IOCs, 1 entity, 1 MITRE technique with rule-sourced evidence, and 6 `AnalysisResult` rows — the exact shape `IncidentDetailPage` is built to render, verified against genuine data rather than fixtures.
- **A characteristic worth recording, found during that same verification, not a bug**: every one of those 6 `AnalysisResult` rows had `validation_status=invalid`, because `get_llm_provider()`'s unconfigured `MockProvider()` (this project's real default, per Phase 6) returns a bare `{}` for every call — it was never designed to fabricate plausible content, only to prove the retry/validation machinery works. `renderAnalysisBody()` handles this correctly (an honest message, not a crash), which is what actually satisfies TODO.md's "no dead ends or unhandled empty states" requirement — but a reviewer wanting to see populated AI panels needs `LLM_PROVIDER=ollama` with a real model pulled. Left as Phase 6/7's own established behavior rather than patched here.

## What Phase 10 deliberately does not include

**No Create/Update/Delete anywhere in the UI** — matches Phase 9's read-only API surface exactly; the first real mutation (most likely `Recommendation.status`) waits for an actual need, not a speculative one. **No live "observed techniques" MITRE matrix** — see the key-decisions table; `/mitre` is a technique library view. **No authentication** — matches every phase before Phase 14. **No client-side caching/offline support** — outside what any current requirement asks for. **No dedicated alert-detail page** — TODO.md's task list asks for an alert *list* view, not a detail page the way it explicitly does for incidents; alerts are viewed inline (list, incident detail, detection recent-firings) rather than through their own route. **No real-time updates (WebSockets/polling)** — every page fetches on navigation and via manual refetch (the "Run pipeline" button's own result banner); nothing in TODO.md's task list asked for live-updating views.
