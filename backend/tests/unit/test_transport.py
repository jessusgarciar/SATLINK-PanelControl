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
        app = create_app(Settings(database_url="postgresql+psycopg://localhost/unused"), store=store)
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            with pytest.raises(WebSocketDisconnect) as denied:
                with client.websocket_connect("ws://localhost/api/v1/missions/test/stream", headers={"Origin":"https://evil.example"}):
                    pass
            assert denied.value.code == 1008
            with client.websocket_connect("ws://localhost/api/v1/missions/test/stream") as ws:
                start = time.monotonic()
                assert ws.receive_json() == {"type":"heartbeat"}
                assert 19 <= time.monotonic() - start < 30
    await asyncio.to_thread(run_client)


async def test_slow_websocket_client_is_disconnected_without_blocking_ingestion():
    hub = TelemetryHub()
    with hub.subscribe("mission") as queue:
        for i in range(257):
            await hub.publish("mission", {"id": str(i)})
        assert await queue.get() is None
    assert not hub.clients
