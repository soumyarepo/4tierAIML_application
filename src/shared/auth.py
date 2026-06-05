"""JWT token creation/validation and password hashing utilities.

Provides bcrypt password hashing and HS256 JWT access/refresh token helpers.
"""

import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from typing import Any

from shared.config import settings


def hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt with automatic salt generation.

    Args:
        password: Plain-text password to hash.

    Returns:
        bcrypt hash string suitable for storage.
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plain-text password against a stored bcrypt hash.

    Args:
        password: Plain-text password to verify.
        hashed: Stored bcrypt hash.

    Returns:
        True if password matches, False otherwise.
    """
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(
    data: dict[str, Any],
    secret: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token.

    Args:
        data: Payload data to encode (e.g. {"sub": user_id, "roles": [...]}).
        secret: Secret key override (defaults to settings.JWT_SECRET).
        expires_delta: Token lifetime (defaults to JWT_ACCESS_TOKEN_EXPIRE_MINUTES).

    Returns:
        Encoded JWT string.
    """
    secret = secret or settings.JWT_SECRET
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({
        "exp": expire,
        "type": "access",
        "iat": datetime.now(timezone.utc),
    })
    return jwt.encode(to_encode, secret, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(
    data: dict[str, Any],
    secret: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT refresh token with longer lifetime than access tokens.

    Args:
        data: Payload data to encode.
        secret: Secret key override (defaults to settings.JWT_SECRET).
        expires_delta: Token lifetime (defaults to JWT_REFRESH_TOKEN_EXPIRE_DAYS).

    Returns:
        Encoded JWT string.
    """
    secret = secret or settings.JWT_SECRET
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    )
    to_encode.update({
        "exp": expire,
        "type": "refresh",
        "iat": datetime.now(timezone.utc),
    })
    return jwt.encode(to_encode, secret, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, secret: str | None = None) -> dict[str, Any]:
    """Decode and return the payload of a JWT token without verifying the type.

    Args:
        token: Encoded JWT string.
        secret: Secret key override (defaults to settings.JWT_SECRET).

    Returns:
        Decoded payload dictionary.

    Raises:
        jwt.InvalidTokenError: If the token is malformed or signature is invalid.
    """
    secret = secret or settings.JWT_SECRET
    return jwt.decode(token, secret, algorithms=[settings.JWT_ALGORITHM])


def verify_token(token: str, expected_type: str = "access", secret: str | None = None) -> dict[str, Any]:
    """Verify a JWT token and assert its type matches the expected type.

    Args:
        token: Encoded JWT string.
        expected_type: Expected token type ("access" or "refresh").
        secret: Secret key override (defaults to settings.JWT_SECRET).

    Returns:
        Decoded payload dictionary.

    Raises:
        ValueError: If the token type does not match expected_type.
        jwt.InvalidTokenError: If the token is malformed or expired.
    """
    payload = decode_token(token, secret)
    token_type = payload.get("type", "access")
    if token_type != expected_type:
        raise ValueError(f"Invalid token type: expected '{expected_type}', got '{token_type}'")
    return payload