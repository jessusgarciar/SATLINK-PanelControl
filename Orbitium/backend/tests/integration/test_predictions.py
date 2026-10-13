"""Local integration with synthetic Tawhiri results, never flight evidence."""
import asyncio
import struct
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi.testclient import TestClient

from app.bootstrap.app import create_app
from app.bootstrap.config import Settings
from app.application.use_cases.predict import normalize_prediction
from app.domain.entities.prediction import PredictionTimeout, PredictionUnavailable
from app.infrastructure.database.models import MissionRow
from app.infrastructure.database.store import PostgresStore


pytestmark = pytest.mark.integration
PREFIX = "/api/v1/missions/test-flight"
REFERENCES = {"test-flight": {"launchAltitudeReference": "MSL", "gpsAltitudeReference": "MSL"}}


def planned_request(**changes):
    return {"mode": "planned", "launchDatetime": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "targetRelativeAltitudeM": 15000, "ascentRateMs": 5, "descentRateMs": 6.5, **changes}


def synthetic_tawhiri(request):
    start = datetime.fromisoformat(request["launch_datetime"].replace("Z", "+00:00"))
    def point(seconds, altitude, latitude, longitude):
        return {"datetime": (start + timedelta(seconds=seconds)).isoformat(), "altitude": altitude,
                "latitude": latitude, "longitude": longitude}
    return {"request": {**deepcopy(request), "dataset": "2026100318"},
            "prediction": [
                {"stage": "ascent", "trajectory": [
                    point(0, request["launch_altitude"], request["launch_latitude"], request["launch_longitude"]),
                    point(3000, request["burst_altitude"], 21.1, 258.1)]},
                {"stage": "descent", "trajectory": [
                    point(3000, request["burst_altitude"], 21.1, 258.1),
                    point(5600, 1600, 21.2, 258.2)]}]}


def synthetic_provider():
    provider = AsyncMock()
    provider.predict.side_effect = synthetic_tawhiri
    return provider


def app_and_client(store, db_url, provider, *, enabled=True, references=None, publisher=None):
    settings = Settings(database_url=db_url, source="test-chirpstack", prediction_enabled=enabled,
                        prediction_references=REFERENCES if references is None else references)
    app = create_app(settings, store=store, publisher=publisher, prediction_provider=provider)
    client = AsyncClient(transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
                         base_url="http://localhost")
    return app, client


def authorized(app):
    return {"Origin": "http://localhost:5173", "X-CSRF-Token": app.state.prediction_csrf_token}


async def test_planned_prediction_commits_before_publication_and_survives_restart(store, db_url):
    provider = synthetic_provider()
    publisher = AsyncMock()
    observed = []
    async def published(mission_id, prediction):
        other = PostgresStore(db_url)
        try:
            persisted = await other.latest_prediction(mission_id)
            assert persisted == prediction
            observed.append({"type": "prediction", "data": prediction})
        finally:
            await other.close()
    publisher.publish_prediction.side_effect = published
    app, client = app_and_client(store, db_url, provider, publisher=publisher)
    request = planned_request()
    async with client:
        response = await client.post(PREFIX + "/predictions", json=request, headers=authorized(app))
        assert response.status_code == 200, response.text
        prediction = response.json()
        assert prediction["source"] == "tawhiri"
        assert prediction["missionId"] == "test-flight"
        assert prediction["context"]["mode"] == "planned"
        assert prediction["context"]["origin"] == {"latitude": 21.0, "longitude": -102.0, "altitudeM": 1870.0}
        assert prediction["context"]["telemetryId"] is None
        assert prediction["context"]["altitudeReference"] == "MSL"
        assert prediction["parameters"] == request
        assert prediction["release"]["altitudeM"] == 16870
        assert prediction["landing"]["longitude"] == pytest.approx(-101.8)
        sent = provider.predict.await_args.args[0]
        assert sent["launch_longitude"] == 258
        assert sent["launch_altitude"] == 1870
        assert sent["burst_altitude"] == 16870
        assert sent["profile"] == "standard_profile"
        assert len(observed) == 1 and observed[0] == {"type": "prediction", "data": prediction}
        dashboard = (await client.get(PREFIX + "/dashboard")).json()
        assert dashboard["prediction"] == prediction
        assert dashboard["mission"]["phase"] == "unknown"
        assert dashboard["permissions"]["canCommand"] is False
        assert dashboard["predictionSettings"]["nextAllowedAt"] is not None
    restarted = PostgresStore(db_url)
    try:
        _, client = app_and_client(restarted, db_url, synthetic_provider())
        async with client:
            assert (await client.get(PREFIX + "/dashboard")).json()["prediction"] == prediction
    finally:
        await restarted.close()


@pytest.mark.parametrize("headers", [{}, {"Origin": "http://localhost:5173"},
                                      {"Origin": "http://localhost:5173", "X-CSRF-Token": "wrong"},
                                      {"Origin": "https://evil.example", "X-CSRF-Token": "wrong"}])
