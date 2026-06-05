"""FastAPI API Gateway - Tier 1 of the banking microservices architecture.

Handles request proxying, JWT validation, rate limiting, and header forwarding
to upstream banking services.
"""

import uuid
import jwt
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
import redis.asyncio as redis
import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.rate_limiter import RateLimiter
from shared.logging_config import configure_logging, get_logger
from shared.metrics import setup_metrics, get_metrics_endpoint

# Configure structured logging
configure_logging(
    debug=settings.DEBUG if hasattr(settings, "DEBUG") else False,
    service_name="gateway-service",
)
logger = get_logger("gateway")

# =============================================================================
# Application State
# =============================================================================

app_state: dict[str, Any] = {
    "redis_client": None,
    "http_client": None,
    "rate_limiter": None,
}


# =============================================================================
# Error Response Models
# =============================================================================


class GatewayErrorResponse(BaseModel):
    """Standardized error response format for gateway errors."""

    detail: str
    code: str
    request_id: str | None = None
    timestamp: str | None = None


def make_error_response(
    detail: str,
    code: str,
    request_id: str | None = None,
    status_code: int = 400,
) -> JSONResponse:
    """Create a standardized gateway error response."""
    return JSONResponse(
        status_code=status_code,
        content=GatewayErrorResponse(
            detail=detail,
            code=code,
            request_id=request_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ).model_dump(exclude_none=True),
    )


# =============================================================================
# JWT Validation
# =============================================================================


class JWTClaims(BaseModel):
    """Validated JWT token claims."""

    user_id: str
    email: str
    roles: list[str]


def extract_and_validate_jwt(request: Request) -> JWTClaims | JSONResponse:
    """Extract JWT from Authorization header and validate signature and expiry.

    Args:
        request: Incoming FastAPI request.

    Returns:
        JWTClaims if valid, or JSONResponse with error status if invalid.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        request_id = getattr(request.state, "request_id", None)
        return make_error_response(
            detail="Missing Authorization header",
            code="MISSING_AUTH_HEADER",
            request_id=request_id,
            status_code=401,
        )

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        request_id = getattr(request.state, "request_id", None)
        return make_error_response(
            detail="Invalid Authorization header format. Expected: Bearer <token>",
            code="INVALID_AUTH_FORMAT",
            request_id=request_id,
            status_code=401,
        )

    token = parts[1]

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        request_id = getattr(request.state, "request_id", None)
        return make_error_response(
            detail="JWT token has expired",
            code="TOKEN_EXPIRED",
            request_id=request_id,
            status_code=401,
        )
    except jwt.InvalidTokenError as e:
        request_id = getattr(request.state, "request_id", None)
        return make_error_response(
            detail=f"Invalid JWT token: {str(e)}",
            code="INVALID_TOKEN",
            request_id=request_id,
            status_code=401,
        )

    # Extract required claims
    user_id = payload.get("sub")
    email = payload.get("email", "")
    roles = payload.get("roles", [])

    if not user_id:
        request_id = getattr(request.state, "request_id", None)
        return make_error_response(
            detail="JWT missing required 'sub' claim",
            code="INVALID_TOKEN_CLAIMS",
            request_id=request_id,
            status_code=401,
        )

    return JWTClaims(user_id=str(user_id), email=str(email), roles=roles)


# =============================================================================
# Rate Limiting
# =============================================================================


async def check_rate_limit(request: Request) -> JSONResponse | None:
    """Check rate limit for client IP. Returns error response if exceeded.

    Args:
        request: Incoming FastAPI request.

    Returns:
        None if allowed, or JSONResponse with 429 status if rate limited.
    """
    if app_state["rate_limiter"] is None:
        return None

    client_ip = request.client.host if request.client else "unknown"
    allowed, remaining, reset_in = await app_state["rate_limiter"].is_allowed(client_ip)

    if not allowed:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        return JSONResponse(
            status_code=429,
            content=GatewayErrorResponse(
                detail=f"Rate limit exceeded. Retry after {reset_in} seconds.",
                code="RATE_LIMIT_EXCEEDED",
                request_id=request_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ).model_dump(exclude_none=True),
            headers={
                "X-Request-ID": request_id,
                "Retry-After": str(reset_in),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Limit": str(settings.RATE_LIMIT_REQUESTS),
                "X-RateLimit-Reset": str(reset_in),
            },
        )

    return None


# =============================================================================
# Proxy Logic
# =============================================================================


def get_upstream_url(service_name: str) -> str | None:
    """Get the upstream service URL from settings.

    Args:
        service_name: Name of the service (auth, accounts, transactions, ai, notifications).

    Returns:
        Base URL string for the upstream service, or None if not configured.
    """
    url_map = {
        "auth": settings.AUTH_SERVICE_URL,
        "accounts": settings.ACCOUNT_SERVICE_URL,
        "transactions": settings.TRANSACTION_SERVICE_URL,
        "ai": settings.AI_SERVICE_URL,
        "notifications": settings.NOTIFICATION_SERVICE_URL,
    }
    return url_map.get(service_name)


async def proxy_request(
    service_name: str,
    path: str,
    request: Request,
    method: str,
) -> Response:
    """Proxy an incoming request to an upstream service.

    Validates JWT, forwards user headers, and returns the upstream response
    with status code and body preserved.

    Args:
        service_name: Target service name for logging.
        path: Path portion after the service prefix.
        request: Incoming FastAPI request.
        method: HTTP method to use for upstream request.

    Returns:
        Response from the upstream service with original status code.
    """
    upstream_base = get_upstream_url(service_name)
    if not upstream_base:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        return make_error_response(
            detail=f"Service '{service_name}' not configured",
            code="SERVICE_NOT_FOUND",
            request_id=request_id,
            status_code=503,
        )

    # Validate JWT and extract claims
    claims_result = extract_and_validate_jwt(request)
    if isinstance(claims_result, JSONResponse):
        return claims_result

    claims = claims_result
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    # Build upstream URL
    upstream_url = f"{upstream_base}/{path}"
    if request.url.query:
        upstream_url = f"{upstream_url}?{request.url.query}"

    # Prepare forwarded headers
    headers = {
        "X-User-ID": claims.user_id,
        "X-User-Email": claims.email,
        "X-User-Roles": ",".join(claims.roles),
        "X-Request-ID": request_id,
        "X-Forwarded-For": request.client.host if request.client else "unknown",
        "X-Forwarded-Proto": request.url.scheme,
        "X-Forwarded-Host": request.url.hostname or "gateway",
    }

    # Read request body for non-GET requests
    body = None
    if method not in ("GET", "HEAD", "OPTIONS"):
        body = await request.body()

    # Make upstream request
    try:
        upstream_response = await app_state["http_client"].request(
            method=method,
            url=upstream_url,
            headers=headers,
            content=body,
            timeout=settings.UPSTREAM_TIMEOUT_SECONDS,
        )
        # Return exact status code and body from upstream
        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            headers=dict(upstream_response.headers),
        )
    except httpx.ConnectError as e:
        logger.error(
            "upstream_connection_error",
            service=service_name,
            url=upstream_url,
            error=str(e),
            request_id=request_id,
        )
        return make_error_response(
            detail=f"Failed to connect to {service_name} service",
            code="UPSTREAM_UNAVAILABLE",
            request_id=request_id,
            status_code=503,
        )
    except httpx.TimeoutException as e:
        logger.error(
            "upstream_timeout_error",
            service=service_name,
            url=upstream_url,
            error=str(e),
            request_id=request_id,
        )
        return make_error_response(
            detail=f"Timeout connecting to {service_name} service",
            code="UPSTREAM_TIMEOUT",
            request_id=request_id,
            status_code=504,
        )
    except httpx.HTTPError as e:
        logger.error(
            "upstream_http_error",
            service=service_name,
            url=upstream_url,
            error=str(e),
            request_id=request_id,
        )
        return make_error_response(
            detail=f"Error communicating with {service_name} service",
            code="UPSTREAM_ERROR",
            request_id=request_id,
            status_code=502,
        )


# =============================================================================
# Health & Readiness
# =============================================================================


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Liveness probe - returns 200 if the gateway process is running."""
    return {"status": "ok", "service": "gateway"}


