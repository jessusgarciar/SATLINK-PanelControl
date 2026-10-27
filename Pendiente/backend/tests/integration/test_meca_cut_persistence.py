import asyncio
import struct
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import httpx
import pytest
from app.application.use_cases.ingest import IngestTelemetry
from app.infrastructure.mqtt.picaro import decode_payload
from app.presentation.schemas.uplink import ChirpStackDecoder
from app.presentation.websocket.hub import TelemetryHub
from app.infrastructure.database.store import PostgresStore
from app.bootstrap.app import create_app
from app.bootstrap.config import Settings
from app.domain.entities.commands import CommandConflict

pytestmark = pytest.mark.integration

async def radio_mission(store):
    async with store.edit_mission("test-flight") as (config, snapshot):
        config.update(telemetryProtocol="radiosonda-meca-v1", altitudeTargetMode="absolute", staleAfterSeconds=1200)
        snapshot.update(telemetryProtocol="radiosonda-meca-v1", altitudeTargetMode="absolute", staleAfterSeconds=1200)

async def test_interleaved_feedback_packets_persistence_and_history(store, make_uplink, db_url):
    await radio_mission(store)
    hub = TelemetryHub()
    service = IngestTelemetry(store, hub, "test-chirpstack", ChirpStackDecoder(decode_payload))
    now = datetime.now(timezone.utc)
    ping, _ = await store.reserve_command("test-flight", str(uuid4()), "PING", now)
    async def ingest(port, payload, count):
        return await service.execute(*make_uplink(payload, fPort=port, fCnt=count, time=(now + timedelta(seconds=count)).isoformat()))
    await ingest(20, struct.pack("<iiHB", 210000000, -1020000000, 40000, 9), 1)
    await ingest(30, struct.pack("<Bhb", ping["seq"], -64, 44), 2)
    await ingest(21, bytes.fromhex("720cbe1f64ffffffffffff"), 3)
    cut, _ = await store.reserve_command("test-flight", str(uuid4()), "RELEASE_NOW", now + timedelta(seconds=4))
    await ingest(31, struct.pack("<BBBBHHhB", 1, 4, cut["seq"], 0, 40000, 100, 32767, 3), 4)
    await ingest(22, bytes.fromhex("ff7fffffff7fffffff0100"), 5)
    await ingest(31, struct.pack("<BBBBHHhB", 3, 4, cut["seq"], 3, 40000, 160, 32767, 3), 6)
    await ingest(23, bytes.fromhex("ff7fffffffffffff7f0051"), 7)
    dashboard = await store.dashboard("test-flight")
    assert len(dashboard["telemetry"]) == 4
    by_kind = {c["type"]: c for c in dashboard["commands"]}
    assert by_kind["PING"]["status"] == "executed"
    assert by_kind["PING"]["result"]["rttSeconds"] == 2
    assert by_kind["RELEASE_NOW"]["result"]["evento"] == "sin_confirmar"
    assert dashboard["mission"]["flightState"]["cutResult"] == "sin_confirmar"
    assert dashboard["mission"]["startedAt"] is None
    assert (await store.prediction_context("test-flight"))["telemetry"]["altitudeGpsM"] == 40000
    second = PostgresStore(db_url)
    try:
        next_command, _ = await second.reserve_command("test-flight", str(uuid4()), "PING", now + timedelta(seconds=8))
        assert next_command["seq"] not in (ping["seq"], cut["seq"])
    finally: await second.close()
    app = create_app(Settings(database_url=db_url), store)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=("127.0.0.1",1)),base_url="http://127.0.0.1") as client:
        response = await client.get("/api/v1/missions/test-flight/dashboard")
        assert response.status_code == 200
        assert next(c for c in response.json()["commands"] if c["type"] == "RELEASE_NOW")["result"]["evento"] == "sin_confirmar"
        first = (await client.get("/api/v1/missions/test-flight/packets?limit=3")).json()
        assert len(first["items"]) == 3 and first["nextCursor"]
        second = (await client.get("/api/v1/missions/test-flight/packets",params={"cursor":first["nextCursor"]})).json()
        assert len(second["items"]) == 4
        assert not {p["id"] for p in first["items"]} & {p["id"] for p in second["items"]}
        assert (await client.get("/api/v1/missions/test-flight/packets?cursor=bad")).status_code == 422
        assert (await client.get("/api/v1/missions/missing/packets")).status_code == 404


async def test_cut_api_idempotency_csrf_and_firmware_feedback(store, make_uplink, db_url):
    from unittest.mock import AsyncMock
    await radio_mission(store)
    now = datetime.now(timezone.utc)
    service = IngestTelemetry(store, TelemetryHub(), "test-chirpstack", ChirpStackDecoder(decode_payload))
    transport = AsyncMock()
    transport.supports = lambda mission: True
    app = create_app(Settings(database_url=db_url), store, command_transport=transport)
    endpoint = "/api/v1/missions/test-flight/commands"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        snapshot = (await client.get("/api/v1/missions/test-flight/dashboard")).json()
        request = str(uuid4())
        body = {"type": "RELEASE_NOW", "clientRequestId": request}
        headers = {"Origin": "http://127.0.0.1:5173", "X-CSRF-Token": snapshot["csrfToken"], "Idempotency-Key": request}
        assert (await client.post(endpoint, json=body)).status_code == 403
        assert (await client.post(endpoint, json=body, headers=headers)).status_code == 409
        await service.execute(*make_uplink(bytes(11), fPort=21, time=now.isoformat()))
        response = await client.post(endpoint, json=body, headers=headers)
        assert response.status_code == 202
        command = response.json()
        assert (await client.post(endpoint, json=body, headers=headers)).json()["id"] == command["id"]
        transport.send.assert_awaited_once()
        async def cut(event, reason, seq, offset):
            await service.execute(*make_uplink(struct.pack("<BBBBHHhB", event, reason, seq, 1, 15000, 100, -100, 3),
                fPort=31, time=(now + timedelta(seconds=offset)).isoformat()))
        await cut(2, 1, command["seq"], 2)  # automatic event cannot acknowledge an operator request
        assert (await store.dashboard("test-flight"))["commands"][0]["status"] == "pending"
        await cut(1, 4, command["seq"], 3)
        assert (await store.dashboard("test-flight"))["commands"][0]["status"] == "received"
        await cut(2, 4, command["seq"], 4)
        response = await client.get("/api/v1/missions/test-flight/dashboard")
        assert response.status_code == 200
        completed = response.json()["commands"][0]
        assert completed["status"] == "executed" and completed["result"]["evento"] == "confirmado"
        assert response.json()["mission"]["startedAt"] is None
