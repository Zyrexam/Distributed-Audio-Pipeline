import json
import logging
import pika
from app.config import get_settings

logger = logging.getLogger(__name__)

class RabbitMQBroker:
    def __init__(
        self,
        host: str | None = None,
        user: str | None = None,
        password: str | None = None,
        queue: str | None = None,
        channel_factory=None,
    ) -> None:
        settings = get_settings()
        self.host = host or settings.rabbitmq_host
        self.user = user or settings.rabbitmq_user
        self.password = password or settings.rabbitmq_password
        self.queue = queue or settings.rabbitmq_queue
        self._channel_factory = channel_factory

    def _open_channel(self):
        if self._channel_factory is not None:
            return self._channel_factory()
        credentials = pika.PlainCredentials(self.user, self.password)
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=self.host, credentials=credentials
            )
        )
        channel = connection.channel()
        channel.queue_declare(queue=self.queue, durable=True)
        return channel

    def publish_message(self, message: dict) -> None:
        channel = self._open_channel()
        try:
            channel.basic_publish(
                exchange="",
                routing_key=self.queue,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE
                ),
            )
            logger.info("Published message to %s", self.queue)
        finally:
            channel.connection.close()
