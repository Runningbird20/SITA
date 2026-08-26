# SITA — What's Next

All 15 roadmap phases in [TODO.md](TODO.md) are complete. This file is different from that: it's not tracking commitments or open questions from the original plan — it's a candid list of what would make this project meaningfully better if someone picked it up next, written from having built and verified every line of it.

Nothing here is a promise or a roadmap. It's organized roughly by effort-vs-impact, with the reasoning behind each idea so a future contributor (human or otherwise) can judge whether it's still worth doing rather than taking it on faith.

---

## Security and deployment hardening

- **TLS.** Explicitly out of scope through Phase 14 (plain HTTP, stated as a local-only limitation — see [DEF.md § Phase 14](Documentation/DEF.md#phase-14-security-hardening)). A real deployment target needs this — either terminate TLS at a reverse proxy (nginx/Caddy in front of the stack) or document that requirement clearly for anyone deploying beyond `localhost`.
- **A real production Docker Compose profile.** `docker-compose.yml`'s `frontend` service still runs the `dev` target (hot-reload Vite server); the hardened, non-root `production` nginx stage Phase 14 built (`frontend/Dockerfile`) is never actually used by anything. Add a `docker-compose.prod.yml` (or a profile) that uses it, drops `--reload` from the backend's uvicorn command, and points at real TLS.
- **Multi-user / RBAC.** The single shared bearer token (`[[dashboard-auth]]`, resolved in Phase 14) was the right call for a single-operator local tool — but if this ever needs to serve more than one analyst, that's a real design project: accounts, roles (analyst vs. admin), and an actual audit trail of who did what (right now, nothing tracks *who* triggered a pipeline run or changed an alert's status).
- **Multi-process metrics/rate-limiting.** Both `app/core/metrics.py` (Prometheus registry) and `app/core/rate_limit.py` are in-process, single-worker state — stated clearly as a limitation at the time (Phase 13/14), but would silently under-count/under-limit the moment this runs behind more than one `uvicorn` worker. A shared store (Redis, or a Prometheus push-gateway for metrics) would be needed first.
- **Dependency scanning without a human in the loop.** `pip-audit`/`npm audit` run in CI (Phase 14) but nothing automatically opens a PR when a new advisory lands — Dependabot or Renovate would close that gap.

## AI quality — the honest gap this project already measured

Phase 12's own evaluation is the argument that started this: a live run against a small local model (`qwen2.5:0.5b`) scored **0% grounding rate** and produced a confirmed hallucinated `"ransomware"` classification with zero supporting evidence (see [docs/evaluation_methodology.md](docs/evaluation_methodology.md)). That's not a bug — it's real, measured evidence that small local models produce fluent-but-ungrounded triage text. Few-shot prompting, a grounding-aware retry, and a dashboard feedback signal have since been built for this (see `TODO.md`'s Architecture Decisions Tracker) — this is what's still open:

- **Re-run the same evaluation against the actual configured default model** (`CyberCrew/notmythos-8b` as of this writing, not `qwen2.5:0.5b` or the earlier-recommended `llama3.1:8b-instruct-q4_K_M`) — this project has never measured its own live default's quality, only a smaller stand-in, and the model default itself has since changed again. Now doubly worth doing: to get a real number, and to see whether the few-shot examples and grounding retry above actually move it. Requires a running Ollama instance with the model pulled (a real multi-gigabyte download) — not done in this pass because Docker wasn't available in the environment this work was done in.

## Detection and correlation depth

- **More detection rules.** Seven rules cover a real but narrow slice of attacker behavior (brute force, spraying, port scanning, PowerShell, impossible travel, and their variants). Natural next candidates: DNS tunneling/beaconing, lateral movement via unusual auth patterns between internal hosts, data exfiltration volume anomalies, privilege escalation patterns.
- **A statistical/anomaly layer alongside the deterministic rules.** Every current rule is threshold- or pattern-based, which is explainable but blind to "this is unusual for *this specific* environment" — a simple per-host/per-user baseline (e.g., z-score on event volume) would catch things fixed thresholds miss, without compromising the "deterministic rules own detection" principle (an anomaly score is still deterministic, just adaptive).
- **`[[detection-run-idempotency]]`'s fingerprint could extend to cross-rule dedup.** Right now a fingerprint prevents the *same* rule from re-alerting on the *same* events; it doesn't merge two different rules firing on overlapping evidence (correlation handles this at the incident level, but the alert list itself can still look noisy).
- **Real GeoIP / real asset inventory**, if this ever moves past a demo — both `[[geoip-resolver-stub]]` and `[[host-identity-stub]]` were deliberately left as stubs (see [TODO2.md](TODO2.md)) because nothing in this project's own data currently justifies the extra dependency. That calculus changes the moment real log sources are involved.

