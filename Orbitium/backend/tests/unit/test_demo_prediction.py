from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.bootstrap.app import create_app
from app.bootstrap.config import Settings
from app.bootstrap.demo import DEMO_MISSION
from app.application.use_cases.predict import PredictMission
from app.domain.entities.prediction import PredictionInvalid
from app.presentation.schemas.prediction import DemoPredictionRequest
from tests.unit.test_manual_prediction import prediction_response, planned_body


def doubles():
    store, provider, publisher = AsyncMock(), AsyncMock(), AsyncMock()
    store.prediction_context.return_value = {"mission": {**deepcopy(DEMO_MISSION), "phase": "unknown"}, "telemetry": None}
    store.reserve_prediction.return_value = "demo-attempt"
    provider.predict.side_effect = prediction_response
    store.latest_prediction.return_value = None
    store.prediction_next_allowed_at.return_value = None
    return store, provider, publisher


async def test_simulated_gps_uses_current_sample_without_persisting_telemetry_or_mutating_mission():
    store, provider, publisher = doubles()
    before = deepcopy(store.prediction_context.return_value)
    now = datetime.now(timezone.utc).isoformat()
    sample = {"latitude": 21.9, "longitude": -102.2, "altitudeM": 3000.0, "time": now}
    result = await PredictMission(store, provider, publisher).execute("satlink-demo",
        {"mode": "ascending", "targetRelativeAltitudeM": 15000.0, "ascentRateMs": 5.0, "descentRateMs": 6.5},
        {"launchAltitudeReference": "MSL", "gpsAltitudeReference": "MSL"},
        simulated={"phase": "ascending", "sample": sample})
    wire = provider.predict.await_args.args[0]
    assert wire["launch_altitude"] == 3000
    assert wire["burst_altitude"] == 16870
    assert result["context"]["inputSource"] == "simulated"
    assert result["context"]["telemetryId"] is None
    assert store.prediction_context.return_value == before
    store.persist.assert_not_awaited()
    store.complete_prediction.assert_awaited_once()


@pytest.mark.parametrize("phase,sample", [
    ("descending", None), ("landed", None), ("ascending", None),
    ("ascending", {"latitude": 21.9, "longitude": -102.2, "altitudeM": 3000.0,
                   "time": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()}),
])
async def test_invalid_demo_context_never_calls_provider(phase, sample):
    store, provider, publisher = doubles()
    with pytest.raises(PredictionInvalid):
        await PredictMission(store, provider, publisher).execute("satlink-demo",
            {"mode": "ascending", "targetRelativeAltitudeM": 15000.0, "ascentRateMs": 5.0, "descentRateMs": 6.5},
            {"launchAltitudeReference": "MSL", "gpsAltitudeReference": "MSL"},
            simulated={"phase": phase, "sample": sample})
    provider.predict.assert_not_awaited()


async def test_demo_routes_require_enablement_origin_and_csrf_and_leave_real_prediction_disabled():
    store, provider, publisher = doubles()
    app = create_app(Settings(database_url="postgresql+psycopg://localhost/unused", demo_prediction_enabled=True),
                     store=store, publisher=publisher, prediction_provider=provider)
    async with AsyncClient(transport=ASGITransport(app=app, client=("127.0.0.1", 5000)), base_url="http://localhost") as client:
        session = (await client.get("/api/v1/demo/predictions")).json()
        body = {"parameters": planned_body(), "phase": "ascending", "sample": None}
        assert (await client.post("/api/v1/demo/predictions", json=body)).status_code == 403
        headers = {"Origin": "http://localhost:5173", "X-CSRF-Token": session["csrfToken"]}
        response = await client.post("/api/v1/demo/predictions", json=body, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["context"]["inputSource"] == "simulated"
        assert (await client.post("/api/v1/missions/real-flight/predictions", json=body["parameters"], headers=headers)).status_code == 403
        assert "/api/v1/demo/predictions" in (await client.get("/openapi.json")).json()["paths"]
    app = create_app(Settings(database_url="postgresql+psycopg://localhost/unused"), store=store, prediction_provider=provider)
    async with AsyncClient(transport=ASGITransport(app=app, client=("127.0.0.1", 5000)), base_url="http://localhost") as client:
        assert (await client.get("/api/v1/demo/predictions")).json()["enabled"] is False
        assert (await client.post("/api/v1/demo/predictions", json=body, headers=headers)).status_code == 403


def test_demo_schema_rejects_invalid_coordinates_and_unknown_phase():
    for extra in ({"phase": "unknown"}, {"sample": {"latitude": 91.0, "longitude": 0.0, "altitudeM": 0.0, "time": "invalid"}}):
        with pytest.raises(ValidationError):
            DemoPredictionRequest.model_validate({"parameters": planned_body(), "phase": "ascending", **extra})
