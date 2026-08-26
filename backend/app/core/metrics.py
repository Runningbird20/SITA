"""Metrics registry — every metric declared once, here, at import time.
See DEF.md § Phase 13. Mirrors app/core/config.py's precedent of
declaring the whole configuration surface in one discoverable place,
rather than ad-hoc Counter()/Histogram() calls scattered per module.

Metric declarations here are unchanged whether the process is running
single- or multi-worker — Counter/Histogram objects work the same either
way. What differs is how a scrape reads them back: single-process (the
documented default) reads this module's in-memory registry directly;
multi-process (PROMETHEUS_MULTIPROC_DIR set — see docker-compose.prod.yml)
has each worker write to its own file in that directory instead, and
app/api/metrics.py merges them at scrape time via
prometheus_client.multiprocess. See DEF.md § Phase 14, "Multi-process
metrics (post-roadmap)". Counter/Histogram are both natively
sum-aggregated across processes by that merge — this file has never
declared a Gauge, which would need special multiprocess handling
(default aggregation is "most recent," rarely what you want across
workers) this project has accordingly never had to add.
"""

from prometheus_client import Counter, Histogram

events_ingested_total = Counter(
    "sita_events_ingested_total",
    "Security events successfully ingested.",
    ["source_type"],
)

ingestion_errors_total = Counter(
    "sita_ingestion_errors_total",
    "Raw records rejected during ingestion (malformed/invalid).",
    ["source_type"],
)

alerts_created_total = Counter(
    "sita_alerts_created_total",
    "Alerts created by a detection rule firing.",
    ["rule_key"],
)

alerts_duplicate_skipped_total = Counter(
    "sita_alerts_duplicate_skipped_total",
    "Findings skipped because an Alert with the same fingerprint already "
    "exists — a re-run over an overlapping window, not a new detection.",
    ["rule_key"],
)

alerts_cross_rule_duplicate_skipped_total = Counter(
    "sita_alerts_cross_rule_duplicate_skipped_total",
    "Findings skipped because a different rule already created an Alert "
    "over the exact same matched-event set this run — see DEF.md § Phase 3 "
    "'Post-roadmap addition: cross-rule fingerprint dedup'.",
    ["rule_key"],
)

detection_rule_duration_seconds = Histogram(
    "sita_detection_rule_duration_seconds",
    "Time spent evaluating a single detection rule against loaded events.",
    ["rule_key"],
)

incidents_created_total = Counter(
    "sita_incidents_created_total",
    "New incidents created by correlation (an alert didn't match any open incident).",
)

incidents_updated_total = Counter(
    "sita_incidents_updated_total",
    "Existing incidents updated by correlation (an alert joined an open incident).",
)

llm_calls_total = Counter(
    "sita_llm_calls_total",
    "LLM provider calls, one per network attempt (retries count separately).",
    ["provider", "model", "task_type", "status"],
)

llm_call_duration_seconds = Histogram(
    "sita_llm_call_duration_seconds",
    "Latency of a single LLM provider call attempt.",
    ["provider", "model", "task_type"],
)

http_requests_total = Counter(
    "sita_http_requests_total",
    "HTTP requests handled, by route template and status code.",
    ["method", "path_template", "status_code"],
)

http_request_duration_seconds = Histogram(
    "sita_http_request_duration_seconds",
    "HTTP request handling latency, by route template.",
    ["method", "path_template"],
)
