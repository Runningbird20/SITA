"""Exposes app/core/metrics.py's registry in standard Prometheus text
exposition format. See DEF.md § Phase 13.

Root-level, not under /api/v1 — matching both Prometheus's own scrape
convention and this project's existing precedent of /healthz being
unprefixed.
"""

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter(tags=["health"])


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
