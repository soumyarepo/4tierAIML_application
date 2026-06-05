"""Database configuration for the Auth Service.

Creates the async SQLAlchemy engine and session factory for the bank_auth
database, overriding the shared settings with service-specific configuration.
"""

import sys
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from shared.database import Base

from shared.config import settings

# Build the bank_auth database URL explicitly
DATABASE_URL = settings.get_bank_auth_db_url()


def create_engine(echo: bool = False) -> AsyncEngine:
    """Create an async SQLAlchemy engine for the bank_auth database.

    Args:
        echo: If True, log all SQL statements (useful for debugging).

    Returns:
        Configured AsyncEngine instance.
    """
    return create_async_engine(
        DATABASE_URL,
        echo=echo,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


def create_async_engine(url: str, echo: bool = False) -> AsyncEngine:
    """Proxy to shared create_async_engine for bank_auth URL."""
    from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine
    return _create_async_engine(
        url,
        echo=echo,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to the given engine.

    Args:
        engine: AsyncEngine instance.

    Returns:
        Configured async_sessionmaker for AsyncSession.
    """
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# Module-level engine and session factory (set during startup)
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the module-level async engine, raising if not initialized."""
    if _engine is None:
        raise RuntimeError("Auth service engine not initialized. Call init_db() first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the module-level session factory, raising if not initialized."""
    if _session_factory is None:
        raise RuntimeError(
            "Auth service session factory not initialized. Call init_db() first."
        )
    return _session_factory


async def init_db(echo: bool = False) -> None:
    """Initialize the database engine, session factory, and create all tables.

    Args:
        echo: If True, log SQL statements.
    """
    global _engine, _session_factory
    _engine = create_engine(echo=echo)
    _session_factory = create_session_factory(_engine)

    # Import models to ensure they are registered with Base
    from app import models  # noqa: F401

    # Create all tables in the bank_auth database
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close the database engine and release all connections."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None