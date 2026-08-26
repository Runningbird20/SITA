import logging

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

_LLM_HEALTH_CHECK_TIMEOUT_SECONDS = 2.0


def _check_llm() -> str:
    """ "not_configured" for Mock (nothing to reach, and no network call is
    made — this endpoint is polled frequently, so Mock stays free). "ok" /
    "unavailable" for Ollama, from one short-timeout GET against its own
    lightweight /api/tags endpoint (not a real generation call).
    """
    settings = get_settings()
    if settings.llm_provider != "ollama":
        return "not_configured"
    try:
        response = httpx.get(
            f"{settings.ollama_base_url}/api/tags", timeout=_LLM_HEALTH_CHECK_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        return "ok"
    except httpx.HTTPError:
        logger.warning("LLM health check failed", extra={"provider": settings.llm_provider})
        return "unavailable"


@router.get("/healthz")
def healthz(db: Session = Depends(get_db)) -> dict:
    """Liveness/readiness check: reports process status, DB connectivity,
    and (when an LLM provider is actually configured) LLM reachability.
    Kept dependency-light — short timeouts, no network call at all for
    Mock — since this is polled frequently by Docker/orchestration health
    checks.
    """
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database health check failed")
        db_status = "unavailable"

    llm_status = _check_llm()

    return {
        "status": "ok" if db_status == "ok" and llm_status != "unavailable" else "degraded",
        "database": db_status,
        "llm": llm_status,
    }
