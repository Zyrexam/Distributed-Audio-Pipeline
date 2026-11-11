"""Infrastructure client tests: MinIO, RabbitMQ and metrics.

Every external service is faked, so these run without Docker.
"""

import json

import pytest

from app.infrastructure.broker import RabbitMQBroker
from app.infrastructure.metrics import metrics
from app.infrastructure.storage import MinIOStorage


# --------------------------------------------------------------------------- #
# MinIO
# --------------------------------------------------------------------------- #


class FakeObjectResponse:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.closed = False
        self.released = False

    def read(self) -> bytes:
        return self.data

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class FakeMinio:
    def __init__(self, bucket_exists: bool = False) -> None:
        self.exists = bucket_exists
        self.created_buckets = []
        self.puts = []
        self.response = FakeObjectResponse(b"audio-bytes")
        self.deleted = []

    def bucket_exists(self, bucket: str) -> bool:
        return self.exists

    def make_bucket(self, bucket: str) -> None:
        self.created_buckets.append(bucket)

    def put_object(self, bucket_name, object_name, data, length, content_type):
        self.puts.append((bucket_name, object_name, data.read(), length, content_type))

    def get_object(self, bucket: str, object_key: str):
        return self.response

    def remove_object(self, bucket: str, object_key: str) -> None:
        self.deleted.append((bucket, object_key))


def make_storage(fake: FakeMinio, bucket: str = "raw-audio") -> MinIOStorage:
    return MinIOStorage(bucket=bucket, client=fake)


def test_ensure_bucket_exists_creates_missing_bucket():
    fake = FakeMinio(bucket_exists=False)

    make_storage(fake).ensure_bucket_exists()

    assert fake.created_buckets == ["raw-audio"]


def test_ensure_bucket_exists_keeps_existing_bucket():
    fake = FakeMinio(bucket_exists=True)

    make_storage(fake).ensure_bucket_exists()

    assert fake.created_buckets == []


def test_upload_bytes_sends_data_with_length():
    fake = FakeMinio()

    make_storage(fake).upload_bytes("uploads/a.wav", b"12345", "audio/wav")

    assert fake.puts == [
        ("raw-audio", "uploads/a.wav", b"12345", 5, "audio/wav")
    ]


def test_download_bytes_returns_data_and_releases_connection():
    fake = FakeMinio()

    data = make_storage(fake).download_bytes("uploads/a.wav")

    assert data == b"audio-bytes"
    assert fake.response.closed
    assert fake.response.released


def test_delete_object_removes_key_from_bucket():
    fake = FakeMinio()

    make_storage(fake).delete_object("uploads/a.wav")

    assert fake.deleted == [("raw-audio", "uploads/a.wav")]


# --------------------------------------------------------------------------- #
# RabbitMQ
# --------------------------------------------------------------------------- #


class FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeChannel:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.published = []
        self.connection = FakeConnection()

    def basic_publish(self, exchange, routing_key, body, properties):
        if self.error is not None:
            raise self.error
        self.published.append((exchange, routing_key, body, properties))


def make_broker(channel: FakeChannel) -> RabbitMQBroker:
    return RabbitMQBroker(
        queue="audio.jobs", channel_factory=lambda: channel
    )


def test_publish_message_sends_json_to_queue():
    channel = FakeChannel()

    make_broker(channel).publish_message({"job_id": "abc", "attempt": 0})

    exchange, routing_key, body, properties = channel.published[0]
    assert exchange == ""
    assert routing_key == "audio.jobs"
    assert json.loads(body) == {"job_id": "abc", "attempt": 0}
    assert properties.delivery_mode == 2


def test_publish_message_closes_connection():
    channel = FakeChannel()

    make_broker(channel).publish_message({"job_id": "abc"})

    assert channel.connection.closed


def test_publish_message_closes_connection_on_failure():
    channel = FakeChannel(error=RuntimeError("broker down"))

    with pytest.raises(RuntimeError, match="broker down"):
        make_broker(channel).publish_message({"job_id": "abc"})

    assert channel.connection.closed


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #


def test_counters_and_histograms_record():
    uploads_before = metrics.uploads_total._value.get()

    metrics.record_upload()

    assert metrics.uploads_total._value.get() == uploads_before + 1
    assert metrics.upload_seconds._sum.get() >= 0
    assert metrics.job_processing_seconds._sum.get() >= 0
