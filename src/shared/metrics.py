"""Prometheus metrics helpers for FastAPI services.

Provides request counters, latency histograms, and route decoration utilities.
"""

from prometheus_client import Counter, Histogram, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
from starlette.requests import Request
from starlette.responses import Response
from fastapi import FastAPI
from typing import Callable
import time

# Use the default registry — services can opt into using a custom one if needed
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Business-specific metrics
TRANSACTION_COUNT = Counter(
    "banking_transactions_total",
    "Total banking transactions processed",
    ["type", "status"],
)

FRAUD_SCORE_HISTOGRAM = Histogram(
    "fraud_score_distribution",
    "Distribution of fraud risk scores (0-100)",
    buckets=(10, 20, 30, 40, 50, 60, 70, 80, 90, 100),
)

ACCOUNT_BALANCE_GAUGE = Histogram(
    "account_balance_distribution",
    "Distribution of account balances",
    ["currency"],
    buckets=(100, 500, 1000, 5000, 10000, 50000, 100000),
)


def increment_request_count(method: str, endpoint: str, status_code: int) -> None:
    """Increment the HTTP request counter.

    Args:
        method: HTTP method (GET, POST, etc.).
        endpoint: Sanitized endpoint path (e.g. /api/v1/users).
        status_code: HTTP status code of the response.
    """
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=str(status_code)).inc()


def observe_request_latency(method: str, endpoint: str, latency_seconds: float) -> None:
    """Record request latency in the histogram.

    Args:
        method: HTTP method.
        endpoint: Sanitized endpoint path.
        latency_seconds: Elapsed time in seconds.
    """
    REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(latency_seconds)


def get_metrics_endpoint() -> Response:
    """Return a Prometheus-compatible metrics response."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


class MetricsMiddleware:
    """WSGI/ASGI middleware that records request metrics for Prometheus."""

    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")

        # Replace dynamic path segments for stable label values
        # E.g., /accounts/abc-123 → /accounts/{id}
        endpoint = _sanitize_endpoint(path)
        start_time = time.perf_counter()

        status_code = 500  # default

        async def send_wrapper(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            latency = time.perf_counter() - start_time
            increment_request_count(method, endpoint, status_code)
            observe_request_latency(method, endpoint, latency)


def _sanitize_endpoint(path: str) -> str:
    """Replace UUIDs and numeric IDs in path segments with placeholders."""
    import re

    # Replace UUIDs
    path = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "{id}",
        path,
        flags=re.IGNORECASE,
    )
    # Replace numeric IDs
    path = re.sub(r"/\d+(/|$)", r"/{id}\1", path)
    return path


def decorate_fastapi_route(app: FastAPI, path: str, methods: list[str] | None = None) -> None:
    """Register a /metrics endpoint on the FastAPI app if not already present.

    Args:
        app: FastAPI application instance.
        path: Path for the metrics endpoint (default: /metrics).
        methods: HTTP methods for the endpoint.
    """
    if not hasattr(app, "_metrics_endpoint_registered"):
        app.add_route("/metrics", get_metrics_endpoint, methods=["GET"])
        app._metrics_endpoint_registered = True  # type: ignore[attr-defined]


def setup_metrics(app: FastAPI) -> None:
    """Setup Prometheus metrics integration on a FastAPI app.

    Adds the /metrics endpoint and attaches the MetricsMiddleware.

    Args:
        app: FastAPI application instance.
    """
    decorate_fastapi_route(app, "/metrics")
    app.add_middleware(MetricsMiddleware)