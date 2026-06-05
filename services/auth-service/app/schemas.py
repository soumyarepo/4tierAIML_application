"""Pydantic v2 schemas for the Auth Service API.

Defines request/response models for registration, login, token operations,
and admin user management.
"""

from pydantic import BaseModel, EmailStr, Field, ConfigDict
from datetime import datetime
from typing import Optional
from enum import Enum


class UserRole(str, Enum):
    """User role enumeration for API schemas."""

    CUSTOMER = "customer"
    ADMIN = "admin"
    AGENT = "agent"


# ---------------------------------------------------------------------------
# Registration & Login
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    """Request body for user self-registration.

    Only customers can register themselves. Staff accounts must be created
    by an admin.
    """

    email: EmailStr = Field(..., description="Unique email address")
    full_name: str = Field(..., min_length=1, max_length=255, description="Display name")
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (8-128 characters)",
    )


class UserLogin(BaseModel):
    """Request body for user login."""

    email: EmailStr = Field(..., description="Registered email address")
    password: str = Field(..., description="Password")


# ---------------------------------------------------------------------------
# Token Schemas
# ---------------------------------------------------------------------------


class TokenPair(BaseModel):
    """Response body containing access and refresh token pair."""

    access_token: str = Field(..., description="Short-lived JWT access token")
    refresh_token: str = Field(..., description="Opaque refresh token (UUID)")
    token_type: str = Field(default="bearer", description="Token type identifier")
    expires_in: int = Field(..., description="Access token lifetime in seconds")


class RefreshRequest(BaseModel):
    """Request body for access token refresh."""

    refresh_token: str = Field(..., description="Opaque refresh token")


class TokenPayload(BaseModel):
    """Decoded JWT payload for the current user."""

    sub: str = Field(..., description="User ID (subject)")
    email: str = Field(..., description="User email")
    role: UserRole = Field(..., description="User role")
    exp: datetime = Field(..., description="Token expiration time")
    type: str = Field(..., description="Token type (access or refresh)")


# ---------------------------------------------------------------------------
# User Response Schemas
# ---------------------------------------------------------------------------


class UserOut(BaseModel):
    """Public representation of a user (excludes sensitive fields)."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="User UUID")
    email: EmailStr = Field(..., description="Email address")
    full_name: str = Field(..., description="Display name")
    role: UserRole = Field(..., description="User role")
    is_active: bool = Field(..., description="Whether the account is active")
    created_at: datetime = Field(..., description="Account creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


# ---------------------------------------------------------------------------
# Admin Schemas
# ---------------------------------------------------------------------------


class AdminUserListResponse(BaseModel):
    """Paginated response for the admin user listing endpoint."""

    users: list[UserOut] = Field(..., description="List of users")
    total: int = Field(..., description="Total number of users matching the query")
    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Number of users per page")
    total_pages: int = Field(..., description="Total number of pages")


# ---------------------------------------------------------------------------
# Health & Error Schemas
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Response body for the health check endpoint."""

    status: str = Field(..., description="Service health status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")