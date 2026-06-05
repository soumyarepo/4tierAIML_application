"""Pydantic v2 schemas for the Transaction Service API.

Defines request/response models for transaction operations.
"""

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class TransactionTypeEnum(str, Enum):
    """Transaction type enumeration for API schemas."""

    TRANSFER = "TRANSFER"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    PAYMENT = "PAYMENT"
    FEE = "FEE"


class TransactionStatusEnum(str, Enum):
    """Transaction status enumeration for API schemas."""

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REVERSED = "REVERSED"


class EntryTypeEnum(str, Enum):
    """Entry type enumeration for double-entry bookkeeping."""

    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class TransferRequest(BaseModel):
    """Request body for transferring funds between accounts."""

    from_account_id: str = Field(..., description="Source account UUID")
    to_account_id: str = Field(..., description="Destination account UUID")
    amount: Decimal = Field(
        ...,
        gt=0,
        description="Amount to transfer (must be positive)",
    )
    currency: str = Field(
        default="USD",
        min_length=3,
        max_length=3,
        description="Currency code",
    )
    description: Optional[str] = Field(
        None,
        max_length=255,
        description="Optional transaction description",
    )
    idempotency_key: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique key for idempotent request",
    )


class DepositRequest(BaseModel):
    """Request body for depositing funds to an account."""

    to_account_id: str = Field(..., description="Destination account UUID")
    amount: Decimal = Field(
        ...,
        gt=0,
        description="Amount to deposit (must be positive)",
    )
    currency: str = Field(
        default="USD",
        min_length=3,
        max_length=3,
        description="Currency code",
    )
    description: Optional[str] = Field(
        None,
        max_length=255,
        description="Optional transaction description",
    )
    idempotency_key: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique key for idempotent request",
    )


class WithdrawalRequest(BaseModel):
    """Request body for withdrawing funds from an account."""

    from_account_id: str = Field(..., description="Source account UUID")
    amount: Decimal = Field(
        ...,
        gt=0,
        description="Amount to withdraw (must be positive)",
    )
    currency: str = Field(
        default="USD",
        min_length=3,
        max_length=3,
        description="Currency code",
    )
    description: Optional[str] = Field(
        None,
        max_length=255,
        description="Optional transaction description",
    )
    idempotency_key: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique key for idempotent request",
    )


class TransactionEntryOut(BaseModel):
    """Single entry in double-entry bookkeeping."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Entry UUID")
    account_id: str = Field(..., description="Account UUID")
    entry_type: EntryTypeEnum = Field(..., description="DEBIT or CREDIT")
    amount: Decimal = Field(..., description="Entry amount")
    created_at: datetime = Field(..., description="Creation timestamp")


class TransactionOut(BaseModel):
    """Public representation of a transaction with entries."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Transaction UUID")
    reference_number: str = Field(..., description="Unique reference number")
    from_account_id: Optional[str] = Field(None, description="Source account UUID")
    to_account_id: Optional[str] = Field(None, description="Destination account UUID")
    amount: Decimal = Field(..., description="Transaction amount")
    currency: str = Field(..., description="Currency code")
    type: TransactionTypeEnum = Field(..., description="Transaction type")
    status: TransactionStatusEnum = Field(..., description="Transaction status")
    description: Optional[str] = Field(None, description="Transaction description")
    entries: list[TransactionEntryOut] = Field(
        default_factory=list,
        description="Double-entry bookkeeping entries",
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class TransactionListResponse(BaseModel):
    """Paginated response for transaction history."""

    transactions: list[TransactionOut] = Field(..., description="List of transactions")
    total: int = Field(..., description="Total number of transactions")
    limit: int = Field(..., description="Number of transactions per page")
    offset: int = Field(..., description="Offset from the beginning")


class HealthResponse(BaseModel):
    """Response body for the health check endpoint."""

    status: str = Field(..., description="Service health status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")