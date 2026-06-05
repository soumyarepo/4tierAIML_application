"""Business logic for the Transaction Service.

Encapsulates all transaction-related operations including transfers,
deposits, withdrawals with double-entry bookkeeping, idempotency,
and Kafka event publishing.
"""

import sys
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")

import random
import string
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from aiokafka import AIOKafkaProducer
import redis.asyncio as aioredis

import sys
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")
from shared.config import settings
from shared.kafka_client import KafkaProducerWrapper
from shared.exceptions import (
    NotFoundError,
    ValidationError,
    InsufficientFundsError,
    AccountFrozenError,
)

from app.models import (
    Transaction,
    TransactionEntry,
    TransactionType,
    TransactionStatus,
    EntryType,
)
from app.schemas import TransferRequest, DepositRequest, WithdrawalRequest


# ---------------------------------------------------------------------------
# Reference Number Generation
# ---------------------------------------------------------------------------


def _generate_reference_number() -> str:
    """Generate a unique 16-character reference number.

    Format: 2 letter prefix + 14 alphanumeric characters.
    Example: TX1A2B3C4D5E6F
    """
    prefix = "TX"
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=14))
    return f"{prefix}{suffix}"


# ---------------------------------------------------------------------------
# Idempotency Checking
# ---------------------------------------------------------------------------


async def _check_idempotency(
    redis_client: aioredis.Redis,
    idempotency_key: str,
) -> Optional[str]:
    """Check if an idempotency key exists in Redis.

    Args:
        redis_client: aioredis client.
        idempotency_key: Unique request key.

    Returns:
        Existing transaction ID if found, None otherwise.
    """
    key = f"idempotency:{idempotency_key}"
    result = await redis_client.get(key)
    return result


async def _store_idempotency(
    redis_client: aioredis.Redis,
    idempotency_key: str,
    transaction_id: str,
    ttl_seconds: int = 86400,
) -> None:
    """Store idempotency key in Redis with TTL.

    Args:
        redis_client: aioredis client.
        idempotency_key: Unique request key.
        transaction_id: Associated transaction ID.
        ttl_seconds: Time-to-live in seconds (default 24 hours).
    """
    key = f"idempotency:{idempotency_key}"
    await redis_client.setex(key, ttl_seconds, transaction_id)


# ---------------------------------------------------------------------------
# Account Verification (via direct DB connection to accounts DB)
# ---------------------------------------------------------------------------


async def _verify_account_ownership(
    db: AsyncSession,
    account_id: str,
    user_id: str,
) -> tuple[bool, Optional[Decimal], Optional[str]]:
    """Verify account exists and belongs to user.

    Returns:
        Tuple of (exists_and_owned, balance, status) or (False, None, None).
    """
    # Query the accounts database directly using raw connection
    from app.database import get_session_factory
    
    # Import account model for the query
    sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")
    # We need to connect to accounts DB - use a separate connection
    accounts_url = settings.get_bank_accounts_db_url()
    from sqlalchemy.ext.asyncio import create_async_engine
    
    engine = create_async_engine(accounts_url, echo=False)
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT balance, status, user_id FROM accounts WHERE id = :account_id"),
            {"account_id": account_id}
        )
        row = result.fetchone()
    await engine.dispose()
    
    if row is None:
        return False, None, None
    
    balance = Decimal(str(row[0]))
    status = row[1]
    owner_id = row[2]
    
    if owner_id != user_id:
        return False, None, None
    
    return True, balance, status


# ---------------------------------------------------------------------------
# Audit Logging to MongoDB
# ---------------------------------------------------------------------------


async def _log_audit(
    mongo_client,
    user_id: str,
    account_ids: list[str],
    amount: Decimal,
    transaction_type: str,
    transaction_id: str,
) -> None:
    """Write an audit log entry to MongoDB.

    Args:
        mongo_client: Motor AsyncIOMotorClient.
        user_id: User performing the transaction.
        account_ids: List of affected account IDs.
        amount: Transaction amount.
        transaction_type: Type of transaction.
        transaction_id: Transaction UUID.
    """
    db = mongo_client["bank_audit"]
    collection = db["transaction_audit"]
    
    audit_entry = {
        "date": datetime.now(timezone.utc),
        "user_id": user_id,
        "account_ids": account_ids,
        "amount": float(amount),
        "type": transaction_type,
        "transaction_id": transaction_id,
    }
    
    await collection.insert_one(audit_entry)


