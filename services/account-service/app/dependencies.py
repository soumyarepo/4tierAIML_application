"""FastAPI dependency providers for the Account Service.

Provides:
- get_db: AsyncSession dependency for all route handlers.
- get_current_user_from_headers: Extract user ID from gateway headers.
"""

import sys
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")

from typing import Annotated
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

import sys
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")
from shared.exceptions import AuthenticationError

from app.database import get_session_factory

# HTTP Bearer scheme for JWT extraction (optional - some endpoints may not need auth)
bearer_scheme = HTTPBearer(auto_error=False)


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
    This dependency verifies the header exists and converts to UUID.

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

    # Validate UUID format
    try:
        uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-User-ID format (must be UUID)",
        )

    return user_id


# Type aliases for convenience
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUserId = Annotated[str, Depends(get_current_user_from_headers)]