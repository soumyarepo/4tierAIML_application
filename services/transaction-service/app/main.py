"""FastAPI application entry point for the Transaction Service.

Provides transaction operations: transfer, deposit, withdrawal,
and transaction history with double-entry bookkeeping.
"""

import sys
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src/shared")

from contextlib import asynccontextmanager
from typing import Annotated, AsyncIterator, Optional
from fastapi import FastAPI, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as aioredis

# Shared library imports
from shared.config import settings
from shared.logging_config import configure_logging, get_logger
from shared.middleware import register_middleware
from shared.exceptions import register_exception_handlers
from shared.kafka_client import KafkaProducerWrapper

# Local imports
from app.database import init_db, close_db, get_session_factory
from app.models import Transaction
from app.schemas import (
    TransferRequest,
    DepositRequest,
    WithdrawalRequest,
    TransactionOut,
    TransactionEntryOut,
    TransactionListResponse,
    HealthResponse,
)
from app.dependencies import (
    get_db,
    get_current_user_from_headers,
    set_kafka_producer,
    get_kafka_producer,
)
from app import service as transaction_service

# Configure structured logging
configure_logging(
    debug=settings.DEBUG,
    service_name="transaction-service",
)
logger = get_logger("transaction")

# Global instances
_kafka_producer: Optional[KafkaProducerWrapper] = None
_redis_client: Optional[aioredis.Redis] = None
_mongo_client: Optional[AsyncIOMotorClient] = None


# ---------------------------------------------------------------------------
# Application Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown lifecycle."""
    global _kafka_producer, _redis_client, _mongo_client

    # Startup
    logger.info("transaction_service_starting", port=8003)
    await init_db(echo=settings.DEBUG)

    # Initialize Kafka producer
    global _kafka_producer
    _kafka_producer = KafkaProducerWrapper(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        client_id="transaction-service",
        acks="all",
    )
    try:
        await _kafka_producer.start()
        set_kafka_producer(_kafka_producer)
        logger.info("kafka_producer_started")
    except Exception as e:
        logger.warning("kafka_producer_start_failed", error=str(e))

    # Initialize Redis client
    global _redis_client
    _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    logger.info("redis_client_initialized")

    # Initialize MongoDB client
    global _mongo_client
    _mongo_client = AsyncIOMotorClient(settings.MONGO_URL)
    logger.info("mongo_client_initialized")

    logger.info("transaction_service_started", port=8003)
    yield

    # Shutdown
    if _kafka_producer:
        await _kafka_producer.stop()
        logger.info("kafka_producer_stopped")

    if _redis_client:
        await _redis_client.aclose()
        logger.info("redis_client_closed")

    if _mongo_client:
        _mongo_client.close()
        logger.info("mongo_client_closed")

    await close_db()
    logger.info("transaction_service_shutdown")


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Transaction Service",
    description="Transaction processing with double-entry bookkeeping for the banking platform.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Register middleware
register_middleware(app)

# Register exception handlers
register_exception_handlers(app)


# ---------------------------------------------------------------------------
# Dependency Providers for Request Scope
# ---------------------------------------------------------------------------


async def get_request_redis():
    """FastAPI dependency for Redis client (request-scoped)."""
    return _redis_client


async def get_request_mongo():
    """FastAPI dependency for MongoDB client (request-scoped)."""
    return _mongo_client


# ---------------------------------------------------------------------------
# Health & Metrics
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    """Liveness probe for Kubernetes/container orchestration."""
    return HealthResponse(
        status="healthy",
        service="transaction-service",
        version="1.0.0",
    )


# ---------------------------------------------------------------------------
# Transaction Routes
# ---------------------------------------------------------------------------


@app.post(
    "/api/v1/transactions/transfer",
    response_model=TransactionOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Transactions"],
    summary="Transfer funds between accounts",
)
async def create_transfer(
    data: TransferRequest,
    db: Annotated["AsyncSession", Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_from_headers)],
    redis: Annotated[aioredis.Redis, Depends(get_request_redis)],
    kafka: Annotated[KafkaProducerWrapper, Depends(get_kafka_producer)],
    mongo: Annotated[AsyncIOMotorClient, Depends(get_request_mongo)],
) -> TransactionOut:
    """Transfer funds from one account to another.

    Implements:
    - Idempotency via Redis
    - Double-entry bookkeeping (DEBIT source, CREDIT destination)
    - Row-level locking to prevent race conditions
    - Kafka event publishing on completion
    - MongoDB audit logging
    """
    logger.info(
        "transfer_request",
        from_account=data.from_account_id,
        to_account=data.to_account_id,
        amount=str(data.amount),
        user_id=user_id,
    )

    transaction = await transaction_service.create_transfer(
        db=db,
        redis_client=redis,
        kafka_producer=kafka,
        mongo_client=mongo,
        user_id=user_id,
        data=data,
    )

    # Load entries for response
    await db.refresh(transaction, ["entries"])

    logger.info(
        "transfer_completed",
        transaction_id=transaction.id,
        reference=transaction.reference_number,
    )

    return TransactionOut.model_validate(transaction)


