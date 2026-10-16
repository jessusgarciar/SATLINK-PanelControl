import asyncio
import csv
import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.bootstrap import check_live as module
from app.bootstrap.check_live import LiveCheckError, check_live, verify_archive
from app.bootstrap.config import Settings
from app.infrastructure.mqtt.picaro import decode_payload
from app.presentation.schemas.uplink import ChirpStackDecoder


@pytest.fixture
def live_data(make_uplink, mission_config):
    topic, payload = make_uplink(time=datetime.now(timezone.utc).isoformat())
    event = ChirpStackDecoder(decode_payload).decode(topic, payload, mission_config["source"])
    sample = {**event.measurements, "id": "sample-1", "missionId": mission_config["id"],
              "receivedAt": event.received_at.isoformat(), "frameCounter": event.frame_counter,
              "relativeAltitudeM": None, "altitudeBarometricM": None, "verticalSpeedMs": None}
    row = {key: "" if value is None else str(value) for key, value in sample.items()
           if not isinstance(value, dict)}
    for group in ("device", "radio"):
        row.update({f"{group}_{key}": "" if value is None else str(value)
                    for key, value in sample[group].items()})
    row.update(source=mission_config["source"], applicationId=mission_config["applicationId"],
               devEui=mission_config["deviceEui"], raw_json=json.dumps(event.raw_event))
    return event, sample, row


def test_archive_correlates_original_event_and_preserves_unknowns(live_data, mission_config):
    event, sample, row = live_data
    assert verify_archive([row], {sample["id"]: sample}, {event.deduplication_id: event}, mission_config) == [sample]
    assert sample["latitude"] is None
    assert row["latitude"] == ""


@pytest.mark.parametrize("field,value", [("batteryV", "4.2"), ("source", "other"),
                                        ("device_gpsFix", "True"), ("missionId", "other")])
def test_archive_rejects_wrong_values_or_provenance(live_data, mission_config, field, value):
    event, sample, row = live_data
    row[field] = value
    with pytest.raises(LiveCheckError):
        verify_archive([row], {sample["id"]: sample}, {event.deduplication_id: event}, mission_config)


def test_archive_detects_duplicate_event(live_data, mission_config):
    event, sample, row = live_data
    with pytest.raises(LiveCheckError, match="duplicado"):
        verify_archive([row, row], {sample["id"]: sample}, {event.deduplication_id: event}, mission_config)


def test_archive_requires_live_websocket_and_unchanged_raw_event(live_data, mission_config):
    event, _, row = live_data
    assert verify_archive([row], {}, {event.deduplication_id: event}, mission_config) == []
    raw = json.loads(row["raw_json"])
    raw["fCnt"] += 1
    row["raw_json"] = json.dumps(raw)
    with pytest.raises(LiveCheckError, match="archivado difiere"):
        verify_archive([row], {}, {event.deduplication_id: event}, mission_config)


@pytest.mark.parametrize("mode", ["valid", "timeout", "incompatible"])
async def test_check_live_end_to_end_and_timeout_cleanup(monkeypatch, live_data, mission_config, mode):
    event, sample, row = live_data
    settings = Settings(database_url="postgresql+psycopg://test@127.0.0.1/test",
                        source=mission_config["source"], mqtt_enabled=True, mqtt_host="mock-broker")
    closed = set()
    ready = asyncio.Event()

    class MQTT:
        def __init__(self, **kwargs):
            assert kwargs["clean_session"] is True
            assert kwargs["identifier"] != settings.mqtt_client_id

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            closed.add("mqtt")

        async def subscribe(self, topic, qos):
            assert topic.endswith("/event/up")

        @property
        async def messages(self):
            await ready.wait()
            if mode != "timeout":
                yield SimpleNamespace(retain=False, topic=module.device_uplink_topic(
                    mission_config["applicationId"], mission_config["deviceEui"]),
                    payload=json.dumps({**event.raw_event, "fPort": 1} if mode == "incompatible" else event.raw_event).encode())
            await asyncio.Future()

    class WebSocket:
        async def __aenter__(self):
            ready.set()
            return self

        async def __aexit__(self, *args):
            closed.add("websocket")

        async def __aiter__(self):
            if mode == "valid":
                yield json.dumps({"type": "telemetry", "data": sample})
            await asyncio.Future()

    snapshot = {"mission": {**mission_config, "phase": "unknown", "beaconOn": None,
                 "updatedAt": event.received_at.isoformat(), "startedAt": None, "endedAt": None},
                "telemetry": [sample], "ingestion": {"source": settings.source, "status": "connected",
                                                "updatedAt": event.received_at.isoformat()}}
    snapshot["mission"].pop("source")
    snapshot["mission"].pop("applicationId")
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    requests = []

    def respond(request):
        requests.append(request.url.path)
        if request.url.path.endswith("export.csv"):
            return httpx.Response(200, content=output.getvalue().encode("utf-8-sig"))
        if request.url.path.endswith("/telemetry"):
            return httpx.Response(200, json={"items": [sample], "nextCursor": None})
        return httpx.Response(200, json=snapshot)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw))
    monkeypatch.setattr(module.aiomqtt, "Client", MQTT)
    monkeypatch.setattr(module, "connect", lambda *a, **kw: WebSocket())
    report = {}
    if mode == "valid":
        result = await check_live(settings, mission_config, samples=1, timeout=2, report=report)
        assert result["status"] == "passed"
        assert result["verifiedSamples"] == 1
        assert result["checks"]["history"] is True
        assert result["checks"]["dashboardRecovery"] is True
        assert any(path.endswith("export.csv") for path in requests)
    elif mode == "timeout":
        with pytest.raises(TimeoutError):
            await check_live(settings, mission_config, samples=1, timeout=0.05, report=report)
        assert report["mqttEvents"] == 0
        assert report["samples"] == []
        assert report["status"] != "passed"
    else:
        with pytest.raises(LiveCheckError, match="incompatible"):
            await check_live(settings, mission_config, samples=1, timeout=2, report=report)
        assert report["lastUplink"] == {"fPort": 1, "payloadBytes": 19}
    assert closed == {"mqtt", "websocket"}


async def test_check_live_refuses_disabled_mqtt(mission_config):
    settings = Settings(database_url="postgresql+psycopg://test@127.0.0.1/test")
    with pytest.raises(LiveCheckError, match="deshabilitado"):
        await check_live(settings, mission_config)
