import asyncio
import json
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import httpx
import pytest
from app.bootstrap.app import create_app
from app.bootstrap.config import Settings

from app.domain.entities.commands import CommandConflict
from app.infrastructure.database.store import PostgresStore
from app.infrastructure.mqtt.commands import CommandProfile, ChirpStackCommands
from app.presentation.schemas.api import MissionConfig

pytestmark = pytest.mark.integration
PREFIX = "/api/v1/missions/test-flight"


class Transport:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    def supports(self, mission):
        return mission["deviceEui"] == "0102030405060708"

    async def send(self, mission, command):
        self.sent.append(command)
        if self.fail:
            raise TimeoutError("synthetic uncertain publish")


def client_for(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1234)),
                            base_url="http://127.0.0.1")


def headers(app, request_id):
    return {"Origin": "http://127.0.0.1:5173", "X-CSRF-Token": app.state.prediction_csrf_token,
            "Idempotency-Key": request_id}


async def test_command_endpoint_idempotency_validation_and_history(store, db_url):
    transport = Transport()
    app = create_app(Settings(database_url=db_url), store, command_transport=transport)
    request_id = str(uuid4())
    async with client_for(app) as client:
        snapshot = (await client.get(PREFIX + "/dashboard")).json()
        assert snapshot["permissions"]["canCommand"] is True
        assert "START_MISSION" in snapshot["commandSettings"]["supportedTypes"]
        assert "RELEASE_NOW" not in snapshot["commandSettings"]["supportedTypes"]
        body = {"type": "PING", "clientRequestId": request_id}
        assert (await client.post(PREFIX + "/commands", json=body)).status_code == 403
        assert (await client.post(PREFIX + "/commands", json=body,
            headers={**headers(app, request_id), "Idempotency-Key": str(uuid4())})).status_code == 422
        responses = await asyncio.gather(*(client.post(PREFIX + "/commands", json=body,
            headers=headers(app, request_id)) for _ in range(5)))
        assert {r.status_code for r in responses} == {202}
        assert len({r.json()["id"] for r in responses}) == 1
        assert len(transport.sent) == 1
        assert all(r.json()["status"] == "pending" for r in responses)
        conflict = await client.post(PREFIX + "/commands", json={**body, "type": "STATUS"}, headers=headers(app, request_id))
        assert conflict.status_code == 409
        for kind in ("BEACON_ON", "RELEASE_NOW", "UNKNOWN"):
            assert (await client.post(PREFIX + "/commands", json={**body, "type": kind}, headers=headers(app, request_id))).status_code == 422
        assert (await client.post("/api/v1/missions/missing/commands", json=body, headers=headers(app, request_id))).status_code == 404
        assert "/api/v1/missions/{mission_id}/commands" in (await client.get("/openapi.json")).json()["paths"]
    restarted = PostgresStore(db_url)
    try:
        commands = (await restarted.dashboard("test-flight"))["commands"]
        assert len(commands) == 1 and commands[0]["simulated"] is False
    finally:
        await restarted.close()


async def test_disabled_transport_returns_503_and_creates_no_fake_commands(store, db_url):
    app = create_app(Settings(database_url=db_url), store)
    async with client_for(app) as client:
        snapshot = (await client.get(PREFIX + "/dashboard")).json()
        assert snapshot["commandSettings"]["enabled"] is False
        assert snapshot["commandSettings"]["supportedTypes"] == []
        request_id = str(uuid4())
        response = await client.post(PREFIX + "/commands", json={"type": "PING", "clientRequestId": request_id},
            headers=headers(app, request_id))
        assert response.status_code == 503
        assert (await store.dashboard("test-flight"))["commands"] == []


