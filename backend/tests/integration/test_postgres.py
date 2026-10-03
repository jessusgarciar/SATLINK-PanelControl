import asyncio
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, insert, select
from fastapi.testclient import TestClient
from app.application.use_cases.ingest import IngestTelemetry
from app.bootstrap.app import create_app
from app.bootstrap.config import Settings
from app.domain.entities.telemetry import ConfigurationConflict
from app.infrastructure.database.models import ReceivedEventRow, TelemetryRow
from app.infrastructure.database.store import PostgresStore
from app.infrastructure.mqtt.picaro import decode_payload
from app.presentation.schemas.uplink import ChirpStackDecoder

pytestmark = pytest.mark.integration


def ingestion(store, publisher=None):
    return IngestTelemetry(store, publisher or AsyncMock(), "test-chirpstack", ChirpStackDecoder(decode_payload))


async def test_commit_visible_to_other_connection_before_publication_and_duplicate_restart(store, db_url, make_uplink):
    published = []
    class Publisher:
        async def publish(self, mission_id, data):
            other = PostgresStore(db_url)
            try:
                snap = await other.dashboard(mission_id)
                assert any(t["id"] == data["id"] for t in snap["telemetry"])
                published.append(data)
            finally:
                await other.close()
    service = ingestion(store, Publisher())
    message = make_uplink()
    results = await asyncio.gather(*(service.execute(*message) for _ in range(6)))
    assert len([r for r in results if r is not None]) == len(published) == 1
    restarted = PostgresStore(db_url)
    try:
        assert await ingestion(restarted).execute(*message) is None
        assert len((await restarted.dashboard("test-flight"))["telemetry"]) == 1
    finally:
        await restarted.close()
    # Contador reutilizado con otro ID de evento representa otra muestra.
    assert await service.execute(*make_uplink(fCnt=1)) is not None
    assert len((await store.dashboard("test-flight"))["telemetry"]) == 2


async def test_failed_publication_preserves_data_and_rejections_are_stored(store, make_uplink):
    publisher = AsyncMock()
    publisher.publish.side_effect = RuntimeError("browser disconnected")
    row = await ingestion(store, publisher).execute(*make_uplink())
    assert (await store.dashboard("test-flight"))["telemetry"][0]["id"] == row["id"]
    assert row["relativeAltitudeM"] is None
    assert await ingestion(store).execute(*make_uplink(data="bad")) is None
    async with store.sessions() as session:
        rejects = await session.scalar(select(func.count()).select_from(ReceivedEventRow).where(ReceivedEventRow.status == "rejected"))
        assert rejects == 1


async def test_database_rollback_removes_event_and_never_publishes(store, make_uplink):
    publisher = AsyncMock()
    def fail_insert(*args):
        raise RuntimeError("synthetic failure while inserting telemetry")
    event.listen(TelemetryRow, "before_insert", fail_insert)
    try:
        with pytest.raises(RuntimeError):
            await ingestion(store, publisher).execute(*make_uplink())
    finally:
        event.remove(TelemetryRow, "before_insert", fail_insert)
    publisher.publish.assert_not_awaited()
    async with store.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ReceivedEventRow)) == 0
        assert await session.scalar(select(func.count()).select_from(TelemetryRow)) == 0


async def test_mission_initialization_is_idempotent_and_origin_immutable(store, mission_config):
    first = await store.initialize_mission(mission_config)
    second = await store.initialize_mission(mission_config)
    assert first == second
    changed = {**mission_config, "launch": {**mission_config["launch"], "altitudeM": 2000}}
    with pytest.raises(ConfigurationConflict):
        await store.initialize_mission(changed)
    assert (await store.dashboard("test-flight"))["mission"]["launch"]["altitudeM"] == 1870
    with pytest.raises(ConfigurationConflict):
        await store.initialize_mission({**mission_config, "id": "other-flight"})


