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
        config.update(telemetryProtocol="radiosonda-v1", altitudeTargetMode="absolute", staleAfterSeconds=900)
        snapshot.update(telemetryProtocol="radiosonda-v1", altitudeTargetMode="absolute", staleAfterSeconds=900)

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
        first = (await client.get("/api/v1/missions/test-flight/packets?limit=3")).json()
        assert len(first["items"]) == 3 and first["nextCursor"]
        second = (await client.get("/api/v1/missions/test-flight/packets",params={"cursor":first["nextCursor"]})).json()
        assert len(second["items"]) == 4
        assert not {p["id"] for p in first["items"]} & {p["id"] for p in second["items"]}
        assert (await client.get("/api/v1/missions/test-flight/packets?cursor=bad")).status_code == 422
        assert (await client.get("/api/v1/missions/missing/packets")).status_code == 404

async def test_rejected_packet_and_duplicate_handling(store, make_uplink):
    await radio_mission(store)
    service = IngestTelemetry(store, TelemetryHub(), "test-chirpstack", ChirpStackDecoder(decode_payload))
    topic, payload = make_uplink(bytes.fromhex("720cbe1f64ffffffffffff"), fPort=21)
    assert await service.execute(topic, payload)
    assert await service.execute(topic, payload) is None
    await service.execute(*make_uplink(b"bad", fPort=21))
    page = await store.packets("test-flight")
    assert len(page["items"]) == 2
    assert page["items"][0]["status"] == "rejected"
    assert page["items"][1]["decoded"]["temperatureC"] == 31.86
    assert len((await store.dashboard("test-flight"))["telemetry"]) == 1

async def test_concurrent_reservation_and_automatic_cut_not_correlated(store, make_uplink):
    await radio_mission(store)
    now = datetime.now(timezone.utc)
    commands = await asyncio.gather(*(store.reserve_command("test-flight", str(uuid4()), "PING", now) for _ in range(2)),return_exceptions=True)
    assert sum(isinstance(c, CommandConflict) for c in commands) == 1
    service = IngestTelemetry(store, TelemetryHub(), "test-chirpstack", ChirpStackDecoder(decode_payload))
    await service.execute(*make_uplink(struct.pack("<BBBBHHhB",2,2,0,1,15000,3300,-100,3),fPort=31,time=now.isoformat()))
    snapshot = await store.dashboard("test-flight")
    assert snapshot["commands"][0]["status"] == "pending"
    assert snapshot["mission"]["flightState"]["motivo"] == "tiempo"


async def test_pending_timeout_is_persisted_and_sequences_never_reused(store):
    await radio_mission(store)
    now = datetime.now(timezone.utc)
    first, _ = await store.reserve_command("test-flight", str(uuid4()), "PING", now - timedelta(minutes=16))
    dashboard = await store.dashboard("test-flight")
    assert dashboard["commands"][0]["status"] == "expired"
    second, _ = await store.reserve_command("test-flight", str(uuid4()), "PING", now)
    assert second["seq"] != first["seq"]

async def test_protocol_upgrade_preserves_identity_and_history(store, make_uplink, mission_config):
    service = IngestTelemetry(store, TelemetryHub(), "test-chirpstack", ChirpStackDecoder(decode_payload))
    await service.execute(*make_uplink())
    previous = await store.dashboard("test-flight")
    await store.initialize_mission({**mission_config, "telemetryProtocol":"radiosonda-v1", "altitudeTargetMode":"absolute", "staleAfterSeconds":900})
    snapshot = await store.dashboard("test-flight")
    assert snapshot["mission"]["deviceEui"] == previous["mission"]["deviceEui"]
    assert snapshot["telemetry"] == previous["telemetry"]
    assert snapshot["mission"]["telemetryProtocol"] == "radiosonda-v1"
