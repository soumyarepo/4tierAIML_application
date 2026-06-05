"""FastAPI application entry point for the Account Service.

Provides account CRUD operations: create, list, get, update, and close.
"""

import sys
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src/shared")

from contextlib import asynccontextmanager
from typing import Annotated, AsyncIterator
from fastapi import FastAPI, Depends, status

# Shared library imports
from shared.config import settings
from shared.logging_config import configure_logging, get_logger
from shared.middleware import register_middleware
from shared.exceptions import (
    register_exception_handlers,
    ValidationError,
)

# Local imports
from app.database import init_db, close_db, get_session_factory
from app.models import Account
from app.schemas import (
    AccountCreate,
    AccountOut,
    AccountUpdate,
    AccountListResponse,
    HealthResponse,
)
from app.dependencies import get_db, get_current_user_from_headers
from app import service as account_service

# Configure structured logging
configure_logging(
    debug=settings.DEBUG,
    service_name="account-service",
)
logger = get_logger("account")

# ---------------------------------------------------------------------------
# Application Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown lifecycle."""
    # Startup
    logger.info("account_service_starting", port=8002)
    await init_db(echo=settings.DEBUG)
    logger.info("account_service_started", port=8002)
    yield
    # Shutdown
    await close_db()
    logger.info("account_service_shutdown")


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Account Service",
    description="Bank account management for the banking platform.",
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
        service="account-service",
        version="1.0.0",
    )


# ---------------------------------------------------------------------------
# Account Routes
# ---------------------------------------------------------------------------


@app.post(
    "/api/v1/accounts",
    response_model=AccountOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Accounts"],
    summary="Create a new account",
)
async def create_account(
    data: AccountCreate,
    db: Annotated["AsyncSession", Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_from_headers)],
) -> AccountOut:
    """Create a new bank account for the authenticated user.

    The account is created with zero balance. Account type can be
    CHECKING, SAVINGS, or LOAN. A unique 10-digit account number is
    generated automatically.
    """
    logger.info("create_account_attempt", user_id=user_id, account_type=data.account_type)
    account = await account_service.create_account(db, user_id, data)
    logger.info("account_created", account_id=account.id, user_id=user_id)
    return AccountOut.model_validate(account)


@app.get(
    "/api/v1/accounts",
    response_model=AccountListResponse,
    tags=["Accounts"],
    summary="List my accounts",
)
async def list_accounts(
    db: Annotated["AsyncSession", Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_from_headers)],
) -> AccountListResponse:
    """List all accounts owned by the authenticated user.

    Returns accounts ordered by creation date (newest first).
    """
    logger.info("list_accounts", user_id=user_id)
    accounts = await account_service.list_accounts(db, user_id)
    return AccountListResponse(
        accounts=[AccountOut.model_validate(a) for a in accounts],
        total=len(accounts),
    )


@app.get(
    "/api/v1/accounts/{account_id}",
    response_model=AccountOut,
    tags=["Accounts"],
    summary="Get an account",
)
async def get_account(
    account_id: str,
    db: Annotated["AsyncSession", Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_from_headers)],
) -> AccountOut:
    """Retrieve a specific account by ID.

    Verifies that the account belongs to the authenticated user.
    """
    logger.info("get_account", account_id=account_id, user_id=user_id)
    account = await account_service.get_account(db, account_id, user_id)
    return AccountOut.model_validate(account)


@app.patch(
    "/api/v1/accounts/{account_id}",
    response_model=AccountOut,
    tags=["Accounts"],
    summary="Update an account",
)
async def update_account(
    account_id: str,
    data: AccountUpdate,
    db: Annotated["AsyncSession", Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_from_headers)],
) -> AccountOut:
    """Update an account (e.g., freeze).

    Only the status can be updated. Cannot modify a frozen account's status
    except to unfreeze it. Cannot close an account with non-zero balance.
    """
    logger.info("update_account", account_id=account_id, user_id=user_id, data=data)
    account = await account_service.update_account(db, account_id, user_id, data)
    logger.info("account_updated", account_id=account_id)
    return AccountOut.model_validate(account)


@app.delete(
    "/api/v1/accounts/{account_id}",
    response_model=AccountOut,
    status_code=status.HTTP_200_OK,
    tags=["Accounts"],
    summary="Close an account",
)
async def close_account(
    account_id: str,
    db: Annotated["AsyncSession", Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_from_headers)],
) -> AccountOut:
    """Close an account.

    The account must have a zero balance to be closed.
    This sets the account status to CLOSED.
    """
    logger.info("close_account", account_id=account_id, user_id=user_id)
    try:
        account = await account_service.close_account(db, account_id, user_id)
        logger.info("account_closed", account_id=account_id)
        return AccountOut.model_validate(account)
    except ValidationError:
        logger.warning("close_account_failed", account_id=account_id, reason="non_zero_balance")
        raise


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8002,
        reload=settings.DEBUG,
    )