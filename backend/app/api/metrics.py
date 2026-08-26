"""Exposes app/core/metrics.py's registry in standard Prometheus text
exposition format. See DEF.md § Phase 13.

Root-level, not under /api/v1 — matching both Prometheus's own scrape
convention and this project's existing precedent of /healthz being
unprefixed.
"""

import os

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest, multiprocess

router = APIRouter(tags=["health"])


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    """PROMETHEUS_MULTIPROC_DIR set (docker-compose.prod.yml's multi-worker
    setup — see DEF.md § Phase 14, "Multi-process metrics (post-roadmap)")
    means each worker wrote its own counters to a file in that directory
    instead of this process's in-memory registry; a fresh CollectorRegistry
    + MultiProcessCollector merges them all for this one scrape. Checked
    per-request, not cached, since which mode is active never changes
    after process startup — the cost is a directory read only when
    multiprocess mode is actually on.
    """
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
