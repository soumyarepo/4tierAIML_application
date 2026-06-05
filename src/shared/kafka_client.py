"""Async Kafka producer and consumer wrappers using aiokafka.

Provides graceful startup/shutdown and structured logging for Kafka interactions.
"""

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from typing import Callable, Awaitable, Any
import json
import logging

logger = logging.getLogger(__name__)


class KafkaProducerWrapper:
    """Async Kafka producer with auto-serialization and graceful lifecycle.

    Usage:
        producer = KafkaProducerWrapper(bootstrap_servers="localhost:9092")
        await producer.start()
        await producer.send("topic", {"event": "created", "data": {...}})
        await producer.stop()
    """

    def __init__(
        self,
        bootstrap_servers: str,
        client_id: str | None = None,
        acks: int | str = "all",
    ) -> None:
        """Initialize the producer wrapper.

        Args:
            bootstrap_servers: Comma-separated list of Kafka broker addresses.
            client_id: Optional client identifier for Kafka.
            acks: Acknowledgement level ("all", "-1", "0", or int).
        """
        self.bootstrap_servers = bootstrap_servers
        self.client_id = client_id
        self.acks = acks
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        """Start the underlying AIOKafkaProducer."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            client_id=self.client_id,
            acks=self.acks,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
        )
        await self._producer.start()
        logger.info("kafka_producer_started", bootstrap_servers=self.bootstrap_servers)

    async def stop(self) -> None:
        """Stop and flush the producer gracefully."""
        if self._producer:
            await self._producer.stop()
            logger.info("kafka_producer_stopped")

    async def send(
        self,
        topic: str,
        value: dict[str, Any],
        key: str | None = None,
        headers: list[tuple[str, bytes | None]] | None = None,
    ) -> None:
        """Send a single message to a Kafka topic.

        Args:
            topic: Target Kafka topic name.
            value: Message payload as a dictionary.
            key: Optional message key for partitioning.
            headers: Optional list of (name, value) header tuples.

        Raises:
            RuntimeError: If the producer has not been started.
        """
        if not self._producer:
            raise RuntimeError("KafkaProducerWrapper.start() must be called before sending messages")
        await self._producer.send_and_wait(
            topic,
            value=value,
            key=key,
            headers=headers,
        )
        logger.debug("kafka_message_sent", topic=topic, key=key)

    async def send_batch(self, topic: str, messages: list[dict[str, Any]]) -> None:
        """Send multiple messages to a Kafka topic.

        Args:
            topic: Target Kafka topic name.
            messages: List of message dictionaries.

        Raises:
            RuntimeError: If the producer has not been started.
        """
        if not self._producer:
            raise RuntimeError("KafkaProducerWrapper.start() must be called before sending messages")
        for msg in messages:
            await self._producer.send_and_wait(topic, msg)
        logger.debug("kafka_batch_sent", topic=topic, count=len(messages))


class KafkaConsumerWrapper:
    """Async Kafka consumer with a user-provided message handler and graceful lifecycle.

    Usage:
        async def handler(msg: dict) -> None:
            print(f"Received: {msg}")

        consumer = KafkaConsumerWrapper(
            bootstrap_servers="localhost:9092",
            topics=["transaction.created"],
            group_id="notification-group",
            handler=handler,
        )
        await consumer.start()
        await consumer.consume()  # runs until stop() is called
    """

    def __init__(
        self,
        bootstrap_servers: str,
        topics: list[str],
        group_id: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
        auto_offset_reset: str = "earliest",
        enable_auto_commit: bool = True,
    ) -> None:
        """Initialize the consumer wrapper.

        Args:
            bootstrap_servers: Comma-separated list of Kafka broker addresses.
            topics: List of topics to subscribe to.
            group_id: Consumer group ID for Kafka.
            handler: Async function called for each received message.
            auto_offset_reset: Where to start reading ("earliest" or "latest").
            enable_auto_commit: Whether to auto-commit offsets after each poll.
        """
        self.bootstrap_servers = bootstrap_servers
        self.topics = topics
        self.group_id = group_id
        self.handler = handler
        self.auto_offset_reset = auto_offset_reset
        self.enable_auto_commit = enable_auto_commit
        self._consumer: AIOKafkaConsumer | None = None

    async def start(self) -> None:
        """Start the underlying AIOKafkaConsumer and subscribe to topics."""
        self._consumer = AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            auto_offset_reset=self.auto_offset_reset,
            enable_auto_commit=self.enable_auto_commit,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        )
        await self._consumer.start()
        logger.info(
            "kafka_consumer_started",
            topics=self.topics,
            group_id=self.group_id,
        )

    async def stop(self) -> None:
        """Stop the consumer gracefully."""
        if self._consumer:
            await self._consumer.stop()
            logger.info("kafka_consumer_stopped")

    async def consume(self) -> None:
        """Start consuming messages and call the handler for each.

        Runs until stop() is called or an unhandled exception occurs.

        Raises:
            RuntimeError: If the consumer has not been started.
        """
        if not self._consumer:
            raise RuntimeError("KafkaConsumerWrapper.start() must be called before consuming")

        try:
            async for msg in self._consumer:
                try:
                    await self.handler(msg.value)
                except Exception as exc:
                    logger.error(
                        "kafka_message_handler_error",
                        topic=msg.topic,
                        partition=msg.partition,
                        offset=msg.offset,
                        error=str(exc),
                    )
        finally:
            await self.stop()