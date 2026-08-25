import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz(db: Session = Depends(get_db)) -> dict:
    """Liveness/readiness check: reports process status and DB connectivity.
    Kept dependency-light (no LLM provider check here) since this is polled
    frequently by Docker/orchestration health checks.
    """
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database health check failed")
        db_status = "unavailable"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "database": db_status,
    }