## Real ingestion, not just synthetic data

Every event in this project today is either hand-crafted synthetic data or generated by `app/evaluation/generate_dataset.py` / `app/benchmark/generate_load.py`. There's no actual log source connector. Reasonable next steps, cheapest first:

- A **Syslog listener** (RFC 5424, straightforward to hand-roll or use a small library) mapped onto the existing `auth`/`network` ingestion adapters — real logs from a real box, still fully local.
- A **file-tail ingester** for common local log formats (e.g., an nginx access log, `auth.log`) — lower effort than a network listener, and a compelling demo ("point it at your own machine's logs").
- Further out: a Kafka/webhook consumer for cloud log sources (CloudTrail, etc.) — meaningfully more infrastructure, only worth it if this project is heading toward a real deployment rather than a portfolio piece.

## Operability and UX polish

- **Background job execution for triage.** `POST /api/v1/pipeline/run` runs synchronously — for real Ollama/OpenAI/Anthropic calls, that's a request that can take minutes (Phase 15 measured ~5.5 minutes for a 10-incident, 60-call real Ollama run). A background task queue (even something lightweight like FastAPI's own `BackgroundTasks`, or `RQ` if more durability is needed) plus a status-polling endpoint would let the frontend show real progress instead of a blocked request.
- **Scheduled pipeline runs.** Nothing triggers detection/correlation/ triage on a cadence — it's always a manual `POST` or CLI invocation. A simple interval-based scheduler (even just a documented `cron` line calling the CLI) would make this feel like a running system rather than an on-demand tool.
- **Notifications.** No email/Slack/webhook fires when a new critical incident appears — for a "triage agent" pitch, that's a natural, relatively small feature (a `Notifier` interface parallel to `LLMProvider`'s design, since the project already has a clean pattern for swappable backends).
- **Export.** No way to get an incident or a set of incidents out as a PDF/CSV report — likely to come up in any real review of a SOC tool.
- **Live updates.** The dashboard polls; a WebSocket or SSE channel for "a new incident was just created" would be a nicer demo and isn't a large lift given the pipeline already has clear completion points to push from.

## Testing and quality bar

- **Frontend test rigor doesn't match the backend's.** 24 frontend tests vs. 432 backend tests, no enforced coverage threshold on the frontend (Phase 11 explicitly scoped the 95% floor to the backend only, noting the frontend suite "doesn't yet have enough surface for a threshold number to mean much" — that calculus should be revisited now that the frontend has grown across Phases 10, 14, 15, and the post-roadmap AI-quality work above).
- **No load/stress testing beyond Phase 12's benchmarks**, which measured throughput at a fixed, moderate scale (1500 events) — never pushed toward a breaking point or tested under concurrent write load.
- **No mutation testing anywhere** — coverage percentage confirms code *ran*, not that the assertions would actually catch a real regression. Even a small mutation-testing pass on the highest-stakes modules (correlation scoring, detection thresholds) would be a genuine signal boost.
- **Screenshots in `docs/images/` are static**, captured once. There's no process (automated or otherwise) keeping them in sync with UI changes — fine for now, but worth a reminder next time the dashboard's look changes meaningfully.

## Bigger bets (a new phase's worth of scope each)

- **Kubernetes/Helm manifests and a real horizontal-scaling story** — a genuinely different scope than "docker compose up," only worth it if this stops being a single-operator local tool.
- **A conversational interface with an incident** — right now AI triage is six fixed, one-shot tasks per incident. A chat-style "ask a follow-up question about this incident" would be a compelling demo feature and a natural extension of the existing `LLMProvider`/context-building machinery, but is a real scope addition (streaming responses, multi-turn context management, a new UI surface).
- **Analyst feedback closing the loop into rule tuning** — e.g., marking an alert as a false positive doesn't currently feed back into anything; over enough volume, that data could inform threshold adjustments (still deterministic, still explainable — the AI stays uninvolved in this loop, consistent with the project's core principle).
