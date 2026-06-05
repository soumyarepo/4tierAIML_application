"""FastAPI middleware for request lifecycle management.

Provides:
- Request ID generation (UUID4) per request
- Request timing and X-Process-Time header
- Structured JSON logging per request
"""

import time
import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable

logger = structlog.get_logger()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware that generates a unique request ID and sets it on response headers."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class TimingMiddleware(BaseHTTPMiddleware):
    """Middleware that measures request processing time and sets X-Process-Time header."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        response = await call_next(request)
        process_time = time.perf_counter() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.6f}"
        return response


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs each request with structured context using structlog."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = getattr(request.state, "request_id", "unknown")
        log = logger.bind(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_host=request.client.host if request.client else None,
        )

        try:
            response = await call_next(request)
            log.info(
                "request_completed",
                status_code=response.status_code,
            )
            return response
        except Exception as e:
            log.error(
                "request_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise


def register_middleware(app) -> None:
    """Register all middleware classes on a FastAPI application.

    Middleware is registered in reverse order (last applied = first in chain).
    The actual Starlette order is: Logging -> Timing -> RequestID.

    Args:
        app: FastAPI application instance.
    """
    app.add_middleware(StructuredLoggingMiddleware)
    app.add_middleware(TimingMiddleware)
    app.add_middleware(RequestIDMiddleware)