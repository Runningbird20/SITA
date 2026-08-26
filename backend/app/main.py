import logging
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.alerts import router as alerts_router
from app.api.analysis_results import router as analysis_results_router
from app.api.deps import require_auth
from app.api.detections import router as detections_router
from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.incidents import router as incidents_router
from app.api.iocs import router as iocs_router
from app.api.metrics import router as metrics_router
from app.api.mitre import router as mitre_router
from app.api.pipeline import router as pipeline_router
from app.api.recommendations import router as recommendations_router
from app.core.config import get_settings
from app.core.exceptions import InvalidQueryParameterError, NotFoundError, UnauthorizedError
from app.core.logging import configure_logging
from app.core.metrics import http_request_duration_seconds, http_requests_total
from app.core.rate_limit import check_rate_limit
from app.core.request_context import reset_request_id, set_request_id

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


@app.middleware("http")
async def request_id_and_metrics(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Stamps every request (and every log line emitted while handling it,
    via RequestIdFilter) with a request ID, and records HTTP-level metrics.
    See DEF.md § Phase 13.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = set_request_id(request_id)
    try:
        start = time.monotonic()
        logger.info("request started", extra={"method": request.method, "path": request.url.path})
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "unhandled exception while processing request",
                extra={"method": request.method, "path": request.url.path},
            )
            raise

        duration = time.monotonic() - start
        route = request.scope.get("route")
        path_template = route.path if route is not None else request.url.path

        http_requests_total.labels(
            method=request.method,
            path_template=path_template,
            status_code=str(response.status_code),
        ).inc()
        http_request_duration_seconds.labels(
            method=request.method, path_template=path_template
        ).observe(duration)
        logger.info(
            "request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": int(duration * 1000),
            },
        )
        response.headers["X-Request-ID"] = request_id
        _apply_security_headers(response, request.url.path)
        return response
    finally:
        reset_request_id(token)


def _apply_security_headers(response: Response, path: str) -> None:
    """Applied to every response (including error/blocked ones, since this
    runs in the outermost middleware after call_next returns) — see DEF.md
    § Phase 14.
    """
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # /docs and /redoc load their JS/CSS from a CDN — a strict CSP there
    # would break FastAPI's own interactive docs. Everything else is a pure
    # JSON API with nothing to load, so default-src 'none' is safe.
    if path not in ("/docs", "/redoc"):
        response.headers["Content-Security-Policy"] = "default-src 'none'"


@app.middleware("http")
async def security_gate(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Request body size cap and rate limiting, checked before the request
    reaches routing. See DEF.md § Phase 14. Runs inside
    request_id_and_metrics (added after it, so Starlette makes it the
    inner middleware) — a blocked request still gets a request ID, gets
    logged, and is counted in http_requests_total by its real status code.
    """
    settings = get_settings()

    content_length = request.headers.get("content-length")
    if content_length is not None and int(content_length) > settings.max_request_body_bytes:
        return JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "payload_too_large",
                    "message": f"Request body exceeds {settings.max_request_body_bytes} bytes",
                    "details": None,
                }
            },
        )

    client_key = request.client.host if request.client is not None else "unknown"
    allowed, retry_after = check_rate_limit(request.method, request.url.path, client_key)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "rate_limited",
                    "message": "Rate limit exceeded",
                    "details": None,
                }
            },
            headers={"Retry-After": str(int(retry_after) + 1)},
        )

    return await call_next(request)


@app.exception_handler(Exception)
async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    """Catch-all so an unhandled exception always produces the same
    structured error envelope (and a logged traceback with request-ID
    context, via the middleware above) instead of FastAPI's default,
    unstructured 500. See DEF.md § Phase 13.
    """
    logger.exception("Unhandled exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {"code": "internal_error", "message": "Internal server error", "details": None}
        },
    )


@app.exception_handler(UnauthorizedError)
async def handle_unauthorized(_: Request, exc: UnauthorizedError) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"error": {"code": "unauthorized", "message": exc.message, "details": None}},
        headers={"WWW-Authenticate": "Bearer"},
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


# health/metrics deliberately excluded from require_auth — see DEF.md §
# Phase 14 (network-restricted rather than app-token-gated, by convention).
app.include_router(health_router)
app.include_router(metrics_router)

_auth = [Depends(require_auth)]
app.include_router(events_router, dependencies=_auth)
app.include_router(alerts_router, dependencies=_auth)
app.include_router(incidents_router, dependencies=_auth)
app.include_router(iocs_router, dependencies=_auth)
app.include_router(detections_router, dependencies=_auth)
app.include_router(analysis_results_router, dependencies=_auth)
app.include_router(recommendations_router, dependencies=_auth)
app.include_router(mitre_router, dependencies=_auth)
app.include_router(pipeline_router, dependencies=_auth)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Bare API root has nothing of its own to show — send a human
    browsing to it straight to the interactive docs instead of a 404.
    """
    return RedirectResponse(url="/docs")
