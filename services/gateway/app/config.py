"""Gateway-specific Pydantic settings for the API Gateway service.

Loads upstream service URLs, rate limit config, and JWT validation secret
from environment variables.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Gateway settings loaded from environment variables.

    Attributes:
        AUTH_SERVICE_URL: Base URL of the auth service.
        ACCOUNT_SERVICE_URL: Base URL of the account service.
        TRANSACTION_SERVICE_URL: Base URL of the transaction service.
        AI_SERVICE_URL: Base URL of the AI/fraud service.
        NOTIFICATION_SERVICE_URL: Base URL of the notification service.
        JWT_SECRET: Secret key for validating JWT tokens (HS256).
        JWT_ALGORITHM: Algorithm for JWT verification (default HS256).
        RATE_LIMIT_REQUESTS: Max requests per window (default 100).
        RATE_LIMIT_WINDOW_SECONDS: Sliding window size in seconds (default 60).
        REDIS_URL: Redis connection URL for rate limiting.
        UPSTREAM_TIMEOUT_SECONDS: Timeout for upstream service requests.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # Upstream service URLs
    AUTH_SERVICE_URL: str = Field(
        default="http://auth-service:8001",
        description="Auth service base URL",
    )
    ACCOUNT_SERVICE_URL: str = Field(
        default="http://account-service:8002",
        description="Account service base URL",
    )
    TRANSACTION_SERVICE_URL: str = Field(
        default="http://transaction-service:8003",
        description="Transaction service base URL",
    )
    AI_SERVICE_URL: str = Field(
        default="http://fraud-service:8004",
        description="AI/Fraud service base URL",
    )
    NOTIFICATION_SERVICE_URL: str = Field(
        default="http://notification-service:8005",
        description="Notification service base URL",
    )

    # JWT validation
    JWT_SECRET: str = Field(
        default="change-me-in-production-use-strong-secret",
        description="Secret key for JWT signature validation",
    )
    JWT_ALGORITHM: str = Field(
        default="HS256",
        description="JWT algorithm for signature verification",
    )

    # Rate limiting
    RATE_LIMIT_REQUESTS: int = Field(
        default=100,
        description="Maximum requests per rate limit window",
    )
    RATE_LIMIT_WINDOW_SECONDS: int = Field(
        default=60,
        description="Sliding window size in seconds",
    )

    # Redis
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )

    # Upstream timeout
    UPSTREAM_TIMEOUT_SECONDS: int = Field(
        default=30,
        description="Timeout for upstream service HTTP requests",
    )


# Global settings instance
settings = Settings()