async def test_history_over_1200_order_filters_scope_and_pagination(store, mission_config, make_uplink):
    base = await ingestion(store).execute(*make_uplink())
    now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
    events, telemetry = [], []
    for index in range(1205):
        identifier = str(uuid4())
        time = now + timedelta(seconds=index // 3 + 1)
        data = {**base, "id": identifier, "receivedAt": time.isoformat(), "frameCounter": index}
        events.append(dict(id=identifier, source="test-chirpstack", mission_id="test-flight",
                           dev_eui=mission_config["deviceEui"], deduplication_id=str(uuid4()),
                           received_at=time, ingested_at=now, status="accepted", reason=None,
                           raw_payload=b"SYNTHETIC ARCHIVE FIXTURE", details={"synthetic": True}))
        telemetry.append(dict(id=identifier, mission_id="test-flight", received_at=time, data=data))
    async with store.sessions.begin() as session:
        await session.execute(insert(ReceivedEventRow), events)
        await session.execute(insert(TelemetryRow), telemetry)
    assert len((await store.dashboard("test-flight"))["telemetry"]) == 1200
    found, cursor = [], None
    while True:
        page = await store.history("test-flight", cursor=cursor, limit=113)
        found.extend(page["items"])
        cursor = page["nextCursor"]
        if cursor is None:
            break
    assert len(found) == len({t["id"] for t in found}) == 1206
    assert [(t["receivedAt"], t["id"]) for t in found[1:]] == sorted((t["receivedAt"], t["id"]) for t in found[1:])
    assert len((await store.history("test-flight", now, now + timedelta(seconds=1)))["items"]) == 1
    another = {**mission_config, "id": "empty", "deviceEui": "1111111111111111"}
    await store.initialize_mission(another)
    assert (await store.history("empty"))["items"] == []
    cursor = (await store.history("test-flight", limit=1))["nextCursor"]
    with pytest.raises(ValueError):
        await store.history("empty", cursor=cursor)
    with pytest.raises(ValueError):
        await store.history("test-flight", from_time=now, cursor=cursor)


async def test_http_contract_and_typescript_parsers(store, db_url, make_uplink):
    app = create_app(Settings(database_url=db_url, source="test-chirpstack"), store=store)
    data = await app.state.ingestor.execute(*make_uplink())
    transport = ASGITransport(app=app, client=("127.0.0.1", 50000))
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.get("/api/v1/missions/test-flight/dashboard")
        assert response.status_code == 200
        snapshot = response.json()
        assert snapshot["permissions"] == {"canCommand": False, "canPredict": False}
        page = await client.get("/api/v1/missions/test-flight/telemetry")
        assert page.status_code == 200
        for url in ("telemetry?limit=0", "telemetry?limit=1201", "telemetry?cursor=bad", "telemetry?from=2026-10-02", "telemetry?from=2026-10-03T00:00:00Z&to=2026-10-02T00:00:00Z"):
            assert (await client.get("/api/v1/missions/test-flight/" + url)).status_code == 422
        assert (await client.get("/api/v1/missions/missing/dashboard")).status_code == 404
        assert (await client.post("/api/v1/missions/test-flight/commands", json={})).status_code == 404
        assert (await client.get("/docs")).status_code == 200
        assert "/api/v1/missions/{mission_id}/telemetry" in (await client.get("/openapi.json")).json()["paths"]
        assert (await client.get("/docs", headers={"Origin": "https://evil.example"})).status_code == 403
        assert (await client.get("/docs", headers={"Host": "evil.example"})).status_code == 403
    node = shutil.which("node")
    assert node, "Node requerido para validar el contrato real TypeScript"
    script = Path(__file__).resolve().parents[3] / "frontend/tests/validate-backend.mjs"
    result = await asyncio.to_thread(subprocess.run, [node, "--experimental-strip-types", str(script)],
        input=json.dumps({"snapshot": snapshot, "history": page.json(), "stream": {"type": "telemetry", "data": data}}),
        text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr


async def test_websocket_end_to_end_and_reconnect(store, db_url, make_uplink):
    def run_client():
        app = create_app(Settings(database_url=db_url, source="test-chirpstack"))
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000),
                        backend_options={"loop_factory": asyncio.SelectorEventLoop}) as client:
            with client.websocket_connect("ws://localhost/api/v1/missions/test-flight/stream", headers={"Origin":"http://localhost:5173"}) as ws:
                data = client.portal.call(app.state.ingestor.execute, *make_uplink())
                message = ws.receive_json()
                assert message == {"type": "telemetry", "data": data}
            for _ in range(10):
                with client.websocket_connect("ws://localhost/api/v1/missions/test-flight/stream"):
                    assert client.get("/api/v1/missions/test-flight/dashboard").json()["telemetry"][0]["id"] == data["id"]
    await asyncio.to_thread(run_client)
