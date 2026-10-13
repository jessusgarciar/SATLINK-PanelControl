import csv
import io
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert, select

from app.application.use_cases.ingest import IngestTelemetry
from app.bootstrap.app import create_app
from app.bootstrap.config import Settings
from app.infrastructure.database.models import ReceivedEventRow, TelemetryRow
from app.infrastructure.mqtt.picaro import decode_payload
from app.presentation.schemas.uplink import ChirpStackDecoder, utc_time


pytestmark = pytest.mark.integration
START = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
PREFIX = "/api/v1/missions/test-flight"
NOTE = 'Sonda SINTÉTICA, "áéíóú"\nsegunda línea'


def client_for(store, db_url):
    app = create_app(Settings(database_url=db_url, source="test-chirpstack"), store=store)
    return app, AsyncClient(transport=ASGITransport(app=app, client=("127.0.0.1", 54321)),
                            base_url="http://localhost")


async def synthetic_archive(store, mission_config, make_uplink, count):
    service = IngestTelemetry(store, AsyncMock(), "test-chirpstack", ChirpStackDecoder(decode_payload))
    base = await service.execute(*make_uplink())
    identifiers, events, samples = [], [], []
    for index in range(count):
        identifier = str(uuid4())
        identifiers.append(identifier)
        received = START + timedelta(seconds=index + 1)
        gps = index > 0
        data = {**base, "id": identifier, "receivedAt": received.isoformat(), "frameCounter": index + 2,
                "latitude": 21.0 if gps else None, "longitude": -102.0 if gps else None,
                "altitudeGpsM": 1870 if gps else None, "relativeAltitudeM": 0 if gps else None}
        raw_event = {"synthetic": True, "note": NOTE, "index": index}
        events.append(dict(id=identifier, source="test-chirpstack", mission_id="test-flight",
            dev_eui=mission_config["deviceEui"], deduplication_id=str(uuid4()),
            received_at=received, ingested_at=START, status="accepted", reason=None,
            raw_payload=json.dumps(raw_event, ensure_ascii=False).encode("utf-8"),
            details={"event": raw_event, "codec": {}, "provenance": "synthetic-test"}))
        samples.append(dict(id=identifier, mission_id="test-flight", received_at=received, data=data))
    async with store.sessions.begin() as session:
        await session.execute(insert(ReceivedEventRow), events)
        await session.execute(insert(TelemetryRow), samples)
    return base, identifiers


async def test_window_counts_complete_range_and_bounds_series_and_valid_gps_track(store, db_url, mission_config, make_uplink):
    base, identifiers = await synthetic_archive(store, mission_config, make_uplink, 1305)
    _, client = client_for(store, db_url)
    async with client:
        response = await client.get(PREFIX + "/telemetry/window", params={
            "from": START.isoformat(), "to": (START + timedelta(seconds=1400)).isoformat()})
        assert response.status_code == 200
        window = response.json()
        assert window["total"] == 1306
        assert len(window["series"]) == 600
        assert len(window["track"]) == 500
        assert window["series"][0]["id"] == base["id"]
        assert window["series"][-1]["id"] == identifiers[-1]
        assert window["track"][0]["id"] == identifiers[1]
        assert window["track"][-1]["id"] == identifiers[-1]
        for key in ("series", "track"):
            rows = window[key]
            assert len({row["id"] for row in rows}) == len(rows)
            assert [utc_time(row["receivedAt"]) for row in rows] == sorted(utc_time(row["receivedAt"]) for row in rows)
        assert all(row["latitude"] is not None and row["longitude"] is not None for row in window["track"])
        # El snapshot y la ventana tienen límites distintos; exportar debe conservar todo.
        assert len((await client.get(PREFIX + "/dashboard")).json()["telemetry"]) == 1200


async def test_window_from_inclusive_to_exclusive_and_default_cutoff_are_consistent(store, db_url, mission_config, make_uplink):
    _, identifiers = await synthetic_archive(store, mission_config, make_uplink, 5)
    _, client = client_for(store, db_url)
    async with client:
        response = await client.get(PREFIX + "/telemetry/window", params={
            "from": (START + timedelta(seconds=2)).isoformat(),
            "to": (START + timedelta(seconds=4)).isoformat()})
        window = response.json()
        assert window["total"] == 2
        assert [row["id"] for row in window["series"]] == identifiers[1:3]
        before = datetime.now(timezone.utc)
        default = (await client.get(PREFIX + "/telemetry/window")).json()
        after = datetime.now(timezone.utc)
        assert default["from"] is None
        assert before <= utc_time(default["to"]) <= after
        assert default["total"] == 6
        empty_config = {**mission_config, "id": "empty", "deviceEui": "1111111111111111"}
        await store.initialize_mission(empty_config)
        empty = (await client.get("/api/v1/missions/empty/telemetry/window")).json()
        assert empty["total"] == 0
        assert empty["series"] == empty["track"] == []


