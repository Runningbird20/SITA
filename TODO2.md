# SITA — Architecture Decisions Tracker

All 15 phases in [TODO.md](TODO.md) are complete, and every architecture
decision this project was carrying is now resolved. This file started as
an extract of the still-open items from TODO.md's now-removed
"Architecture Decisions / Open Questions" section (that section originally
had twelve entries; six were already tagged `— resolved` there with a
phase and a DEF.md link). Since that section no longer exists in TODO.md's
working tree, this file is the standing home for tracking these decisions
going forward — including any new ones that come up later.

Each entry is tagged with the same `[[tag]]` identifier used elsewhere in
the repo (DEF.md, code comments) so it stays findable regardless of which
file currently holds the write-up.

---

## Resolved

### `[[recommended-local-model]]` Recommended local model — resolved

Original ask: needs a concrete choice (e.g., a Llama 3.x or Qwen2.5
instruct variant in the 7–8B range) balancing hardware fit,
structured-output reliability, and demo latency; pin it in `.env.example`
with a documented smaller fallback for constrained hardware.

**Resolution:** two-tier, not a single pinned model. `OLLAMA_MODEL`
defaults to `qwen2.5:0.5b` — small (~400MB), fast, chosen specifically so
a first `docker compose up`/`scripts/demo.sh` run never forces a
multi-gigabyte download or serious hardware just to prove the pipeline
works. This is a quick-start convenience, explicitly not a quality claim.
For real triage quality, the README's "Choosing an Ollama model" section
now documents an explicit recommendation to switch to a 7–8B instruct
model (`llama3.1:8b-instruct-q4_K_M`), with the actual tradeoff spelled
out — download size, RAM, CPU-only latency, and the measured quality gap
(the 0.5B default has produced at least one confirmed hallucinated
classification in this project's own evaluation results). See
[DEF.md § Phase 6, "Recommended local model — resolved (post-roadmap)"](Documentation/DEF.md#recommended-local-model--resolved-post-roadmap).

### Orchestration: hand-rolled vs LangChain/LangGraph — resolved

Original framing: leaning toward implementing the `LLMProvider`
abstraction and triage pipeline ourselves, revisiting only if a specific
need (e.g., complex multi-step agent loops) couldn't be reasonably
hand-rolled.

**Resolution:** confirmed correct by everything built after this question
was first raised, not just left as a leaning. The hand-rolled
`LLMProvider` abstraction went on to absorb three more providers post-roadmap
(OpenAI, Anthropic, LM Studio) alongside Ollama and Mock — five providers,
zero framework, no code outside `app/llm/` needing to change. No multi-step
agent loop has ever been needed anywhere in this project's pipeline
(detection → correlation → MITRE mapping → triage is a fixed, deterministic
sequence, not an agentic loop). Nothing points at revisiting this.

### `[[event-schema-design]]` Event schema design specifics — resolved

Original ask: the high-level `SecurityEvent` shape was sketched in Phase
1/2, but the exact field-level design (how much source-specific detail
lives in a `raw` JSON blob vs. promoted normalized columns) needed to be
finalized once real sample data from all 5 source types was in hand.

**Resolution:** settled in practice, now confirmed rather than assumed.
Real sample data for all 5 source types has existed since Phase 2
(`data/synthetic_events/`), and the split Phase 2 finalized — raw payload
preserved verbatim, source-specific detail in a `normalized` JSON blob,
nothing promoted to dedicated columns — has been built against and used
completely unchanged through every one of the following 13 phases,
including Phase 12's independent held-out evaluation dataset and Phase
15's synthetic-data-loading bootstrap script. See
[DEF.md § Phase 2, "Normalized Shape"](Documentation/DEF.md#2-normalized-shape-securityeventnormalized--finalized).

### `[[host-identity-stub]]` Hostname ↔ IP identity resolution — resolved

Original ask: Phase 5's `KNOWN_HOST_ALIASES` is a small, hardcoded map
covering only the two hosts this project's own scenario dataset ties
together — extend it manually as new scenarios are added, or build a real
(still-local, no paid API) asset-inventory mechanism?

**Resolution:** extend manually. Building general asset-inventory
infrastructure for a map that has only ever needed two entries across this
project's entire lifetime would be speculative scope with no exercising
use case — exactly what this project's own engineering principles (see
root `CLAUDE.md`, "don't build ahead of what's needed") argue against.
Documented directly in the stub itself:
`backend/app/correlation/host_identity.py`.

### `[[geoip-resolver-stub]]` Real GeoIP data source for `impossible_travel` — resolved

Original ask: `StaticGeoIPResolver` is a small hardcoded table covering
only the IPs used in this project's own synthetic datasets — bundle a free
offline dataset (e.g., a trimmed MaxMind GeoLite2 snapshot), or leave the
stub in place and document the rule as demo-only?

**Resolution:** leave the stub, document as demo-only. MaxMind's free
GeoLite2 tier now requires a registered account and license key even at
no cost — real onboarding friction for a stub whose only actual job is
making this project's own fixture scenario computable, not genuine
geolocation. Not worth the dependency for a demo-only rule. Documented
directly in the stub itself: `backend/app/detection/geoip.py`.

### `[[detection-run-idempotency]]` Idempotent detection re-runs — resolved

Original ask: `run_detection()` didn't deduplicate — re-running it over an
already-processed time range created duplicate `Alert` rows. Needed a
dedup strategy (e.g., a fingerprint on `Alert` derived from `detection_id`
+ sorted matched event IDs) or a decision to rely entirely on callers
scoping `since` correctly.

**Resolution:** implemented the fingerprint approach, not just documented
a policy — this was the one item in this file with a real, already-observed
cost (it had forced a workaround in `scripts/demo.sh`, Phase 15).
`Alert.fingerprint` (SHA-256 of `detection_id` + sorted matched event IDs,
`UNIQUE` at the database level) makes a re-run over an overlapping window
a genuine no-op: `run_detection()` now reports `duplicates_skipped`
instead of silently creating duplicates. Verified against a real Postgres
instance, not just SQLite: re-running the full pipeline against an
already-populated demo database created 0 new alerts and reported
`duplicates_skipped: 17`, exactly matching the 17 real alerts already
present. See
[DEF.md § Phase 3, "Post-roadmap addition: idempotent detection re-runs"](Documentation/DEF.md#post-roadmap-addition-idempotent-detection-re-runs--resolves-detection-run-idempotency).
