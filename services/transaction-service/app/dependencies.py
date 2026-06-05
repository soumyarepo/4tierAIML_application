"""FastAPI dependency providers for the Transaction Service.

Provides:
- get_db: AsyncSession dependency for all route handlers.
- get_current_user_from_headers: Extract user ID from gateway headers.
- get_kafka_producer: Singleton Kafka producer dependency.
"""

import sys
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")

from typing import Annotated, Optional
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
from aiokafka import AIOKafkaProducer

import sys
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")
from shared.kafka_client import KafkaProducerWrapper
from shared.config import settings

from app.database import get_session_factory

# Global producer instance
_kafka_producer: Optional[KafkaProducerWrapper] = None


async def get_db() -> AsyncSession:
    """FastAPI dependency that yields an AsyncSession with auto-commit/rollback.

    Yields:
        AsyncSession instance scoped to the current request.
    """
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_current_user_from_headers(
    request: Request,
) -> str:
    """Extract and validate the current user ID from gateway headers.

    The gateway forwards X-User-ID header after JWT validation.

    Args:
        request: FastAPI Request object.

    Returns:
        User ID string from the X-User-ID header.

    Raises:
        HTTPException 401: If X-User-ID header is missing or invalid.
    """
    user_id = request.headers.get("X-User-ID")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-ID header from gateway",
        )

    try:
        uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-User-ID format (must be UUID)",
        )

    return user_id


def get_kafka_producer() -> KafkaProducerWrapper:
    """Return the singleton Kafka producer instance.

    Returns:
        KafkaProducerWrapper instance.

    Raises:
        RuntimeError: If producer not initialized (startup not complete).
    """
    global _kafka_producer
    if _kafka_producer is None:
        raise RuntimeError("Kafka producer not initialized. Call startup handler first.")
    return _kafka_producer


def set_kafka_producer(producer: KafkaProducerWrapper) -> None:
    """Set the global Kafka producer instance (called at startup)."""
    global _kafka_producer
    _kafka_producer = producer


async def get_redis_client():
    """Get a Redis client for idempotency key checking.

    Returns:
        aioredis Redis client instance.
    """
    import redis.asyncio as aioredis
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        yield redis_client
    finally:
        await redis_client.aclose()


async def get_mongo_client():
    """Get a MongoDB client for audit logging.

    Returns:
        motor AsyncIOMotorClient instance.
    """
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo_client = AsyncIOMotorClient(settings.MONGO_URL)
    try:
        yield mongo_client
    finally:
        mongo_client.close()


# Type aliases
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUserId = Annotated[str, Depends(get_current_user_from_headers)]
KafkaProducer = Annotated[KafkaProducerWrapper, Depends(get_kafka_producer)]
RedisClient = Annotated[aioredis.Redis, Depends(get_redis_client)]
MongoClient = Annotated[AsyncIOMotorClient, Depends(get_mongo_client)]