@pytest.mark.parametrize("endpoint", ["window", "export.csv"])
async def test_archive_endpoints_reject_bad_ranges_and_missing_missions(store, db_url, endpoint):
    _, client = client_for(store, db_url)
    async with client:
        for params in ({"from": "2026-10-02"}, {"to": "2026-10-02T12:00:00"},
                       {"from": "2026-10-03T00:00:00Z", "to": "2026-10-02T00:00:00Z"},
                       {"from": "2026-10-02T00:00:00Z", "to": "2026-10-02T00:00:00Z"}):
            assert (await client.get(PREFIX + "/telemetry/" + endpoint, params=params)).status_code == 422
        assert (await client.get("/api/v1/missions/missing/telemetry/" + endpoint)).status_code == 404


async def test_csv_exports_full_archive_raw_json_and_nulls_with_utf8_quoting(store, db_url, mission_config, make_uplink):
    base, identifiers = await synthetic_archive(store, mission_config, make_uplink, 1305)
    _, client = client_for(store, db_url)
    async with client:
        response = await client.get(PREFIX + "/telemetry/export.csv", params={
            "to": (START + timedelta(seconds=1400)).isoformat()})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
        assert len(rows) == len({row["id"] for row in rows}) == 1306
        assert rows[0]["id"] == base["id"] and rows[-1]["id"] == identifiers[-1]
        assert rows[0]["latitude"] == rows[0]["longitude"] == ""
        assert rows[0]["humidityPct"] == rows[0]["verticalSpeedMs"] == ""
        assert rows[0]["radio_fPort"] == "10"
        assert rows[-1]["source"] == "test-chirpstack"
        assert rows[0]["applicationId"] == "test-app"
        assert rows[0]["devEui"] == mission_config["deviceEui"]
        assert json.loads(rows[-1]["raw_json"]) == {"synthetic": True, "note": NOTE, "index": 1304}
        filtered = await client.get(PREFIX + "/telemetry/export.csv", params={
            "from": (START + timedelta(seconds=2)).isoformat(),
            "to": (START + timedelta(seconds=4)).isoformat()})
        selected = list(csv.DictReader(io.StringIO(filtered.content.decode("utf-8-sig"))))
        assert [row["id"] for row in selected] == identifiers[1:3]


async def test_legacy_samples_recover_metadata_from_raw_event_without_rewriting_storage(store, db_url, make_uplink):
    service = IngestTelemetry(store, AsyncMock(), "test-chirpstack", ChirpStackDecoder(decode_payload))
    sample = await service.execute(*make_uplink(dr=2, txInfo={"frequency": 902300000}))
    async with store.sessions.begin() as session:
        legacy = await session.get(TelemetryRow, sample["id"])
        legacy.data = {key: value for key, value in legacy.data.items() if key not in ("device", "radio")}
    _, client = client_for(store, db_url)
    async with client:
        dashboard = (await client.get(PREFIX + "/dashboard")).json()
        history = (await client.get(PREFIX + "/telemetry")).json()
        window = (await client.get(PREFIX + "/telemetry/window")).json()
        for recovered in (dashboard["telemetry"][0], history["items"][0], window["series"][0]):
            assert recovered["device"]["usbPowered"] is True
            assert recovered["device"]["gpsFix"] is False
            assert recovered["radio"] == {"gatewayId": "strong", "frequencyHz": 902300000, "dataRate": 2, "fPort": 10}
        assert dashboard["ingestion"]["status"] == "disabled"
        assert dashboard["permissions"] == {"canCommand": False, "canPredict": False}
    async with store.sessions() as session:
        saved = await session.scalar(select(TelemetryRow.data).where(TelemetryRow.id == sample["id"]))
        assert "device" not in saved and "radio" not in saved


async def test_legacy_csv_without_raw_event_keeps_raw_json_empty(store, db_url, make_uplink):
    service = IngestTelemetry(store, AsyncMock(), "test-chirpstack", ChirpStackDecoder(decode_payload))
    sample = await service.execute(*make_uplink())
    async with store.sessions.begin() as session:
        event = await session.get(ReceivedEventRow, sample["id"])
        event.details = {"codec": event.details["codec"]}
    _, client = client_for(store, db_url)
    async with client:
        response = await client.get(PREFIX + "/telemetry/export.csv")
        assert response.status_code == 200
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
        assert len(rows) == 1
        assert rows[0]["raw_json"] == ""
        assert rows[0]["source"] == "test-chirpstack"
        assert rows[0]["applicationId"] == "test-app"
