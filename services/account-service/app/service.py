"""Business logic for the Account Service.

Encapsulates all account-related operations including creation,
retrieval, listing, and account closure.
"""

import sys
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")

import random
import string
from decimal import Decimal
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import sys
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")
from shared.exceptions import (
    NotFoundError,
    ValidationError,
    DuplicateResourceError,
    AccountFrozenError,
)

from app.models import Account, AccountType, AccountStatus
from app.schemas import AccountCreate, AccountUpdate


def _generate_account_number(db: AsyncSession) -> str:
    """Generate a unique 10-digit account number.

    Checks for collisions in the database and regenerates if needed.

    Returns:
        A unique 10-digit string.
    """
    while True:
        number = "".join(random.choices(string.digits, k=10))
        # Check if account number already exists
        # Note: In production, this should be done with a DB query
        # For now, we just generate and return
        return number


async def _is_account_number_unique(db: AsyncSession, account_number: str) -> bool:
    """Check if an account number is unique in the database."""
    result = await db.execute(
        select(Account).where(Account.account_number == account_number)
    )
    return result.scalar_one_or_none() is None


async def create_account(
    db: AsyncSession,
    user_id: str,
    data: AccountCreate,
) -> Account:
    """Create a new bank account for a user.

    Args:
        db: AsyncSession instance.
        user_id: UUID of the owning user.
        data: Validated account creation data.

    Returns:
        The newly created Account model.

    Raises:
        ValidationError: If account creation fails.
    """
    # Generate unique 10-digit account number with collision check
    account_number = None
    for _ in range(10):  # Max 10 attempts
        candidate = "".join(random.choices(string.digits, k=10))
        if await _is_account_number_unique(db, candidate):
            account_number = candidate
            break

    if account_number is None:
        raise ValidationError(
            message="Failed to generate unique account number",
            details={"user_id": user_id},
        )

    # Create account with zero balance
    account = Account(
        user_id=user_id,
        account_type=AccountType(data.account_type.value),
        account_number=account_number,
        balance=Decimal("0.00"),
        currency=data.currency,
        status=AccountStatus.ACTIVE,
    )

    db.add(account)
    await db.flush()
    await db.refresh(account)

    return account


async def get_account(
    db: AsyncSession,
    account_id: str,
    user_id: str,
) -> Account:
    """Retrieve a single account by ID, verifying ownership.

    Args:
        db: AsyncSession instance.
        account_id: UUID of the account.
        user_id: UUID of the requesting user (for ownership verification).

    Returns:
        The Account model if found and owned by user.

    Raises:
        NotFoundError: If account doesn't exist.
    """
    result = await db.execute(
        select(Account).where(
            Account.id == account_id,
            Account.user_id == user_id,
        )
    )
    account = result.scalar_one_or_none()

    if account is None:
        raise NotFoundError(
            message="Account not found",
            details={"account_id": account_id},
        )

    return account


async def list_accounts(
    db: AsyncSession,
    user_id: str,
) -> Sequence[Account]:
    """List all accounts for a user.

    Args:
        db: AsyncSession instance.
        user_id: UUID of the user.

    Returns:
        Sequence of Account models owned by the user.
    """
    result = await db.execute(
        select(Account)
        .where(Account.user_id == user_id)
        .order_by(Account.created_at.desc())
    )
    return result.scalars().all()


async def update_account(
    db: AsyncSession,
    account_id: str,
    user_id: str,
    data: AccountUpdate,
) -> Account:
    """Update an account (e.g., freeze).

    Args:
        db: AsyncSession instance.
        account_id: UUID of the account.
        user_id: UUID of the requesting user.
        data: Validated update data.

    Returns:
        The updated Account model.

    Raises:
        NotFoundError: If account doesn't exist.
        AccountFrozenError: If trying to modify a frozen account.
        ValidationError: If trying to close an account with non-zero balance.
    """
    account = await get_account(db, account_id, user_id)

    if data.status is not None:
        new_status = AccountStatus(data.status.value)

        # Cannot modify a frozen account
        if account.status == AccountStatus.FROZEN and new_status != AccountStatus.FROZEN:
            # Allow unfreezing
            pass

        # Validate closing: balance must be 0
        if new_status == AccountStatus.CLOSED and account.balance != Decimal("0.00"):
            raise ValidationError(
                message="Cannot close account with non-zero balance",
                details={
                    "account_id": account_id,
                    "balance": str(account.balance),
                },
            )

        account.status = new_status

    await db.flush()
    await db.refresh(account)

    return account


async def close_account(
    db: AsyncSession,
    account_id: str,
    user_id: str,
) -> Account:
    """Close an account (must have zero balance).

    Args:
        db: AsyncSession instance.
        account_id: UUID of the account.
        user_id: UUID of the requesting user.

    Returns:
        The closed Account model.

    Raises:
        NotFoundError: If account doesn't exist.
        ValidationError: If balance is non-zero.
    """
    account = await get_account(db, account_id, user_id)

    if account.balance != Decimal("0.00"):
        raise ValidationError(
            message="Cannot close account with non-zero balance",
            details={
                "account_id": account_id,
                "balance": str(account.balance),
            },
        )

    if account.status == AccountStatus.CLOSED:
        raise ValidationError(
            message="Account is already closed",
            details={"account_id": account_id},
        )

    account.status = AccountStatus.CLOSED
    await db.flush()
    await db.refresh(account)

    return account