import asyncio
import time
from unittest.mock import AsyncMock
import pytest
from httpx import ASGITransport, AsyncClient
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.bootstrap.app import create_app
from app.bootstrap.config import Settings
from app.presentation.websocket.hub import TelemetryHub


async def test_local_access_only():
    store = AsyncMock()
    app = create_app(Settings(database_url="postgresql+psycopg://localhost/unused"), store=store)
    async with AsyncClient(transport=ASGITransport(app=app, client=("192.168.1.20", 54321)), base_url="http://localhost") as client:
        assert (await client.get("/docs")).status_code == 403
    with pytest.raises(ValueError):
        Settings(database_url="postgresql+psycopg://localhost/unused", allowed_origins=("https://evil.example",))


async def test_websocket_heartbeat_and_origin_policy():
    def run_client():
        store = AsyncMock()
        store.dashboard.return_value = {"ingestion": {"source": "chirpstack-local"}}
        app = create_app(Settings(database_url="postgresql+psycopg://localhost/unused"), store=store)
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            with pytest.raises(WebSocketDisconnect) as denied:
                with client.websocket_connect("ws://localhost/api/v1/missions/test/stream", headers={"Origin":"https://evil.example"}):
                    pass
            assert denied.value.code == 1008
            with client.websocket_connect("ws://localhost/api/v1/missions/test/stream") as ws:
                initial = ws.receive_json()
                assert initial["type"] == "ingestion"
                assert initial["data"]["status"] == "disabled"
                start = time.monotonic()
                assert ws.receive_json() == {"type":"heartbeat"}
                assert 19 <= time.monotonic() - start < 30
    await asyncio.to_thread(run_client)


async def test_websocket_reports_broker_status_without_claiming_new_sensor_readings():
    def run_client():
        store = AsyncMock()
        store.dashboard.return_value = {"ingestion": {"source": "test-source"}}
        app = create_app(Settings(database_url="postgresql+psycopg://localhost/unused", source="test-source"), store=store)
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            with client.websocket_connect("ws://localhost/api/v1/missions/test/stream") as ws:
                initial = ws.receive_json()
                assert initial["data"]["source"] == "test-source"
                for status in ("connecting", "connected", "reconnecting", "offline"):
                    client.portal.call(app.state.ingestion.update, status)
                    message = ws.receive_json()
                    assert message["type"] == "ingestion"
                    assert message["data"]["status"] == status
                    assert message["data"]["source"] == "test-source"
                    assert "updatedAt" in message["data"]
                store.persist.assert_not_awaited()
    await asyncio.to_thread(run_client)


async def test_slow_websocket_client_is_disconnected_without_blocking_ingestion():
    hub = TelemetryHub()
    with hub.subscribe("mission") as queue:
        for i in range(257):
            await hub.publish("mission", {"id": str(i)})
        assert await queue.get() is None
    assert not hub.clients
