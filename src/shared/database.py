"""SQLAlchemy 2.0 async database setup.

Provides async engine, session factory, and declarative base for all services.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String
from typing import AsyncGenerator

import uuid


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy ORM models.

    All service-specific models should inherit from this class.
    """

    pass


class UUIDPrimaryKey:
    """Mixin that provides a UUID primary key column."""

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


def create_async_engine(url: str, echo: bool = False) -> AsyncEngine:
    """Create an async SQLAlchemy engine.

    Args:
        url: Async database URL (e.g. postgresql+asyncpg://...).
        echo: If True, log all SQL statements.

    Returns:
        Configured AsyncEngine instance.
    """
    return create_async_engine(
        url,
        echo=echo,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


def create_async_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to the given engine.

    Args:
        engine: AsyncEngine instance to bind sessions to.

    Returns:
        Configured async_sessionmaker.
    """
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session with auto-commit/rollback.

    Usage in FastAPI:
        @app.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db_session)):
            ...

    Args:
        session_factory: async_sessionmaker bound to the service's engine.

    Yields:
        AsyncSession instance. Commits on success, rolls back on exception.
    """
    session = session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()