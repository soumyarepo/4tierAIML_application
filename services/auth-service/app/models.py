"""SQLAlchemy 2.0 async models for the Auth Service.

Defines the User and RefreshToken tables stored in the bank_auth database.
"""

import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, ForeignKey, Index, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from typing import TYPE_CHECKING

import sys
sys.path.insert(0, "/mnt/c/Users/LENOVO/Desktop/New folder/parket-ai/src")
from shared.database import Base

if TYPE_CHECKING:
    pass


class UserRole(str, enum.Enum):
    """Enumeration of user roles for RBAC."""

    CUSTOMER = "customer"
    ADMIN = "admin"
    AGENT = "agent"


class User(Base):
    """Represents a bank customer or staff member.

    Attributes:
        id: UUID primary key.
        email: Unique email address used for login.
        full_name: Display name of the user.
        password_hash: Bcrypt hash of the user's password.
        role: User's role for RBAC (customer, admin, agent).
        is_active: Whether the account is active (False = suspended).
        created_at: Timestamp when the account was created.
        updated_at: Timestamp of the last update to the account.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"),
        nullable=False,
        default=UserRole.CUSTOMER,
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
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
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_users_email_lower", func.lower("email")),
    )


class RefreshToken(Base):
    """Stores opaque refresh tokens for JWT rotation.

    The token value itself is not stored — only its bcrypt hash.
    This allows revocation without needing the original token value.

    Attributes:
        id: UUID primary key.
        user_id: Foreign key to the owning user.
        token_hash: Bcrypt hash of the opaque refresh token (UUID).
        expires_at: When this refresh token expires.
        created_at: Timestamp when the token was issued.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")