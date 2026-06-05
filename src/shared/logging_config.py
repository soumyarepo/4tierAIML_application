"""structlog configuration for JSON-structured logging.

Configures structlog to output machine-parseable JSON in production
and human-readable console output in debug mode.
"""

import logging
import sys
import structlog
from structlog.types import Processor


def configure_logging(
    debug: bool = False,
    service_name: str = "banking-service",
    log_level: int = logging.INFO,
) -> None:
    """Configure structlog processors and logger factory for the application.

    Call this once at application startup, before any log calls are made.

    Args:
        debug: If True, use console output instead of JSON. Defaults to False.
        service_name: Value added to all log entries as the "service" field.
        log_level: Minimum log level (default INFO).
    """
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if debug:
        # Human-readable format for local development
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
        logger_factory = structlog.make_filtering_bound_logger(logging.DEBUG)
    else:
        # JSON output for production log aggregation
        processors.append(structlog.processors.JSONRenderer())
        logger_factory = structlog.make_filtering_bound_logger(log_level)

    structlog.configure(
        processors=processors,
        wrapper_class=logger_factory,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Ensure standard library loggers also route to structlog
    # so that libraries (sqlalchemy, httpx, etc.) produce structured output
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Get a structlog logger bound with the service name and any provided name.

    Args:
        name: Optional sub-component name (e.g. "kafka", "auth").

    Returns:
        Configured structlog BoundLogger.
    """
    base = structlog.get_logger()
    if name:
        return base.bind(component=name)
    return base