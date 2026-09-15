# SITA — What's Next

All 15 roadmap phases in [TODO.md](TODO.md) are complete. This file is different from that: it's not tracking commitments or open questions from the original plan — it's a candid list of what would make this project meaningfully better if someone picked it up next, written from having built and verified every line of it.

Nothing here is a promise or a roadmap. It's organized roughly by effort-vs-impact, with the reasoning behind each idea so a future contributor (human or otherwise) can judge whether it's still worth doing rather than taking it on faith.

---

## AI quality — the honest gap this project already measured

Phase 12's own evaluation is the argument that started this: a live run against a small local model (`qwen2.5:0.5b`) scored **0% grounding rate** and produced a confirmed hallucinated `"ransomware"` classification with zero supporting evidence (see [docs/evaluation_methodology.md](docs/evaluation_methodology.md)). That's not a bug — it's real, measured evidence that small local models produce fluent-but-ungrounded triage text. Few-shot prompting, a grounding-aware retry, and a dashboard feedback signal have since been built for this (see `TODO.md`'s Architecture Decisions Tracker) — this is what's still open:

- **Re-run the same evaluation against the actual configured default model** (`CyberCrew/notmythos-8b` as of this writing, not `qwen2.5:0.5b` or the earlier-recommended `llama3.1:8b-instruct-q4_K_M`) — this project has never measured its own live default's quality, only a smaller stand-in, and the model default itself has since changed again. Now doubly worth doing: to get a real number, and to see whether the few-shot examples and grounding retry above actually move it. Requires a running Ollama instance with the model pulled (a real multi-gigabyte download) — not done in this pass because Docker wasn't available in the environment this work was done in.

## Detection and correlation depth

- **Real GeoIP / real asset inventory** — skipped for now. Both `[[geoip-resolver-stub]]` and `[[host-identity-stub]]` were deliberately left as stubs (see [TODO2.md](TODO2.md)) because nothing in this project's own data currently justifies the extra dependency; that calculus changes the moment real log sources are involved, not before, so this stays open rather than being built ahead of an actual need.

## Real ingestion, not just synthetic data

A real syslog listener (RFC 5424) and a file-tail ingester for local `auth.log`-style files were added post-roadmap — see [Documentation/DEF.md](Documentation/DEF.md#post-roadmap-addition-real-ingestion-syslog--file-tail). Still open:

- Further out: a Kafka/webhook consumer for cloud log sources (CloudTrail, etc.) — meaningfully more infrastructure, only worth it if this project is heading toward a real deployment rather than a portfolio piece. Skipped for the same reason in this pass.

## Operability and UX polish

All four items here — scheduled pipeline runs, incident notifications, CSV/PDF export, and live SSE updates — were built post-roadmap. See [Documentation/DEF.md](Documentation/DEF.md#post-roadmap-addition-operability-scheduled-runs-notifications-export-live-updates).

## Testing and quality bar

Frontend coverage enforcement, load/stress testing at scale and under concurrency, and a mutation-testing pass on the highest-stakes modules were all added post-roadmap — see [Documentation/DEF.md § Phase 11](Documentation/DEF.md#post-roadmap-addition-frontend-coverage-floor) and its "mutation testing" and "load/stress testing" sections. Still open:

- **Screenshots in `docs/images/` are static**, captured once. There's no process (automated or otherwise) keeping them in sync with UI changes — fine for now, but worth a reminder next time the dashboard's look changes meaningfully.

## Bigger bets (a new phase's worth of scope each)

- **Kubernetes/Helm manifests and a real horizontal-scaling story** — a genuinely different scope than "docker compose up," only worth it if this stops being a single-operator local tool. Skipped for now: this environment has no Kubernetes cluster to build or verify against, and the calculus described above hasn't changed.

A conversational interface with an incident, and analyst feedback closing the loop into rule tuning, were both built post-roadmap — see [Documentation/DEF.md § Phase 7](Documentation/DEF.md#post-roadmap-addition-a-conversational-interface-with-an-incident) and [§ Phase 3](Documentation/DEF.md#post-roadmap-addition-rule-tuning-suggestions-from-analyst-feedback) respectively.
