"""Configuration management using Pydantic Settings v2.

Loads settings from environment variables with sensible defaults.
All settings can be overridden via .env file or environment variables.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Any


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Attributes:
        DATABASE_URL: Async PostgreSQL connection URL for SQLAlchemy.
        REDIS_URL: Redis connection URL for caching and rate limiting.
        KAFKA_BOOTSTRAP_SERVERS: Kafka broker address (comma-separated for multiple).
        MONGO_URL: MongoDB connection URL for audit logging.
        JWT_SECRET: Secret key for signing JWT tokens (HS256).
        JWT_ALGORITHM: Algorithm for JWT signing (default HS256).
        JWT_ACCESS_TOKEN_EXPIRE_MINUTES: Access token lifetime in minutes.
        JWT_REFRESH_TOKEN_EXPIRE_DAYS: Refresh token lifetime in days.
        SERVICE_NAME: Name of this microservice for logging/metrics.
        DEBUG: Enable debug mode for verbose logging.
        POSTGRES_HOST: PostgreSQL host address.
        POSTGRES_PORT: PostgreSQL port number.
        POSTGRES_USER: PostgreSQL username.
        POSTGRES_PASSWORD: PostgreSQL password.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://bankuser:bankpass@localhost:5432/bank_auth"
    MONGO_URL: str = "mongodb://mongo:27017"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"

    # Auth
    JWT_SECRET: str = "change-me-in-production-use-strong-secret"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Service
    SERVICE_NAME: str = "banking-service"
    DEBUG: bool = False

    # PostgreSQL (individual connection params)
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "bankuser"
    POSTGRES_PASSWORD: str = "bankpass"

    def get_bank_auth_db_url(self) -> str:
        """Return the PostgreSQL URL for the bank_auth database."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/bank_auth"
        )

    def get_bank_accounts_db_url(self) -> str:
        """Return the PostgreSQL URL for the bank_accounts database."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/bank_accounts"
        )

    def get_bank_transactions_db_url(self) -> str:
        """Return the PostgreSQL URL for the bank_transactions database."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/bank_transactions"
        )


# Global settings instance — import this in all services
settings = Settings()