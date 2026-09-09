from __future__ import annotations

import logging
import re
import time
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import TimeoutError as DatabasePoolTimeout

logger = logging.getLogger("buyer_dash.api")
SLOW_REQUEST_MS = 1_000.0
_PORTAL_TOKEN_PATH = re.compile(r"(/commerce-portal/)[^/]+", re.IGNORECASE)


def _safe_log_path(request: Request) -> str:
    """Return a route-shaped path without bearer-like portal secrets.

    FastAPI exposes the matched route template after routing (for example
    ``/api/v1/commerce-portal/{token}/offers``). Prefer that template so no path
    parameter can accidentally enter logs. The regex fallback protects error and
    not-found paths where a route object may not have been attached yet.
    """

    route = request.scope.get("route")
    template = str(getattr(route, "path", "") or "").strip()
    if template:
        return template
    return _PORTAL_TOKEN_PATH.sub(r"\1{token}", request.url.path, count=1)


def _serializable_validation_errors(exc: RequestValidationError) -> list[dict]:
    """Preserve validation detail without leaking non-JSON Python exception objects."""
    rows: list[dict] = []
    for error in exc.errors():
        safe = dict(error)
        context = safe.get("ctx")
        if isinstance(context, dict):
            safe["ctx"] = {
                key: value if value is None or isinstance(value, (str, int, float, bool)) else str(value)
                for key, value in context.items()
            }
        rows.append(safe)
    return rows


def install_observability(app: FastAPI) -> None:
    # Most operator workspaces are JSON-heavy. Compress responses large enough
    # to benefit while leaving small health and mutation payloads untouched.
    # A moderate compression level keeps transfer size down without turning
    # response compression itself into a meaningful CPU/latency cost.
    app.add_middleware(GZipMiddleware, minimum_size=1_000, compresslevel=5)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "").strip()
        request_id = supplied[:128] if supplied else str(uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except DatabasePoolTimeout:
            logger.warning(
                "database_busy request_id=%s method=%s path=%s",
                request_id,
                request.method,
                _safe_log_path(request),
            )
            response = JSONResponse(status_code=503, content={"error": {
                "code": "database_busy", "message": "The app database is busy. Wait a moment before retrying; do not reset your METRC keys.",
                "request_id": request_id,
            }}, headers={"Retry-After": "5"})
        except Exception:
            logger.exception(
                "api_request_failed request_id=%s method=%s path=%s",
                request_id,
                request.method,
                _safe_log_path(request),
            )
            response = JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "An unexpected server error occurred.", "request_id": request_id}})
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
        response.headers["Server-Timing"] = f"app;dur={duration_ms:.2f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers.setdefault("Cache-Control", "no-store")
        log = logger.warning if duration_ms >= SLOW_REQUEST_MS else logger.info
        log(
            "api_request request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
            request_id,
            request.method,
            _safe_log_path(request),
            response.status_code,
            duration_ms,
        )
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        request_id = getattr(request.state, "request_id", str(uuid4()))
        detail = exc.detail
        message = detail if isinstance(detail, str) else "The request could not be completed."
        code = "not_found" if exc.status_code == 404 else "forbidden" if exc.status_code == 403 else "conflict" if exc.status_code == 409 else "request_error"
        return JSONResponse(status_code=exc.status_code, content={"detail": detail, "error": {"code": code, "message": message, "request_id": request_id}}, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", str(uuid4()))
        return JSONResponse(status_code=422, content={"detail": _serializable_validation_errors(exc), "error": {"code": "validation_error", "message": "One or more request fields are invalid.", "request_id": request_id}})
