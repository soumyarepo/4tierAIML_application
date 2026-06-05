"""FastAPI dependency providers for the Auth Service.

Provides:
- get_db: AsyncSession dependency for all route handlers.
- get_current_user: JWT access token validation and User model injection.
- require_role: Dependency factory for role-based access control (RBAC).
"""

import sys
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")

from typing import Annotated, Callable
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

import sys
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")
from shared.auth import decode_token
from shared.config import settings
from shared.exceptions import AuthenticationError

from app.database import get_session_factory
from app.models import User, UserRole

# HTTP Bearer scheme for JWT extraction
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


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Extract and validate the current user from a JWT access token.

    Reads the Bearer token from the Authorization header, decodes it,
    verifies it is an access token, and looks up the corresponding user.

    Args:
        credentials: HTTP Authorization header with Bearer scheme.
        db: Database session.

    Returns:
        The authenticated User model.

    Raises:
        HTTPException 401: If no token is provided, the token is invalid,
            or the user no longer exists.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        payload = decode_token(token)
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type: expected access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing 'sub' claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Look up the user in the database
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is suspended",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_role(allowed_roles: list[UserRole]) -> Callable:
    """Factory that returns a FastAPI dependency enforcing role-based access.

    Use as a route dependency: Depends(require_role([UserRole.ADMIN]))

    Args:
        allowed_roles: List of roles permitted to access the endpoint.

    Returns:
        A FastAPI dependency that validates the user's role.
    """

    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {[r.value for r in allowed_roles]}",
            )
        return current_user

    return role_checker


# Type aliases for convenience
CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]