"""Pydantic v2 schemas for the Account Service API.

Defines request/response models for account operations.
"""

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class AccountTypeEnum(str, Enum):
    """Account type enumeration for API schemas."""

    CHECKING = "CHECKING"
    SAVINGS = "SAVINGS"
    LOAN = "LOAN"


class AccountStatusEnum(str, Enum):
    """Account status enumeration for API schemas."""

    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    CLOSED = "CLOSED"


class AccountCreate(BaseModel):
    """Request body for creating a new account."""

    account_type: AccountTypeEnum = Field(
        ...,
        description="Type of account to create (CHECKING, SAVINGS, LOAN)",
    )
    currency: str = Field(
        default="USD",
        min_length=3,
        max_length=3,
        description="Currency code (3 letters)",
    )


class AccountUpdate(BaseModel):
    """Request body for updating an account (e.g., freeze)."""

    status: Optional[AccountStatusEnum] = Field(
        None,
        description="New account status (ACTIVE, FROZEN, CLOSED)",
    )


class AccountBalanceUpdate(BaseModel):
    """Request body for balance updates (internal use by transaction service)."""

    amount: Decimal = Field(
        ...,
        description="Amount to add (positive) or subtract (negative)",
    )


class AccountOut(BaseModel):
    """Public representation of an account."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Account UUID")
    user_id: str = Field(..., description="Owner user UUID")
    account_type: AccountTypeEnum = Field(..., description="Account type")
    account_number: str = Field(..., description="Unique 10-digit account number")
    balance: Decimal = Field(..., description="Current balance")
    currency: str = Field(..., description="Currency code")
    status: AccountStatusEnum = Field(..., description="Account status")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class AccountListResponse(BaseModel):
    """Paginated response for account listing."""

    accounts: list[AccountOut] = Field(..., description="List of accounts")
    total: int = Field(..., description="Total number of accounts")


class HealthResponse(BaseModel):
    """Response body for the health check endpoint."""

    status: str = Field(..., description="Service health status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")