"""In-process metrics registry — every metric declared once, here, at import
time. See DEF.md § Phase 13. Mirrors app/core/config.py's precedent of
declaring the whole configuration surface in one discoverable place, rather
than ad-hoc Counter()/Histogram() calls scattered per module.

In-memory, per-process (prometheus_client's default registry) — correct for
this project's documented single-process run mode, would under-count across
multiple worker processes without a push-gateway or shared registry.
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