async def test_prediction_rejects_missing_or_untrusted_authorization(store, db_url, headers):
    provider = synthetic_provider()
    _, client = app_and_client(store, db_url, provider)
    async with client:
        response = await client.post(PREFIX + "/predictions", json=planned_request(), headers=headers)
        assert response.status_code == 403
    provider.predict.assert_not_awaited()


async def test_prediction_disabled_does_not_contact_provider(store, db_url):
    provider = synthetic_provider()
    app, client = app_and_client(store, db_url, provider, enabled=False)
    async with client:
        response = await client.post(PREFIX + "/predictions", json=planned_request(), headers=authorized(app))
        assert response.status_code == 403
    provider.predict.assert_not_awaited()


@pytest.mark.parametrize("changes", [{"targetRelativeAltitudeM": 15001}, {"ascentRateMs": 0},
                                      {"descentRateMs": 16}, {"launchDatetime": "2026-10-03T12:00:00"},
                                      {"launchDatetime": None}, {"mode": "unsupported"},
                                      {"ascentWindMs": 8}, {"ascentRateMs": True}])
async def test_invalid_prediction_inputs_never_contact_provider(store, db_url, changes):
    provider = synthetic_provider()
    app, client = app_and_client(store, db_url, provider)
    async with client:
        assert (await client.post(PREFIX + "/predictions", json=planned_request(**changes),
                                  headers=authorized(app))).status_code == 422
    provider.predict.assert_not_awaited()


async def test_unconfigured_altitude_reference_and_missing_mission_are_rejected(store, db_url):
    provider = synthetic_provider()
    app, client = app_and_client(store, db_url, provider, references={})
    async with client:
        assert (await client.post(PREFIX + "/predictions", json=planned_request(), headers=authorized(app))).status_code == 422
        assert (await client.post("/api/v1/missions/missing/predictions", json=planned_request(),
                                  headers=authorized(app))).status_code == 404
    provider.predict.assert_not_awaited()


async def test_concurrent_prediction_is_limited_and_does_not_block_ingestion(store, db_url, make_uplink):
    entered, release = asyncio.Event(), asyncio.Event()
    provider = synthetic_provider()
    async def waiting(request):
        entered.set()
        await release.wait()
        return synthetic_tawhiri(request)
    provider.predict.side_effect = waiting
    app, client = app_and_client(store, db_url, provider)
    async with client:
        pending = asyncio.create_task(client.post(PREFIX + "/predictions", json=planned_request(), headers=authorized(app)))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            second = await asyncio.wait_for(client.post(PREFIX + "/predictions", json=planned_request(), headers=authorized(app)), 5)
            assert second.status_code == 429
            assert 1 <= int(second.headers["Retry-After"]) <= 60
            data = await asyncio.wait_for(app.state.ingestor.execute(*make_uplink()), 5)
            assert data["missionId"] == "test-flight"
            assert (await client.get(PREFIX + "/dashboard")).json()["telemetry"][0]["id"] == data["id"]
        finally:
            release.set()
            response = await asyncio.wait_for(pending, 5)
        assert response.status_code == 200, response.text
    assert provider.predict.await_count == 1


async def test_ascending_requires_fresh_gps_and_disallows_planned_datetime(store, db_url):
    provider = synthetic_provider()
    app, client = app_and_client(store, db_url, provider)
    request = {"mode": "ascending", "targetRelativeAltitudeM": 15000, "ascentRateMs": 5, "descentRateMs": 6.5}
    async with client:
        assert (await client.post(PREFIX + "/predictions", json=request, headers=authorized(app))).status_code == 422
        assert (await client.post(PREFIX + "/predictions", json={**request, "launchDatetime": planned_request()["launchDatetime"]},
                                  headers=authorized(app))).status_code == 422
    provider.predict.assert_not_awaited()


@pytest.mark.parametrize("age_seconds,altitude,gps_reference,status", [
    (0, 3000, "MSL", 200), (300, 3000, "MSL", 422), (0, 16870, "MSL", 422),
    (0, 3000, "unknown", 422)])
async def test_ascending_uses_current_gps_but_target_stays_relative_to_launch(
        store, db_url, make_uplink, age_seconds, altitude, gps_reference, status):
    references = {"test-flight": {"launchAltitudeReference": "MSL", "gpsAltitudeReference": gps_reference}}
    provider = synthetic_provider()
    app, client = app_and_client(store, db_url, provider, references=references)
    payload = struct.pack(">BiihBHBhH", 1, 21_000_000, -102_000_000, altitude, 8, 4000, 90, 2000, 10000)
    sample_time = (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).isoformat()
    telemetry = await app.state.ingestor.execute(*make_uplink(payload, time=sample_time))
    request = {"mode": "ascending", "targetRelativeAltitudeM": 15000, "ascentRateMs": 5, "descentRateMs": 6.5}
    async with client:
        response = await client.post(PREFIX + "/predictions", json=request, headers=authorized(app))
        assert response.status_code == status, response.text
    if status == 200:
        prediction = response.json()
        assert prediction["context"]["telemetryId"] == telemetry["id"]
        assert prediction["context"]["origin"]["altitudeM"] == 3000
        assert provider.predict.await_args.args[0]["launch_altitude"] == 3000
        assert provider.predict.await_args.args[0]["burst_altitude"] == 16870
        assert "launchDatetime" not in prediction["parameters"] or prediction["parameters"]["launchDatetime"] is None
    else:
        provider.predict.assert_not_awaited()


