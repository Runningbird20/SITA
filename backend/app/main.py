import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.alerts import router as alerts_router
from app.api.analysis_results import router as analysis_results_router
from app.api.detections import router as detections_router
from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.incidents import router as incidents_router
from app.api.iocs import router as iocs_router
from app.api.mitre import router as mitre_router
from app.api.pipeline import router as pipeline_router
from app.api.recommendations import router as recommendations_router
from app.core.config import get_settings
from app.core.exceptions import InvalidQueryParameterError, NotFoundError
from app.core.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

settings = get_settings()

_TAGS_METADATA = [
    {"name": "events", "description": "Ingested security events, and ingestion itself."},
    {"name": "alerts", "description": "Deterministic detection-rule firings."},
    {"name": "incidents", "description": "Correlated groups of alerts, with nested detail."},
    {"name": "iocs", "description": "Extracted, validated indicators of compromise."},
    {"name": "detections", "description": "Deterministic detection rule definitions."},
    {
        "name": "analysis-results",
        "description": "AI-generated triage output — always scoped to an incident or alert, "
        "always distinguishable from deterministic fields.",
    },
    {"name": "recommendations", "description": "Suggested next steps, rule-based or AI-generated."},
    {"name": "mitre", "description": "The locally vendored MITRE ATT&CK technique subset."},
    {
        "name": "pipeline",
        "description": "Trigger the full deterministic-then-AI pipeline, for demo purposes.",
    },
    {"name": "health", "description": "Liveness/readiness."},
]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(
        "SITA backend starting",
        extra={"environment": settings.environment, "llm_provider": settings.llm_provider},
    )
    yield
    logger.info("SITA backend shutting down")


app = FastAPI(
    title=settings.app_name,
    description="Local-first security incident triage platform. Deterministic detection, "
    "correlation, and MITRE mapping are always distinguishable from AI-assisted analysis — "
    "see the `analysis-results` tag.",
    version="0.1.0",
    lifespan=lifespan,
    openapi_tags=_TAGS_METADATA,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(NotFoundError)
async def handle_not_found(_: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "not_found", "message": str(exc), "details": None}},
    )


@app.exception_handler(InvalidQueryParameterError)
async def handle_invalid_query_parameter(
    _: Request, exc: InvalidQueryParameterError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {"code": "invalid_query_parameter", "message": exc.message, "details": None}
        },
    )


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "details": jsonable_encoder(exc.errors()),
            }
        },
    )


app.include_router(health_router)
app.include_router(events_router)
app.include_router(alerts_router)
app.include_router(incidents_router)
app.include_router(iocs_router)
app.include_router(detections_router)
app.include_router(analysis_results_router)
app.include_router(recommendations_router)
app.include_router(mitre_router)
app.include_router(pipeline_router)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Bare API root has nothing of its own to show — send a human
    browsing to it straight to the interactive docs instead of a 404.
    """
    return RedirectResponse(url="/docs")