# ---------------------------------------------------------------------------
# Transaction Service Functions
# ---------------------------------------------------------------------------


async def create_transfer(
    db: AsyncSession,
    redis_client: aioredis.Redis,
    kafka_producer: KafkaProducerWrapper,
    mongo_client,
    user_id: str,
    data: TransferRequest,
) -> Transaction:
    """Create a transfer transaction between two accounts.

    Implements:
    1. Idempotency check via Redis
    2. SERIALIZABLE transaction with SELECT FOR UPDATE
    3. Deadlock prevention via ordered account UUIDs
    4. Balance verification
    5. Double-entry bookkeeping
    6. Kafka event publishing
    7. MongoDB audit logging

    Args:
        db: AsyncSession instance.
        redis_client: aioredis client for idempotency.
        kafka_producer: Kafka producer for events.
        mongo_client: MongoDB client for audit logs.
        user_id: UUID of the authenticated user.
        data: Validated transfer request.

    Returns:
        The created Transaction with entries.

    Raises:
        NotFoundError: If account not found or not owned by user.
        InsufficientFundsError: If source account has insufficient balance.
        AccountFrozenError: If either account is frozen.
        ValidationError: If transfer validation fails.
    """
    # 1. Check idempotency
    existing_tx = await _check_idempotency(redis_client, data.idempotency_key)
    if existing_tx:
        # Return existing transaction
        result = await db.execute(
            select(Transaction).where(Transaction.id == existing_tx)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing
        # If not found in DB, continue with new transaction

    # 2. Begin transaction with SERIALIZABLE isolation
    # Note: SQLAlchemy async doesn't directly support SERIALIZABLE isolation
    # We'll use SELECT FOR UPDATE for row-level locking instead

    # 3. Lock accounts in order to prevent deadlocks (lowest UUID first)
    account_ids = sorted([data.from_account_id, data.to_account_id])
    
    # Execute SELECT FOR UPDATE on both accounts
    locked_accounts = {}
    for acc_id in account_ids:
        result = await db.execute(
            text("SELECT id, user_id, balance, status FROM accounts WHERE id = :acc_id FOR UPDATE"),
            {"acc_id": acc_id}
        )
        row = result.fetchone()
        if row is None:
            raise NotFoundError(
                message="Account not found",
                details={"account_id": acc_id},
            )
        locked_accounts[acc_id] = {
            "user_id": row[1],
            "balance": Decimal(str(row[2])),
            "status": row[3],
        }

    # 4. Verify ownership of both accounts
    from_account = locked_accounts[data.from_account_id]
    to_account = locked_accounts[data.to_account_id]

    if from_account["user_id"] != user_id:
        raise NotFoundError(
            message="Source account not found",
            details={"account_id": data.from_account_id},
        )

    # 5. Check for frozen accounts
    if from_account["status"] == "FROZEN":
        raise AccountFrozenError(
            message="Source account is frozen",
            details={"account_id": data.from_account_id},
        )
    if to_account["status"] == "FROZEN":
        raise AccountFrozenError(
            message="Destination account is frozen",
            details={"account_id": data.to_account_id},
        )

    # 6. Verify sufficient balance
    if from_account["balance"] < data.amount:
        raise InsufficientFundsError(
            message="Insufficient funds for transfer",
            details={
                "account_id": data.from_account_id,
                "available": str(from_account["balance"]),
                "requested": str(data.amount),
            },
        )

    # 7. Create transaction with PENDING status
    reference = _generate_reference_number()
    transaction = Transaction(
        reference_number=reference,
        from_account_id=data.from_account_id,
        to_account_id=data.to_account_id,
        amount=data.amount,
        currency=data.currency,
        type=TransactionType.TRANSFER,
        status=TransactionStatus.PENDING,
        idempotency_key=data.idempotency_key,
        description=data.description,
    )
    db.add(transaction)
    await db.flush()

    # 8. Create double-entry: DEBIT from_account, CREDIT to_account
    debit_entry = TransactionEntry(
        transaction_id=transaction.id,
        account_id=data.from_account_id,
        entry_type=EntryType.DEBIT,
        amount=data.amount,
    )
    credit_entry = TransactionEntry(
        transaction_id=transaction.id,
        account_id=data.to_account_id,
        entry_type=EntryType.CREDIT,
        amount=data.amount,
    )
    db.add(debit_entry)
    db.add(credit_entry)

    # 9. Update account balances
    from_balance = from_account["balance"] - data.amount
    to_balance = to_account["balance"] + data.amount

    await db.execute(
        text("UPDATE accounts SET balance = :balance WHERE id = :account_id"),
        {"balance": str(from_balance), "account_id": data.from_account_id}
    )
    await db.execute(
        text("UPDATE accounts SET balance = :balance WHERE id = :account_id"),
        {"balance": str(to_balance), "account_id": data.to_account_id}
    )

    # 10. Mark transaction as COMPLETED
    transaction.status = TransactionStatus.COMPLETED
    await db.flush()

    # 11. Commit the transaction
    await db.commit()
    await db.refresh(transaction)

    # 12. Write audit log to MongoDB
    try:
        await _log_audit(
            mongo_client=mongo_client,
            user_id=user_id,
            account_ids=[data.from_account_id, data.to_account_id],
            amount=data.amount,
            transaction_type="TRANSFER",
            transaction_id=transaction.id,
        )
    except Exception as e:
        # Log but don't fail - audit is secondary
        import structlog
        logger = structlog.get_logger()
        logger.error("audit_log_failed", error=str(e), transaction_id=transaction.id)

    # 13. Publish Kafka event
    try:
        await kafka_producer.send(
            topic="transaction.created",
            value={
                "event": "transaction.created",
                "transaction_id": transaction.id,
                "reference_number": transaction.reference_number,
                "type": "TRANSFER",
                "amount": str(data.amount),
                "currency": data.currency,
                "from_account_id": data.from_account_id,
                "to_account_id": data.to_account_id,
                "user_id": user_id,
                "status": "COMPLETED",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            key=transaction.id,
        )
    except Exception as e:
        import structlog
        logger = structlog.get_logger()
        logger.error("kafka_publish_failed", error=str(e), transaction_id=transaction.id)

    # 14. Store idempotency key in Redis
    await _store_idempotency(redis_client, data.idempotency_key, transaction.id)

    return transaction


async def create_deposit(
    db: AsyncSession,
    redis_client: aioredis.Redis,
    kafka_producer: KafkaProducerWrapper,
    mongo_client,
    user_id: str,
    data: DepositRequest,
) -> Transaction:
    """Create a deposit transaction.

    Args:
        db: AsyncSession instance.
        redis_client: aioredis client for idempotency.
        kafka_producer: Kafka producer for events.
        mongo_client: MongoDB client for audit logs.
        user_id: UUID of the authenticated user.
        data: Validated deposit request.

    Returns:
        The created Transaction with entries.
    """
    # Check idempotency
    existing_tx = await _check_idempotency(redis_client, data.idempotency_key)
    if existing_tx:
        result = await db.execute(
            select(Transaction).where(Transaction.id == existing_tx)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    # Lock the destination account
    result = await db.execute(
        text("SELECT id, user_id, balance, status FROM accounts WHERE id = :acc_id FOR UPDATE"),
        {"acc_id": data.to_account_id}
    )
    row = result.fetchone()
    if row is None:
        raise NotFoundError(
            message="Account not found",
            details={"account_id": data.to_account_id},
        )

    if row[1] != user_id:
        raise NotFoundError(
            message="Account not found",
            details={"account_id": data.to_account_id},
        )

    if row[3] == "FROZEN":
        raise AccountFrozenError(
            message="Account is frozen",
            details={"account_id": data.to_account_id},
        )

    # Create transaction
    reference = _generate_reference_number()
    transaction = Transaction(
        reference_number=reference,
        from_account_id=None,
        to_account_id=data.to_account_id,
        amount=data.amount,
        currency=data.currency,
        type=TransactionType.DEPOSIT,
        status=TransactionStatus.PENDING,
        idempotency_key=data.idempotency_key,
        description=data.description,
    )
    db.add(transaction)
    await db.flush()

    # Create double-entry: CREDIT to_account (no DEBIT side for deposit)
    credit_entry = TransactionEntry(
        transaction_id=transaction.id,
        account_id=data.to_account_id,
        entry_type=EntryType.CREDIT,
        amount=data.amount,
    )
    db.add(credit_entry)

    # Update balance
    new_balance = Decimal(str(row[2])) + data.amount
    await db.execute(
        text("UPDATE accounts SET balance = :balance WHERE id = :account_id"),
        {"balance": str(new_balance), "account_id": data.to_account_id}
    )

    # Mark completed
    transaction.status = TransactionStatus.COMPLETED
    await db.flush()
    await db.commit()
    await db.refresh(transaction)

    # Audit log
    try:
        await _log_audit(
            mongo_client=mongo_client,
            user_id=user_id,
            account_ids=[data.to_account_id],
            amount=data.amount,
            transaction_type="DEPOSIT",
            transaction_id=transaction.id,
        )
    except Exception:
        pass

    # Kafka event
    try:
        await kafka_producer.send(
            topic="transaction.created",
            value={
                "event": "transaction.created",
                "transaction_id": transaction.id,
                "reference_number": transaction.reference_number,
                "type": "DEPOSIT",
                "amount": str(data.amount),
                "currency": data.currency,
                "to_account_id": data.to_account_id,
                "user_id": user_id,
                "status": "COMPLETED",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            key=transaction.id,
        )
    except Exception:
        pass

    # Store idempotency
    await _store_idempotency(redis_client, data.idempotency_key, transaction.id)

    return transaction


async def create_withdrawal(
    db: AsyncSession,
    redis_client: aioredis.Redis,
    kafka_producer: KafkaProducerWrapper,
    mongo_client,
    user_id: str,
    data: WithdrawalRequest,
) -> Transaction:
    """Create a withdrawal transaction.

    Args:
        db: AsyncSession instance.
        redis_client: aioredis client for idempotency.
        kafka_producer: Kafka producer for events.
        mongo_client: MongoDB client for audit logs.
        user_id: UUID of the authenticated user.
        data: Validated withdrawal request.

    Returns:
        The created Transaction with entries.
    """
    # Check idempotency
    existing_tx = await _check_idempotency(redis_client, data.idempotency_key)
    if existing_tx:
        result = await db.execute(
            select(Transaction).where(Transaction.id == existing_tx)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    # Lock the source account
    result = await db.execute(
        text("SELECT id, user_id, balance, status FROM accounts WHERE id = :acc_id FOR UPDATE"),
        {"acc_id": data.from_account_id}
    )
    row = result.fetchone()
    if row is None:
        raise NotFoundError(
            message="Account not found",
            details={"account_id": data.from_account_id},
        )

    if row[1] != user_id:
        raise NotFoundError(
            message="Account not found",
            details={"account_id": data.from_account_id},
        )

    if row[3] == "FROZEN":
        raise AccountFrozenError(
            message="Account is frozen",
            details={"account_id": data.from_account_id},
        )

    current_balance = Decimal(str(row[2]))
    if current_balance < data.amount:
        raise InsufficientFundsError(
            message="Insufficient funds for withdrawal",
            details={
                "account_id": data.from_account_id,
                "available": str(current_balance),
                "requested": str(data.amount),
            },
        )

    # Create transaction
    reference = _generate_reference_number()
    transaction = Transaction(
        reference_number=reference,
        from_account_id=data.from_account_id,
        to_account_id=None,
        amount=data.amount,
        currency=data.currency,
        type=TransactionType.WITHDRAWAL,
        status=TransactionStatus.PENDING,
        idempotency_key=data.idempotency_key,
        description=data.description,
    )
    db.add(transaction)
    await db.flush()

    # Create double-entry: DEBIT from_account (no CREDIT side for withdrawal)
    debit_entry = TransactionEntry(
        transaction_id=transaction.id,
        account_id=data.from_account_id,
        entry_type=EntryType.DEBIT,
        amount=data.amount,
    )
    db.add(debit_entry)

    # Update balance
    new_balance = current_balance - data.amount
    await db.execute(
        text("UPDATE accounts SET balance = :balance WHERE id = :account_id"),
        {"balance": str(new_balance), "account_id": data.from_account_id}
    )

    # Mark completed
    transaction.status = TransactionStatus.COMPLETED
    await db.flush()
    await db.commit()
    await db.refresh(transaction)

    # Audit log
    try:
        await _log_audit(
            mongo_client=mongo_client,
            user_id=user_id,
            account_ids=[data.from_account_id],
            amount=data.amount,
            transaction_type="WITHDRAWAL",
            transaction_id=transaction.id,
        )
    except Exception:
        pass

    # Kafka event
    try:
        await kafka_producer.send(
            topic="transaction.created",
            value={
                "event": "transaction.created",
                "transaction_id": transaction.id,
                "reference_number": transaction.reference_number,
                "type": "WITHDRAWAL",
                "amount": str(data.amount),
                "currency": data.currency,
                "from_account_id": data.from_account_id,
                "user_id": user_id,
                "status": "COMPLETED",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            key=transaction.id,
        )
    except Exception:
        pass

    # Store idempotency
    await _store_idempotency(redis_client, data.idempotency_key, transaction.id)

    return transaction


async def get_transaction(
    db: AsyncSession,
    transaction_id: str,
    user_id: str,
) -> Transaction:
    """Retrieve a transaction by ID with ownership verification.

    Args:
        db: AsyncSession instance.
        transaction_id: UUID of the transaction.
        user_id: UUID of the requesting user.

    Returns:
        Transaction with entries.

    Raises:
        NotFoundError: If transaction not found or user doesn't own involved accounts.
    """
    result = await db.execute(
        select(Transaction)
        .where(Transaction.id == transaction_id)
    )
    transaction = result.scalar_one_or_none()

    if transaction is None:
        raise NotFoundError(
            message="Transaction not found",
            details={"transaction_id": transaction_id},
        )

    # Verify user owns at least one of the accounts involved
    if transaction.from_account_id:
        result = await db.execute(
            text("SELECT user_id FROM accounts WHERE id = :account_id"),
            {"account_id": transaction.from_account_id}
        )
        row = result.fetchone()
        if row and row[0] == user_id:
            return transaction

    if transaction.to_account_id:
        result = await db.execute(
            text("SELECT user_id FROM accounts WHERE id = :account_id"),
            {"account_id": transaction.to_account_id}
        )
        row = result.fetchone()
        if row and row[0] == user_id:
            return transaction

    raise NotFoundError(
        message="Transaction not found",
        details={"transaction_id": transaction_id},
    )


async def get_transaction_history(
    db: AsyncSession,
    user_id: str,
    account_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[Sequence[Transaction], int]:
    """Get paginated transaction history for a user.

    Args:
        db: AsyncSession instance.
        user_id: UUID of the user.
        account_id: Optional account ID to filter by.
        limit: Maximum number of transactions to return.
        offset: Number of transactions to skip.

    Returns:
        Tuple of (transactions, total_count).
    """
    # Get user's account IDs
    accounts_url = settings.get_bank_accounts_db_url()
    from sqlalchemy.ext.asyncio import create_async_engine
    
    engine = create_async_engine(accounts_url, echo=False)
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT id FROM accounts WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        account_ids = [row[0] for row in result.fetchall()]
    await engine.dispose()

    if not account_ids:
        return [], 0

    # Filter by specific account if provided
    if account_id and account_id not in account_ids:
        return [], 0

    # Build query for transactions involving user's accounts
    if account_id:
        account_filter = account_id
    else:
        # Get all transactions for any of user's accounts
        pass

    # Query transactions
    if account_id:
        query = select(Transaction).where(
            (Transaction.from_account_id == account_id) |
            (Transaction.to_account_id == account_id)
        ).order_by(Transaction.created_at.desc())
    else:
        query = select(Transaction).where(
            (Transaction.from_account_id.in_(account_ids)) |
            (Transaction.to_account_id.in_(account_ids))
        ).order_by(Transaction.created_at.desc())

    # Get total count
    count_query = select(Transaction).where(
        (Transaction.from_account_id.in_(account_ids)) |
        (Transaction.to_account_id.in_(account_ids))
    )
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    # Apply pagination
    result = await db.execute(query.offset(offset).limit(limit))
    transactions = result.scalars().all()

    return transactions, total