async def test_start_requires_recent_sample_and_execution_not_network_ack(store, db_url, make_uplink):
    transport = Transport()
    app = create_app(Settings(database_url=db_url, source="test-chirpstack"), store, command_transport=transport)
    async with client_for(app) as client:
        request_id = str(uuid4())
        body = {"type": "START_MISSION", "clientRequestId": request_id}
        assert (await client.post(PREFIX + "/commands", json=body, headers=headers(app, request_id))).status_code == 409
        await app.state.ingestor.execute(*make_uplink(time=datetime.now(timezone.utc).isoformat()))
        with app.state.hub.subscribe("test-flight") as queue:
            response = await client.post(PREFIX + "/commands", json=body, headers=headers(app, request_id))
            assert response.status_code == 202
            command = response.json()
            assert (await store.dashboard("test-flight"))["mission"]["startedAt"] is None
            # ACK correlacionado por queueItemId, nunca por proximidad temporal.
            profile = CommandProfile("test-flight", "test-app", "0102030405060708", "test-chirpstack", 20,
                {"START_MISSION": "01{requestId}{watchdogSeconds}"})
            adapter = ChirpStackCommands(Settings(database_url=db_url), profile)
            event = {"queueItemId": command["id"], "deviceInfo": {"applicationId": "test-app", "devEui": "0102030405060708"}}
            await adapter.ingest_evidence(adapter.event_topics[1], json.dumps({**event, "acknowledged": True}).encode(), app.state.commander)
            assert (await store.dashboard("test-flight"))["commands"][0]["status"] == "received"
            assert (await store.dashboard("test-flight"))["mission"]["startedAt"] is None
            # Un txack retrasado no degrada received a sent.
            await adapter.ingest_evidence(adapter.event_topics[0], json.dumps(event).encode(), app.state.commander)
            assert (await store.dashboard("test-flight"))["commands"][0]["status"] == "received"
            with pytest.raises(CommandConflict):
                await app.state.commander.update("test-flight", command["id"], "executed", "firmware sin fecha")
            started = datetime.now(timezone.utc)
            await app.state.commander.update("test-flight", command["id"], "executed", "Evidencia SINTÉTICA de firmware", started_at=started)
            mission = (await store.dashboard("test-flight"))["mission"]
            assert datetime.fromisoformat(mission["startedAt"]) == started
            assert mission["phase"] == "unknown"  # iniciar no afirma que haya ascenso
            messages = []
            while not queue.empty():
                messages.append(queue.get_nowait())
            assert any(message["type"] == "mission" and message["data"]["startedAt"] for message in messages)
            assert (await client.post(PREFIX + "/commands", json=body, headers=headers(app, request_id))).json()["id"] == command["id"]
            new_id = str(uuid4())
            assert (await client.post(PREFIX + "/commands", json={**body, "clientRequestId": new_id}, headers=headers(app, new_id))).status_code == 409
            assert (await store.dashboard("test-flight"))["mission"]["startedAt"] == mission["startedAt"]


async def test_uncertain_publish_is_persisted_without_retry_and_foreign_ack_ignored(store, db_url):
    transport = Transport(fail=True)
    app = create_app(Settings(database_url=db_url), store, command_transport=transport)
    mission = (await store.dashboard("test-flight"))["mission"]
    request_id = str(uuid4())
    command = await app.state.commander.execute(mission, request_id, "PING")
    assert "incierto" in command["evidence"]
    assert (await app.state.commander.execute(mission, request_id, "PING"))["id"] == command["id"]
    assert len(transport.sent) == 1
    profile = CommandProfile("test-flight", "test-app", "0102030405060708", "test-chirpstack", 20, {"PING": "01{requestId}"})
    adapter = ChirpStackCommands(Settings(database_url=db_url), profile)
    for device, identifier in (("ffffffffffffffff", command["id"]), ("0102030405060708", str(uuid4()))):
        event = {"queueItemId": identifier, "acknowledged": True, "deviceInfo": {"applicationId": "test-app", "devEui": device}}
        await adapter.ingest_evidence(adapter.event_topics[1], json.dumps(event).encode(), app.state.commander)
    assert (await store.dashboard("test-flight"))["commands"][0]["status"] == "pending"


