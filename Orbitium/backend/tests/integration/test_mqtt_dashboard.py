import asyncio
import csv
import io
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.app import create_app
from app.bootstrap.config import Settings
from app.infrastructure.database.models import ReceivedEventRow
from app.infrastructure.database.store import PostgresStore
from app.infrastructure.mqtt import consumer


pytestmark = pytest.mark.integration


async def test_mqtt_uplink_reaches_committed_database_websocket_and_full_http_exports(store, db_url, make_uplink, monkeypatch):
    topic, payload = make_uplink(dr=3, txInfo={"frequency": 902300000},
                                note='Entrada SINTÉTICA, "áéíóú"')
    raw_event = json.loads(payload)
    attempts, subscriptions, published = [], [], []

    class FakeClient:
        def __init__(self, **kwargs):
            attempts.append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def subscribe(self, subscribed_topic, qos):
            subscriptions.append((subscribed_topic, qos))

        @property
        def messages(self):
            async def stream():
                # La red puede repetir la misma entrega QoS 1; el UUID de evento es idéntico.
                yield SimpleNamespace(topic=topic, payload=payload)
                yield SimpleNamespace(topic=topic, payload=payload)
                raise asyncio.CancelledError
            return stream()

    monkeypatch.setattr(consumer.aiomqtt, "Client", FakeClient)

    def run_client():
        app = create_app(Settings(database_url=db_url, source="test-chirpstack"))

        class CommittedPublisher:
            async def publish(self, mission_id, data):
                observer = PostgresStore(db_url)
                try:
                    snapshot = await observer.dashboard(mission_id)
                    assert snapshot["telemetry"] == [data]
                    async with observer.sessions() as session:
                        event = await session.get(ReceivedEventRow, data["id"])
                        assert event.status == "accepted"
                        assert event.raw_payload == payload
                        assert event.details["event"] == raw_event
                    published.append(data)
                finally:
                    await observer.close()
                await app.state.hub.publish(mission_id, data)

        app.state.ingestor.publisher = CommittedPublisher()

        async def consume_fixture():
            try:
                await consumer.consume("synthetic-broker", 1883, None, None, False,
                    "synthetic-client", app.state.ingestor.execute, app.state.ingestion.update)
            except asyncio.CancelledError:
                return "cancelled"
            pytest.fail("El consumidor debe propagar cancelación al terminar el flujo sintético")

        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000),
                        backend_options={"loop_factory": asyncio.SelectorEventLoop}) as client:
            with client.websocket_connect("ws://localhost/api/v1/missions/test-flight/stream") as ws:
                assert ws.receive_json()["data"]["status"] == "disabled"
                assert client.portal.call(consume_fixture) == "cancelled"
                messages = []
                for _ in range(4):
                    messages.append(ws.receive_json())
                assert [message["data"]["status"] for message in messages if message["type"] == "ingestion"] == [
                    "connecting", "connected", "offline"]
                telemetry = [message["data"] for message in messages if message["type"] == "telemetry"]
                assert telemetry == published
                assert len(telemetry) == 1
                sample = telemetry[0]
                assert sample["temperatureC"] == 26.12
                assert sample["radio"] == {"gatewayId": "strong", "frequencyHz": 902300000,
                                            "dataRate": 3, "fPort": 10}
                snapshot = client.get("/api/v1/missions/test-flight/dashboard").json()
                window = client.get("/api/v1/missions/test-flight/telemetry/window").json()
                history = client.get("/api/v1/missions/test-flight/telemetry").json()
                assert snapshot["telemetry"] == history["items"] == window["series"] == [sample]
                assert snapshot["ingestion"]["status"] == "offline"
                assert window["total"] == 1 and window["track"] == []
                response = client.get("/api/v1/missions/test-flight/telemetry/export.csv")
                assert response.status_code == 200
                rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
                assert len(rows) == 1
                assert rows[0]["id"] == sample["id"]
                assert rows[0]["temperatureC"] == "26.12"
                assert rows[0]["source"] == "test-chirpstack"
                assert rows[0]["applicationId"] == "test-app"
                assert rows[0]["devEui"] == "0102030405060708"
                assert json.loads(rows[0]["raw_json"]) == raw_event

    await asyncio.to_thread(run_client)
    assert len(attempts) == 1
    assert subscriptions == [("application/+/device/+/event/up", 1)]
    assert attempts[0]["hostname"] == "synthetic-broker"
    assert attempts[0]["clean_session"] is False
