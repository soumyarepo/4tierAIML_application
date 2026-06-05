"""FastAPI application entry point for the Auth Service.

Provides JWT-based authentication, user registration, login, token refresh,
logout, and admin user management endpoints.
"""

import sys
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src/shared")

from contextlib import asynccontextmanager
from typing import Annotated, AsyncIterator
from fastapi import FastAPI, Depends, Query, status
from fastapi.security import HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Shared library imports
from shared.config import settings
from shared.logging_config import configure_logging, get_logger
from shared.middleware import register_middleware
from shared.exceptions import (
    register_exception_handlers,
    DuplicateResourceError,
    AuthenticationError,
)

# Local imports
from app.database import init_db, close_db, get_session_factory
from app.models import User, UserRole
from app.schemas import (
    UserCreate,
    UserLogin,
    TokenPair,
    RefreshRequest,
    UserOut,
    AdminUserListResponse,
    HealthResponse,
)
from app.dependencies import get_db, get_current_user, require_role
from app import service as auth_service

# Configure structured logging
configure_logging(
    debug=settings.DEBUG,
    service_name="auth-service",
)
logger = get_logger("auth")

# Security scheme for OpenAPI docs
bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Application Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown lifecycle."""
    # Startup
    logger.info("auth_service_starting", port=8001)
    await init_db(echo=settings.DEBUG)
    logger.info("auth_service_started", port=8001)
    yield
    # Shutdown
    await close_db()
    logger.info("auth_service_shutdown")


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Auth Service",
    description="JWT-based authentication and user management for the banking platform.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Register middleware (request ID, timing, structured logging)
register_middleware(app)

# Register shared exception handlers
register_exception_handlers(app)


# ---------------------------------------------------------------------------
# Health & Metrics
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    """Liveness probe for Kubernetes/container orchestration."""
    return HealthResponse(
        status="healthy",
        service="auth-service",
        version="1.0.0",
    )


# ---------------------------------------------------------------------------
# Auth Routes
# ---------------------------------------------------------------------------


@app.post(
    "/api/v1/auth/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    tags=["Auth"],
    summary="Register a new customer account",
)
async def register(
    user_data: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    """Register a new customer and return access + refresh token pair.

    The user is created with the ``customer`` role. Password is hashed
    with bcrypt before storage.
    """
    logger.info("register_attempt", email=user_data.email)
    try:
        user, token_pair = await auth_service.register_user(db, user_data)
        logger.info("user_registered", user_id=user.id, email=user.email)
        return token_pair
    except DuplicateResourceError:
        logger.warning("register_failed_duplicate", email=user_data.email)
        raise


@app.post(
    "/api/v1/auth/login",
    response_model=TokenPair,
    tags=["Auth"],
    summary="Authenticate and receive token pair",
)
async def login(
    credentials: UserLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    """Authenticate with email and password, returning a new token pair.

    Implements token rotation: each login invalidates the previous refresh
    token and issues a fresh pair.
    """
    logger.info("login_attempt", email=credentials.email)
    try:
        user, token_pair = await auth_service.authenticate_user(
            db, credentials.email, credentials.password
        )
        logger.info("login_success", user_id=user.id, email=user.email)
        return token_pair
    except AuthenticationError:
        logger.warning("login_failed", email=credentials.email)
        raise


@app.post(
    "/api/v1/auth/refresh",
    response_model=TokenPair,
    tags=["Auth"],
    summary="Refresh access token",
)
async def refresh_token(
    request: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    """Exchange a valid refresh token for a new access + refresh token pair.

    The provided refresh token is consumed (rotated) to prevent replay attacks.
    """
    logger.info("refresh_attempt")
    try:
        user, token_pair = await auth_service.refresh_access_token(
            db, request.refresh_token
        )
        logger.info("refresh_success", user_id=user.id)
        return token_pair
    except AuthenticationError:
        logger.warning("refresh_failed")
        raise


@app.post(
    "/api/v1/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Auth"],
    summary="Logout and revoke refresh token",
)
async def logout(
    request: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Revoke the provided refresh token (logout).

    The refresh token is permanently invalidated; the user must re-authenticate
    to obtain a new token pair.
    """
    await auth_service.revoke_refresh_token(db, request.refresh_token)
    logger.info("logout_success")
    return None


@app.get(
    "/api/v1/auth/me",
    response_model=UserOut,
    tags=["Auth"],
    summary="Get current authenticated user",
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserOut:
    """Return the currently authenticated user's profile.

    Requires a valid JWT access token in the ``Authorization: Bearer`` header.
    """
    return UserOut.model_validate(current_user)


# ---------------------------------------------------------------------------
# Admin Routes
# ---------------------------------------------------------------------------


@app.get(
    "/api/v1/admin/users",
    response_model=AdminUserListResponse,
    tags=["Admin"],
    summary="List all users (admin only)",
)
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_role([UserRole.ADMIN]))],
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Users per page"),
) -> AdminUserListResponse:
    """Paginated listing of all users (admin only).

    Returns users ordered by ``created_at`` descending (newest first).
    """
    # Count total
    count_result = await db.execute(select(func.count(User.id)))
    total = count_result.scalar_one()

    # Paginated query
    offset = (page - 1) * page_size
    result = await db.execute(
        select(User)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    users = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return AdminUserListResponse(
        users=[UserOut.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=settings.DEBUG,
    )