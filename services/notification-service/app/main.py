"""FastAPI application for the Notification Service (Tier 2b – Event-Driven)."""

import asyncio
import signal
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from aiokafka import AIOKafkaConsumer
import json

from shared.logging_config import configure_logging, get_logger
from shared.metrics import setup_metrics

# ---------------------------------------------------------------------------
# Application settings (environment-driven)
# ---------------------------------------------------------------------------

KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
CONSUMER_GROUP_ID = "banking-notification-group"
TOPICS = ["transaction.created", "transaction.completed", "transaction.flagged"]
MAX_HISTORY = 100

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------


@dataclass
class ProcessedMessage:
    """Lightweight record of a consumed Kafka message for the status endpoint."""

    topic: str
    event_type: str
    user_id: str
    transaction_id: str
    timestamp: datetime
    raw: dict

    @classmethod
    def from_payload(cls, topic: str, payload: dict) -> "ProcessedMessage":
        return cls(
            topic=topic,
            event_type=payload.get("event_type") or payload.get("eventType") or topic,
            user_id=str(payload.get("user_id") or payload.get("userId") or "unknown"),
            transaction_id=str(
                payload.get("transaction_id") or payload.get("transactionId") or "unknown"
            ),
            timestamp=datetime.now(timezone.utc),
            raw=payload,
        )


# Thread-safe deque of last N processed messages
_message_history: deque[ProcessedMessage] = deque(maxlen=MAX_HISTORY)
_consumer_task: asyncio.Task | None = None
_consumer: AIOKafkaConsumer | None = None
_shutdown_event: asyncio.Event = asyncio.Event()
_logger: "structlog.BoundLogger | None" = None


# ---------------------------------------------------------------------------
# Kafka consumer logic (async, runs in background)
# ---------------------------------------------------------------------------

def _notification_body(topic: str, payload: dict) -> str:
    """Build the simulated notification text for a given topic/payload."""
    amount = payload.get("amount")
    templates = {
        "transaction.created": f"Transaction initiated: ${float(amount):,.2f}" if amount else "Transaction initiated",
        "transaction.completed": f"Transaction completed: ${float(amount):,.2f}" if amount else "Transaction completed",
        "transaction.flagged": "ALERT: Suspicious transaction flagged!",
    }
    return templates.get(topic, templates.get(payload.get("event_type", ""), "Notification"))


async def _consume_loop() -> None:
    """Background task that consumes Kafka messages and simulates notifications."""
    global _consumer, _logger

    _logger.info(
        "kafka_consumer_starting",
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=CONSUMER_GROUP_ID,
        topics=TOPICS,
    )

    _consumer = AIOKafkaConsumer(
        *TOPICS,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=CONSUMER_GROUP_ID,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )
    await _consumer.start()
    _logger.info("kafka_consumer_started")

    try:
        async for msg in _consumer:
            if _shutdown_event.is_set():
                break

            topic = msg.topic
            payload: dict = msg.value

            # Record in history
            processed = ProcessedMessage.from_payload(topic, payload)
            _message_history.append(processed)

            # Structured log of received event
            _logger.info(
                "kafka_event_received",
                topic=topic,
                partition=msg.partition,
                offset=msg.offset,
                user_id=processed.user_id,
                transaction_id=processed.transaction_id,
            )

            # Simulate sending the notification
            notification = _notification_body(topic, payload)
            _logger.info(
                "notification_sent",
                topic=topic,
                user_id=processed.user_id,
                transaction_id=processed.transaction_id,
                notification_body=notification,
            )
    except asyncio.CancelledError:
        _logger.info("kafka_consumer_cancelled")
    finally:
        if _consumer:
            await _consumer.stop()
            _logger.info("kafka_consumer_stopped")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start Kafka consumer on startup, stop it on shutdown."""
    global _consumer_task, _shutdown_event, _logger

    configure_logging(service_name="notification-service")
    _logger = get_logger("notification-service")
    _logger.info("notification_service_starting")

    _shutdown_event.clear()

    # Launch consumer as a detached background task
    _consumer_task = asyncio.create_task(_consume_loop())
    _logger.info("notification_service_ready")

    yield

    # Graceful shutdown
    _logger.info("notification_service_shutting_down")
    _shutdown_event.set()

    if _consumer_task:
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass
    _logger.info("notification_service_stopped")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Notification Service",
    description="Event-driven microservice that consumes Kafka events and sends notifications.",
    version="1.0.0",
    lifespan=lifespan,
)

setup_metrics(app)


# ---------------------------------------------------------------------------
# Schemas / DTOs
# ---------------------------------------------------------------------------


class ConsumerStatusResponse(BaseModel):
    """Status response for the notification consumer."""

    status: str = "running"  # or "stopped"
    consumer_group: str
    topics: list[str]
    messages_processed: int
    last_100_messages: list[dict]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """Liveness probe for Kubernetes."""
    return {"status": "healthy", "service": "notification-service"}


@app.get(
    "/api/v1/notifications/status",
    response_model=ConsumerStatusResponse,
    tags=["notifications"],
    summary="Show consumer status and recent processed messages",
)
async def get_status() -> ConsumerStatusResponse:
    """Return the current consumer status, topic offsets, and the last 100 messages."""
    status_str = "running" if _consumer_task and not _consumer_task.done() else "stopped"

    last_messages = [
        {
            "topic": m.topic,
            "event_type": m.event_type,
            "user_id": m.user_id,
            "transaction_id": m.transaction_id,
            "timestamp": m.timestamp.isoformat(),
        }
        for m in _message_history
    ]

    return ConsumerStatusResponse(
        status=status_str,
        consumer_group=CONSUMER_GROUP_ID,
        topics=TOPICS,
        messages_processed=len(_message_history),
        last_100_messages=last_messages,
    )