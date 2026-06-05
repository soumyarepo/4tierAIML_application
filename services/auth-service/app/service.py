"""Business logic for the Auth Service.

Encapsulates all authentication-related operations:
- User registration with password hashing
- Credential verification
- JWT access token creation
- Opaque refresh token generation, validation, and rotation
"""

import sys
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")

import uuid
from datetime import datetime, timedelta, timezone
from typing import Tuple
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
import bcrypt

import sys
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")
from shared.auth import (
    hash_password as shared_hash_password,
    verify_password as shared_verify_password,
    create_access_token as shared_create_access_token,
    create_refresh_token as shared_create_refresh_token,
    decode_token as shared_decode_token,
)
from shared.config import settings
from shared.exceptions import (
    AuthenticationError,
    DuplicateResourceError,
    ValidationError,
)

from app.models import User, RefreshToken, UserRole
from app.schemas import UserCreate, TokenPair


# ---------------------------------------------------------------------------
# Password Helpers
# ---------------------------------------------------------------------------


def _hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ---------------------------------------------------------------------------
# Token Helpers
# ---------------------------------------------------------------------------


def _create_access_token_payload(user: User) -> dict:
    """Build the JWT payload for a user access token."""
    return {
        "sub": user.id,
        "email": user.email,
        "role": user.role.value,
        "type": "access",
    }


def _create_refresh_token_value() -> str:
    """Generate a new opaque refresh token (UUID4)."""
    return str(uuid.uuid4())


def _hash_token(token: str) -> str:
    """Hash an opaque refresh token for secure storage."""
    return bcrypt.hashpw(token.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_token_hash(token: str, hashed: str) -> bool:
    """Verify an opaque refresh token against its stored hash."""
    return bcrypt.checkpw(token.encode("utf-8"), hashed.encode("utf-8"))


# ---------------------------------------------------------------------------
# Service Layer Functions
# ---------------------------------------------------------------------------


async def register_user(db: AsyncSession, user_data: UserCreate) -> Tuple[User, TokenPair]:
    """Register a new customer account.

    Args:
        db: AsyncSession instance.
        user_data: Validated user registration data.

    Returns:
        Tuple of (created User model, TokenPair with access + refresh tokens).

    Raises:
        DuplicateResourceError: If the email is already registered.
    """
    # Check for existing user
    result = await db.execute(select(User).where(User.email == user_data.email))
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise DuplicateResourceError(
            message="A user with this email already exists",
            details={"email": user_data.email},
        )

    # Create user
    user = User(
        email=user_data.email,
        full_name=user_data.full_name,
        password_hash=_hash_password(user_data.password),
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    # Generate tokens
    token_pair = _generate_token_pair(user)

    # Store refresh token hash
    refresh_token_record = RefreshToken(
        user_id=user.id,
        token_hash=_hash_token(token_pair.refresh_token),
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(refresh_token_record)
    await db.flush()

    return user, token_pair


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> Tuple[User, TokenPair]:
    """Authenticate a user with email and password credentials.

    Args:
        db: AsyncSession instance.
        email: User's email address.
        password: Plain-text password.

    Returns:
        Tuple of (authenticated User model, TokenPair with access + refresh tokens).

    Raises:
        AuthenticationError: If credentials are invalid.
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not _verify_password(password, user.password_hash):
        raise AuthenticationError(
            message="Invalid email or password",
            details={"email": email},
        )

    if not user.is_active:
        raise AuthenticationError(
            message="User account is suspended",
            details={"email": email},
        )

    # Generate new token pair (token rotation)
    token_pair = _generate_token_pair(user)

    # Store new refresh token hash
    refresh_token_record = RefreshToken(
        user_id=user.id,
        token_hash=_hash_token(token_pair.refresh_token),
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(refresh_token_record)
    await db.flush()

    return user, token_pair


async def refresh_access_token(
    db: AsyncSession,
    refresh_token: str,
) -> Tuple[User, TokenPair]:
    """Validate a refresh token and issue a new access token (token rotation).

    The provided refresh token is consumed (deleted from DB) after successful
    validation to prevent replay attacks.

    Args:
        db: AsyncSession instance.
        refresh_token: Opaque refresh token value (UUID).

    Returns:
        Tuple of (User model, new TokenPair with fresh access + refresh tokens).

    Raises:
        AuthenticationError: If the refresh token is invalid, expired, or revoked.
    """
    # Find all refresh tokens for the user and check each one
    # We do this because we only store the hash, not the raw token
    # First, find the user by looking through all non-expired tokens
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.expires_at > now)
    )
    candidate_tokens = result.scalars().all()

    user_id: str | None = None
    matched_token_record: RefreshToken | None = None

    for record in candidate_tokens:
        if _verify_token_hash(refresh_token, record.token_hash):
            user_id = record.user_id
            matched_token_record = record
            break

    if matched_token_record is None:
        raise AuthenticationError(
            message="Invalid or expired refresh token",
        )

    # Delete the used refresh token (rotation)
    await db.delete(matched_token_record)

    # Load the user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise AuthenticationError(message="User not found or inactive")

    # Issue new token pair
    token_pair = _generate_token_pair(user)

    # Store new refresh token
    new_refresh_record = RefreshToken(
        user_id=user.id,
        token_hash=_hash_token(token_pair.refresh_token),
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(new_refresh_record)
    await db.flush()

    return user, token_pair


async def revoke_refresh_token(db: AsyncSession, refresh_token: str) -> None:
    """Revoke a refresh token (logout).

    Searches all non-expired tokens for a hash match and deletes it.

    Args:
        db: AsyncSession instance.
        refresh_token: Opaque refresh token to revoke.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.expires_at > now)
    )
    candidate_tokens = result.scalars().all()

    for record in candidate_tokens:
        if _verify_token_hash(refresh_token, record.token_hash):
            await db.delete(record)
            await db.flush()
            return  # Revoke only the first matching token


def _generate_token_pair(user: User) -> TokenPair:
    """Generate an access + refresh token pair for a user."""
    access_payload = _create_access_token_payload(user)
    access_token = shared_create_access_token(access_payload)

    refresh_token = _create_refresh_token_value()

    expires_in_seconds = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=expires_in_seconds,
    )