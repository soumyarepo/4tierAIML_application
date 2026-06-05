"""SQLAlchemy 2.0 async models for the Account Service.

Defines the Account table stored in the bank_accounts database.
"""

import uuid
import enum
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String, ForeignKey, Index, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from typing import TYPE_CHECKING

import sys
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")
from shared.database import Base

if TYPE_CHECKING:
    pass


class AccountType(str, enum.Enum):
    """Enumeration of account types."""

    CHECKING = "CHECKING"
    SAVINGS = "SAVINGS"
    LOAN = "LOAN"


class AccountStatus(str, enum.Enum):
    """Enumeration of account statuses."""

    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    CLOSED = "CLOSED"


class Account(Base):
    """Represents a bank account.

    Attributes:
        id: UUID primary key.
        user_id: UUID of the owning user (indexed).
        account_type: Type of account (CHECKING, SAVINGS, LOAN).
        account_number: Unique 10-digit account number.
        balance: Current account balance (DECIMAL 18,2).
        currency: Currency code (default USD).
        status: Account status (ACTIVE, FROZEN, CLOSED).
        created_at: Timestamp when the account was created.
        updated_at: Timestamp of the last update.
    """

    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    account_type: Mapped[AccountType] = mapped_column(
        SAEnum(AccountType, name="account_type"),
        nullable=False,
    )
    account_number: Mapped[str] = mapped_column(
        String(10),
        unique=True,
        nullable=False,
        index=True,
    )
    balance: Mapped[Decimal] = mapped_column(
        String(20),
        nullable=False,
        default=Decimal("0.00"),
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD",
    )
    status: Mapped[AccountStatus] = mapped_column(
        SAEnum(AccountStatus, name="account_status"),
        nullable=False,
        default=AccountStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_accounts_user_id", "user_id"),
        Index("ix_accounts_account_number", "account_number"),
    )