"""SQLAlchemy 2.0 async models for the Transaction Service.

Defines the Transaction and TransactionEntry tables stored in the bank_transactions database.
"""

import uuid
import enum
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String, ForeignKey, Index, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from typing import TYPE_CHECKING

import sys
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")
from shared.database import Base

if TYPE_CHECKING:
    pass


class TransactionType(str, enum.Enum):
    """Enumeration of transaction types."""

    TRANSFER = "TRANSFER"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    PAYMENT = "PAYMENT"
    FEE = "FEE"


class TransactionStatus(str, enum.Enum):
    """Enumeration of transaction statuses."""

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REVERSED = "REVERSED"


class EntryType(str, enum.Enum):
    """Enumeration of entry types for double-entry bookkeeping."""

    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class Transaction(Base):
    """Represents a financial transaction with double-entry bookkeeping.

    Attributes:
        id: UUID primary key.
        reference_number: Unique 16-character reference number.
        from_account_id: Source account UUID (nullable for deposits).
        to_account_id: Destination account UUID (nullable for withdrawals).
        amount: Transaction amount (DECIMAL 18,2).
        currency: Currency code.
        type: Transaction type (TRANSFER, DEPOSIT, WITHDRAWAL, etc.).
        status: Current status (PENDING, COMPLETED, FAILED, REVERSED).
        idempotency_key: Unique key to prevent duplicate transactions.
        description: Optional transaction description.
        created_at: Timestamp when the transaction was created.
        updated_at: Timestamp of the last update.
    """

    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    reference_number: Mapped[str] = mapped_column(
        String(16),
        unique=True,
        nullable=False,
        index=True,
    )
    from_account_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    to_account_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(
        String(20),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD",
    )
    type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType, name="transaction_type"),
        nullable=False,
    )
    status: Mapped[TransactionStatus] = mapped_column(
        SAEnum(TransactionStatus, name="transaction_status"),
        nullable=False,
        default=TransactionStatus.PENDING,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
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

    # Relationships
    entries: Mapped[list["TransactionEntry"]] = relationship(
        "TransactionEntry",
        back_populates="transaction",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_transactions_idempotency_key", "idempotency_key"),
        Index("ix_transactions_from_account_id", "from_account_id"),
        Index("ix_transactions_to_account_id", "to_account_id"),
        Index("ix_transactions_reference_number", "reference_number"),
    )


class TransactionEntry(Base):
    """Represents a single entry in double-entry bookkeeping.

    Each transaction has 2 entries: one DEBIT and one CREDIT.

    Attributes:
        id: UUID primary key.
        transaction_id: Foreign key to the parent transaction.
        account_id: Account UUID this entry affects.
        entry_type: DEBIT or CREDIT.
        amount: Entry amount (always positive, type determines direction).
        created_at: Timestamp when the entry was created.
    """

    __tablename__ = "transaction_entries"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    transaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    entry_type: Mapped[EntryType] = mapped_column(
        SAEnum(EntryType, name="entry_type"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(
        String(20),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    transaction: Mapped["Transaction"] = relationship(
        "Transaction",
        back_populates="entries",
    )

    __table_args__ = (
        Index("ix_transaction_entries_account_id", "account_id"),
    )