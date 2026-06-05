"""Async Kafka consumer for the Notification Service.

Consumes events from transaction topics and simulates sending notifications.
"""

from typing import Any

import structlog

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Notification templates
# ---------------------------------------------------------------------------

_NOTIFICATION_TEMPLATES: dict[str, str] = {
    "transaction.created": "Transaction initiated: ${amount}",
    "transaction.completed": "Transaction completed: ${amount}",
    "transaction.flagged": "ALERT: Suspicious transaction flagged!",
}


def _format_amount(amount: Any) -> str:
    """Safely format an amount field for display."""
    try:
        return f"{float(amount):,.2f}"
    except (TypeError, ValueError):
        return str(amount)


# ---------------------------------------------------------------------------
# Message handler
# ---------------------------------------------------------------------------

async def handle_kafka_message(msg: dict[str, Any], topic: str) -> None:
    """Process a single Kafka message and simulate sending a notification.

    Args:
        msg: Deserialised message payload.
        topic: Kafka topic the message was consumed from.
    """
    user_id = msg.get("user_id") or msg.get("userId") or "unknown"
    transaction_id = msg.get("transaction_id") or msg.get("transactionId") or "unknown"
    event_type = msg.get("event_type") or msg.get("eventType") or topic
    amount = msg.get("amount")

    # Structured log of the raw event (the "received" side)
    logger.info(
        "kafka_event_received",
        topic=topic,
        user_id=user_id,
        transaction_id=transaction_id,
        event_type=event_type,
        amount=amount,
    )

    # Build and "send" the notification (simulation — logs only)
    template = _NOTIFICATION_TEMPLATES.get(topic, _NOTIFICATION_TEMPLATES.get(event_type, ""))
    if "{amount}" in template and amount is not None:
        body = template.replace("{amount}", _format_amount(amount))
    else:
        body = template

    logger.info(
        "notification_sent",
        topic=topic,
        user_id=user_id,
        transaction_id=transaction_id,
        notification_body=body,
    )