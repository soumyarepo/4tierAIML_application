"""Common exception classes and FastAPI exception handlers.

Provides a hierarchy of banking-specific exceptions with
standardized error codes, plus helpers to register handlers with FastAPI.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Any


class BankingException(Exception):
    """Base exception for all banking-related errors.

    All service-specific exceptions should inherit from this class.

    Attributes:
        message: Human-readable error description.
        code: Machine-readable error code string.
        details: Optional dict of additional context (e.g. field violations).
    """

    def __init__(
        self,
        message: str,
        code: str = "BANKING_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)


class NotFoundError(BankingException):
    """Raised when a requested resource (account, user, transaction) is not found."""

    def __init__(self, message: str = "Resource not found", details: dict[str, Any] | None = None) -> None:
        super().__init__(message=message, code="NOT_FOUND", details=details)


class ValidationError(BankingException):
    """Raised when input data fails validation (schema, business rules)."""

    def __init__(self, message: str = "Validation failed", details: dict[str, Any] | None = None) -> None:
        super().__init__(message=message, code="VALIDATION_ERROR", details=details)


class AuthenticationError(BankingException):
    """Raised when authentication fails (invalid credentials, expired token)."""

    def __init__(self, message: str = "Authentication failed", details: dict[str, Any] | None = None) -> None:
        super().__init__(message=message, code="AUTHENTICATION_ERROR", details=details)


class InsufficientFundsError(BankingException):
    """Raised when an account has insufficient funds for a transaction."""

    def __init__(
        self,
        message: str = "Insufficient funds",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code="INSUFFICIENT_FUNDS", details=details)


class AccountFrozenError(BankingException):
    """Raised when attempting operations on a frozen account."""

    def __init__(
        self,
        message: str = "Account is frozen",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code="ACCOUNT_FROZEN", details=details)


class DuplicateResourceError(BankingException):
    """Raised when attempting to create a resource that already exists."""

    def __init__(
        self,
        message: str = "Resource already exists",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code="DUPLICATE_RESOURCE", details=details)


# -------------------------------------------------------------------
# Error Response Model
# -------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """Standardized error response body returned by all API error handlers.

    Attributes:
        code: Machine-readable error code (e.g. NOT_FOUND, VALIDATION_ERROR).
        message: Human-readable description of the error.
        request_id: Unique identifier of the request (from X-Request-ID header).
        details: Optional additional context (field errors, etc.).
    """

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    request_id: str | None = Field(None, description="Request tracking ID")
    details: dict[str, Any] | None = Field(None, description="Additional error context")


# -------------------------------------------------------------------
# FastAPI Exception Handlers
# -------------------------------------------------------------------


async def banking_exception_handler(request: Request, exc: BankingException) -> JSONResponse:
    """Handle any BankingException and return a standardized JSON error response."""
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=_code_to_http_status(exc.code),
        content=ErrorResponse(
            code=exc.code,
            message=exc.message,
            request_id=request_id,
            details=exc.details,
        ).model_dump(exclude_none=True),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle uncaught exceptions with a generic INTERNAL_ERROR response."""
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            request_id=request_id,
        ).model_dump(exclude_none=True),
    )


def _code_to_http_status(code: str) -> int:
    """Map BankingException codes to HTTP status codes."""
    mapping = {
        "NOT_FOUND": 404,
        "VALIDATION_ERROR": 422,
        "AUTHENTICATION_ERROR": 401,
        "INSUFFICIENT_FUNDS": 400,
        "ACCOUNT_FROZEN": 403,
        "DUPLICATE_RESOURCE": 409,
        "BANKING_ERROR": 400,
    }
    return mapping.get(code, 400)


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on a FastAPI application.

    Args:
        app: FastAPI application instance.
    """
    app.add_exception_handler(BankingException, banking_exception_handler)
    # Optionally catch all other exceptions in development
    app.add_exception_handler(Exception, generic_exception_handler)