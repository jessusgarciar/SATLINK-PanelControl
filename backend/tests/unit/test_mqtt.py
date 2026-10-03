import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import aiomqtt
import pytest
from app.infrastructure.mqtt import consumer


async def test_mqtt_reconnects_and_retries_database_failure_without_skipping_message(monkeypatch):
    connections, delivered, delays = [], [], []
    class Client:
        def __init__(self, **kwargs):
            connections.append(kwargs)
        async def __aenter__(self):
            if len(connections) == 1:
                raise aiomqtt.MqttError("synthetic disconnect")
            return self
        async def __aexit__(self, *args):
            pass
        async def subscribe(self, topic, qos):
            assert topic == "application/+/device/+/event/up" and qos == 1
        @property
        def messages(self):
            async def stream():
                yield SimpleNamespace(topic="synthetic/topic", payload=b"synthetic")
                raise asyncio.CancelledError
            return stream()
    async def ingest(topic, payload):
        delivered.append((topic, payload))
        if len(delivered) == 1:
            raise RuntimeError("database temporarily unavailable")
    async def sleep(seconds):
        delays.append(seconds)
    monkeypatch.setattr(consumer.aiomqtt, "Client", Client)
    monkeypatch.setattr(consumer, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await consumer.consume("test-broker", 1883, None, None, False, "test-id", ingest)
    assert len(connections) == 2
    assert delivered == [("synthetic/topic", b"synthetic")] * 2
    assert delays == [1, 1]