@app.get("/ready", tags=["health"])
async def readiness_check() -> dict[str, Any]:
    """Readiness probe - checks Redis connectivity."""
    if app_state["redis_client"] is None:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "Redis client not initialized"},
        )

    try:
        await app_state["redis_client"].ping()
        return {"status": "ready", "redis": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": f"Redis error: {str(e)}"},
        )


# =============================================================================
# Proxy Routes
# =============================================================================


@app.api_route("/auth/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], tags=["proxy"])
async def proxy_auth(path: str, request: Request) -> Response:
    """Proxy requests to the Auth service."""
    rate_limited = await check_rate_limit(request)
    if rate_limited:
        return rate_limited
    return await proxy_request("auth", path, request, request.method)


@app.api_route("/accounts/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], tags=["proxy"])
async def proxy_accounts(path: str, request: Request) -> Response:
    """Proxy requests to the Account service."""
    rate_limited = await check_rate_limit(request)
    if rate_limited:
        return rate_limited
    return await proxy_request("accounts", path, request, request.method)


@app.api_route("/transactions/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], tags=["proxy"])
async def proxy_transactions(path: str, request: Request) -> Response:
    """Proxy requests to the Transaction service."""
    rate_limited = await check_rate_limit(request)
    if rate_limited:
        return rate_limited
    return await proxy_request("transactions", path, request, request.method)


@app.api_route("/ai/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], tags=["proxy"])
async def proxy_ai(path: str, request: Request) -> Response:
    """Proxy requests to the AI/Fraud service."""
    rate_limited = await check_rate_limit(request)
    if rate_limited:
        return rate_limited
    return await proxy_request("ai", path, request, request.method)


@app.api_route("/notifications/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], tags=["proxy"])
async def proxy_notifications(path: str, request: Request) -> Response:
    """Proxy requests to the Notification service."""
    rate_limited = await check_rate_limit(request)
    if rate_limited:
        return rate_limited
    return await proxy_request("notifications", path, request, request.method)


# =============================================================================
# Application Lifecycle
# =============================================================================


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize connections on application startup."""
    logger.info("gateway_starting")

    # Initialize Redis client
    app_state["redis_client"] = redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )

    # Initialize rate limiter
    app_state["rate_limiter"] = RateLimiter(
        redis_client=app_state["redis_client"],
    )

    # Initialize httpx async client with connection pooling
    app_state["http_client"] = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.UPSTREAM_TIMEOUT_SECONDS),
        limits=httpx.Limits(
            max_keepalive_connections=20,
            max_connections=100,
        ),
        follow_redirects=True,
    )

    logger.info("gateway_started", service="gateway")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Clean up connections on application shutdown."""
    logger.info("gateway_shutting_down")

    if app_state["http_client"]:
        await app_state["http_client"].aclose()

    if app_state["rate_limiter"]:
        await app_state["rate_limiter"].close()

    if app_state["redis_client"]:
        await app_state["redis_client"].aclose()

    logger.info("gateway_stopped")


# =============================================================================
# App Creation
# =============================================================================


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(
        title="Banking API Gateway",
        description="Tier 1 API Gateway for the four-tier banking microservices architecture",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Prometheus metrics
    setup_metrics(app)

    # Include all routes from this module
    app.include_router(app.router)

    return app


app = create_app()