@pytest.mark.parametrize("failure,status", [(PredictionUnavailable("offline"), 502),
                                           (PredictionTimeout("timeout"), 504)])
async def test_failed_first_attempt_keeps_null_prediction_and_cadence_survives_restart(store, db_url, failure, status):
    provider = synthetic_provider()
    provider.predict.side_effect = failure
    app, client = app_and_client(store, db_url, provider)
    async with client:
        response = await client.post(PREFIX + "/predictions", json=planned_request(), headers=authorized(app))
        assert response.status_code == status, response.text
        assert (await client.get(PREFIX + "/dashboard")).json()["prediction"] is None
    restarted = PostgresStore(db_url)
    try:
        fresh_provider = synthetic_provider()
        restarted_app, client = app_and_client(restarted, db_url, fresh_provider)
        async with client:
            blocked = await client.post(PREFIX + "/predictions", json=planned_request(), headers=authorized(restarted_app))
            assert blocked.status_code == 429
            assert 1 <= int(blocked.headers["Retry-After"]) <= 60
        fresh_provider.predict.assert_not_awaited()
    finally:
        await restarted.close()


async def test_invalid_response_preserves_last_valid_prediction_and_persists_failed_attempt(store, db_url):
    parameters = planned_request()
    wire = {"profile": "standard_profile", "launch_latitude": 21.0, "launch_longitude": 258.0,
            "launch_altitude": 1870.0, "launch_datetime": parameters["launchDatetime"],
            "burst_altitude": 16870.0, "ascent_rate": 5.0, "descent_rate": 6.5}
    old_time = datetime.now(timezone.utc) - timedelta(seconds=120)
    attempt_id = await store.reserve_prediction("test-flight", wire, old_time)
    raw = synthetic_tawhiri(wire)
    context = {"mode": "planned", "origin": {"latitude": 21.0, "longitude": -102.0, "altitudeM": 1870.0},
               "originAt": parameters["launchDatetime"], "telemetryId": None, "dataset": None, "altitudeReference": "MSL"}
    prior = normalize_prediction(raw, "test-flight", attempt_id, parameters, context, old_time)
    await store.complete_prediction(attempt_id, raw, prior)
    provider = synthetic_provider()
    provider.predict.side_effect = None
    provider.predict.return_value = {"prediction": []}
    publisher = AsyncMock()
    app, client = app_and_client(store, db_url, provider, publisher=publisher)
    async with client:
        failed = await client.post(PREFIX + "/predictions", json=planned_request(), headers=authorized(app))
        assert failed.status_code == 502
        snapshot = (await client.get(PREFIX + "/dashboard")).json()
        assert snapshot["prediction"] == prior
        assert snapshot["predictionSettings"]["nextAllowedAt"] is not None
    publisher.publish_prediction.assert_not_awaited()


async def test_publication_failure_keeps_committed_result_in_snapshot(store, db_url):
    publisher = AsyncMock()
    publisher.publish_prediction.side_effect = RuntimeError("synthetic unavailable websocket")
    app, client = app_and_client(store, db_url, synthetic_provider(), publisher=publisher)
    async with client:
        response = await client.post(PREFIX + "/predictions", json=planned_request(), headers=authorized(app))
        assert response.status_code == 200, response.text
        assert (await client.get(PREFIX + "/dashboard")).json()["prediction"] == response.json()


async def test_real_websocket_prediction_matches_http_response_and_dashboard(store, db_url):
    def run_client():
        app = create_app(Settings(database_url=db_url, source="test-chirpstack", prediction_enabled=True,
                                  prediction_references=REFERENCES), prediction_provider=synthetic_provider())
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000),
                        backend_options={"loop_factory": asyncio.SelectorEventLoop}) as client:
            with client.websocket_connect("ws://localhost" + PREFIX + "/stream",
                                          headers={"Origin": "http://localhost:5173"}) as websocket:
                assert websocket.receive_json()["type"] == "ingestion"
                response = client.post(PREFIX + "/predictions", json=planned_request(), headers=authorized(app))
                assert response.status_code == 200, response.text
                assert websocket.receive_json() == {"type": "prediction", "data": response.json()}
                assert client.get(PREFIX + "/dashboard").json()["prediction"] == response.json()
    await asyncio.wait_for(asyncio.to_thread(run_client), 10)


async def test_confirmed_descent_rejects_prediction_without_provider_call(store, db_url):
    async with store.sessions.begin() as session:
        mission = await session.get(MissionRow, "test-flight")
        mission.snapshot = {**mission.snapshot, "phase": "descending"}
    provider = synthetic_provider()
    app, client = app_and_client(store, db_url, provider)
    async with client:
        assert (await client.post(PREFIX + "/predictions", json=planned_request(), headers=authorized(app))).status_code == 422
    provider.predict.assert_not_awaited()
