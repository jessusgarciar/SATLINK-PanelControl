import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiomqtt
import pytest

from app.infrastructure.mqtt import consumer


async def test_broker_backoff_is_bounded_and_status_tracks_subscription_and_shutdown(monkeypatch):
    attempts, delays, statuses, subscriptions = [], [], [], []

    class Client:
        def __init__(self, **kwargs):
            attempts.append(kwargs)

        async def __aenter__(self):
            if len(attempts) <= 7:
                raise aiomqtt.MqttError("synthetic broker outage")
            return self

        async def __aexit__(self, *args):
            pass

        async def subscribe(self, topic, qos):
            subscriptions.append((topic, qos))

        @property
        def messages(self):
            async def stream():
                raise asyncio.CancelledError
                yield
            return stream()

    async def sleep(seconds):
        delays.append(seconds)

    async def on_status(status):
        if status == "connected":
            assert subscriptions == [("application/+/device/+/event/up", 1)]
        statuses.append(status)

    monkeypatch.setattr(consumer.aiomqtt, "Client", Client)
    monkeypatch.setattr(consumer, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await consumer.consume("fake-broker", 1883, None, None, False, "test-id", AsyncMock(), on_status)
    assert delays == [1, 2, 4, 8, 16, 30, 30]
    assert statuses[0] == "connecting"
    assert "reconnecting" in statuses
    assert statuses[-2:] == ["connected", "offline"]
    assert len(attempts) == 8


async def test_shutdown_during_database_retry_cancels_without_skipping_to_next_uplink(monkeypatch):
    delivered, statuses = [], []
    closed = asyncio.Event()

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            closed.set()

        async def subscribe(self, topic, qos):
            pass

        @property
        def messages(self):
            async def stream():
                yield SimpleNamespace(topic="first", payload=b"first")
                yield SimpleNamespace(topic="second", payload=b"second")
            return stream()

    async def ingest(topic, payload):
        delivered.append((topic, payload))
        raise RuntimeError("synthetic database outage")

    async def sleep(seconds):
        raise asyncio.CancelledError

    async def on_status(status):
        statuses.append(status)

    monkeypatch.setattr(consumer.aiomqtt, "Client", Client)
    monkeypatch.setattr(consumer, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await consumer.consume("fake-broker", 1883, None, None, False, "test-id", ingest, on_status)
    assert delivered == [("first", b"first")]
    assert closed.is_set()
    assert statuses[-1] == "offline"


async def test_cancellation_during_broker_backoff_marks_ingestion_offline(monkeypatch):
    statuses = []

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            raise aiomqtt.MqttError("synthetic disconnected broker")

        async def __aexit__(self, *args):
            pass

    async def sleep(seconds):
        raise asyncio.CancelledError

    async def on_status(status):
        statuses.append(status)

    monkeypatch.setattr(consumer.aiomqtt, "Client", Client)
    monkeypatch.setattr(consumer, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await consumer.consume("fake-broker", 1883, None, None, False, "test-id", AsyncMock(), on_status)
    assert statuses == ["connecting", "reconnecting", "offline"]
