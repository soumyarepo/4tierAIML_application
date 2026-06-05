"""Banking Shared Library.

Re-exports commonly used components from submodules.
"""

from shared.config import Settings
from shared.database import Base, get_db_session, create_async_engine, create_async_session_factory
from shared.exceptions import (
    BankingException,
    NotFoundError,
    ValidationError,
    AuthenticationError,
    InsufficientFundsError,
    register_exception_handlers,
    ErrorResponse,
)
from shared.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_token,
)
from shared.logging_config import configure_logging
from shared.kafka_client import KafkaProducerWrapper, KafkaConsumerWrapper
from shared.metrics import (
    REQUEST_COUNT,
    REQUEST_LATENCY,
    decorate_fastapi_route,
    increment_request_count,
    observe_request_latency,
)

__all__ = [
    "Settings",
    "Base",
    "get_db_session",
    "create_async_engine",
    "create_async_session_factory",
    "BankingException",
    "NotFoundError",
    "ValidationError",
    "AuthenticationError",
    "InsufficientFundsError",
    "register_exception_handlers",
    "ErrorResponse",
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "verify_token",
    "configure_logging",
    "KafkaProducerWrapper",
    "KafkaConsumerWrapper",
    "REQUEST_COUNT",
    "REQUEST_LATENCY",
    "decorate_fastapi_route",
    "increment_request_count",
    "observe_request_latency",
]