from __future__ import annotations

import logging
import time
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("buyer_dash.api")


def install_observability(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "").strip()
        request_id = supplied[:128] if supplied else str(uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("api_request_failed request_id=%s method=%s path=%s", request_id, request.method, request.url.path)
            response = JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "An unexpected server error occurred.", "request_id": request_id}})
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
        logger.info("api_request request_id=%s method=%s path=%s status=%s duration_ms=%.2f", request_id, request.method, request.url.path, response.status_code, duration_ms)
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
        return JSONResponse(status_code=422, content={"detail": exc.errors(), "error": {"code": "validation_error", "message": "One or more request fields are invalid.", "request_id": request_id}})
