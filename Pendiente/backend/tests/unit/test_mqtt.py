import asyncio
import logging
import ssl
from types import SimpleNamespace
from unittest.mock import AsyncMock
import aiomqtt
import pytest
from app.infrastructure.mqtt import consumer

TOPIC = "application/test-app/device/0102030405060708/event/up"


def test_exact_uplink_topic_is_built_from_mission_identifiers():
    assert consumer.device_uplink_topic("test-app", "0102030405060708") == TOPIC


async def test_mqtt_reconnects_and_retries_database_failure_without_skipping_message(monkeypatch):
    connections, delivered, delays, subscriptions, removals = [], [], [], [], []
    class Client:
        def __init__(self, **kwargs):
            connections.append(kwargs)
        async def __aenter__(self):
            if len(connections) == 1:
                raise aiomqtt.MqttError("synthetic disconnect")
            return self
        async def __aexit__(self, *args):
            pass
        async def unsubscribe(self, topic):
            removals.append(topic)
        async def subscribe(self, topic, qos):
            subscriptions.append((topic, qos))
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
        await consumer.consume("test-broker", 1883, None, None, False, "test-id", TOPIC, ingest)
    assert len(connections) == 2
    assert delivered == [("synthetic/topic", b"synthetic")] * 2
    assert delays == [1, 1]
    assert removals == [consumer.LEGACY_UPLINK_TOPIC]
    assert subscriptions == [(TOPIC, 1)]
    assert all(connection["clean_session"] is False for connection in connections)


async def test_tls_uses_system_ca_and_verifies_server_hostname(monkeypatch):
    connections = []

    class Client:
        def __init__(self, **kwargs):
            connections.append(kwargs)
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def unsubscribe(self, topic):
            pass
        async def subscribe(self, topic, qos):
            pass
        @property
        def messages(self):
            async def stream():
                raise asyncio.CancelledError
                yield
            return stream()

    monkeypatch.setattr(consumer.aiomqtt, "Client", Client)
    with pytest.raises(asyncio.CancelledError):
        await consumer.consume("tls-broker", 8883, "user", "password", True,
                               "test-id", TOPIC, AsyncMock())
    context = connections[0]["tls_context"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert connections[0]["username"] == "user"
    assert connections[0]["password"] == "password"


async def test_connection_failure_log_redacts_credentials(monkeypatch, caplog):
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            raise aiomqtt.MqttError("refused for test-user with super-secret")
        async def __aexit__(self, *args):
            pass

    async def stop_after_failure(seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(consumer.aiomqtt, "Client", Client)
    monkeypatch.setattr(consumer, "sleep", stop_after_failure)
    with caplog.at_level(logging.WARNING, logger=consumer.__name__):
        with pytest.raises(asyncio.CancelledError):
            await consumer.consume("test-broker", 8883, "test-user", "super-secret",
                                   True, "test-id", TOPIC, AsyncMock())
    assert "Fallo MQTT en connection" in caplog.text
    assert "[redacted]" in caplog.text
    assert "test-user" not in caplog.text
    assert "super-secret" not in caplog.text