@app.post(
    "/api/v1/transactions/deposit",
    response_model=TransactionOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Transactions"],
    summary="Deposit funds to an account",
)
async def create_deposit(
    data: DepositRequest,
    db: Annotated["AsyncSession", Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_from_headers)],
    redis: Annotated[aioredis.Redis, Depends(get_request_redis)],
    kafka: Annotated[KafkaProducerWrapper, Depends(get_kafka_producer)],
    mongo: Annotated[AsyncIOMotorClient, Depends(get_request_mongo)],
) -> TransactionOut:
    """Deposit funds to an account.

    Creates a CREDIT entry for the destination account.
    """
    logger.info(
        "deposit_request",
        to_account=data.to_account_id,
        amount=str(data.amount),
        user_id=user_id,
    )

    transaction = await transaction_service.create_deposit(
        db=db,
        redis_client=redis,
        kafka_producer=kafka,
        mongo_client=mongo,
        user_id=user_id,
        data=data,
    )

    await db.refresh(transaction, ["entries"])

    logger.info(
        "deposit_completed",
        transaction_id=transaction.id,
        reference=transaction.reference_number,
    )

    return TransactionOut.model_validate(transaction)


@app.post(
    "/api/v1/transactions/withdraw",
    response_model=TransactionOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Transactions"],
    summary="Withdraw funds from an account",
)
async def create_withdrawal(
    data: WithdrawalRequest,
    db: Annotated["AsyncSession", Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_from_headers)],
    redis: Annotated[aioredis.Redis, Depends(get_request_redis)],
    kafka: Annotated[KafkaProducerWrapper, Depends(get_kafka_producer)],
    mongo: Annotated[AsyncIOMotorClient, Depends(get_request_mongo)],
) -> TransactionOut:
    """Withdraw funds from an account.

    Creates a DEBIT entry for the source account.
    """
    logger.info(
        "withdrawal_request",
        from_account=data.from_account_id,
        amount=str(data.amount),
        user_id=user_id,
    )

    transaction = await transaction_service.create_withdrawal(
        db=db,
        redis_client=redis,
        kafka_producer=kafka,
        mongo_client=mongo,
        user_id=user_id,
        data=data,
    )

    await db.refresh(transaction, ["entries"])

    logger.info(
        "withdrawal_completed",
        transaction_id=transaction.id,
        reference=transaction.reference_number,
    )

    return TransactionOut.model_validate(transaction)


@app.get(
    "/api/v1/transactions",
    response_model=TransactionListResponse,
    tags=["Transactions"],
    summary="Get transaction history",
)
async def get_transactions(
    db: Annotated["AsyncSession", Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_from_headers)],
    account_id: Optional[str] = Query(
        None,
        description="Filter by account ID",
    ),
    limit: int = Query(50, ge=1, le=100, description="Number of transactions"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> TransactionListResponse:
    """Get paginated transaction history for the authenticated user.

    Returns transactions ordered by creation date (newest first).
    Optionally filter by specific account ID.
    """
    logger.info(
        "get_transactions",
        user_id=user_id,
        account_id=account_id,
        limit=limit,
        offset=offset,
    )

    transactions, total = await transaction_service.get_transaction_history(
        db=db,
        user_id=user_id,
        account_id=account_id,
        limit=limit,
        offset=offset,
    )

    return TransactionListResponse(
        transactions=[TransactionOut.model_validate(t) for t in transactions],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get(
    "/api/v1/transactions/{transaction_id}",
    response_model=TransactionOut,
    tags=["Transactions"],
    summary="Get a specific transaction",
)
async def get_transaction(
    transaction_id: str,
    db: Annotated["AsyncSession", Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_from_headers)],
) -> TransactionOut:
    """Retrieve a specific transaction by ID.

    Verifies that the transaction involves an account owned by the user.
    """
    logger.info(
        "get_transaction",
        transaction_id=transaction_id,
        user_id=user_id,
    )

    transaction = await transaction_service.get_transaction(
        db=db,
        transaction_id=transaction_id,
        user_id=user_id,
    )

    await db.refresh(transaction, ["entries"])

    return TransactionOut.model_validate(transaction)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8003,
        reload=settings.DEBUG,
    )