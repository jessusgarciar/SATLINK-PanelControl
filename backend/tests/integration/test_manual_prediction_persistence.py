"""Synthetic manual planning through HTTP and PostgreSQL; no real predictor."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.bootstrap.app import create_app
from app.bootstrap.config import Settings
from app.infrastructure.database.models import MissionRow
from app.infrastructure.database.store import PostgresStore


pytestmark = pytest.mark.integration


async def test_manual_planning_survives_restart_without_rewriting_mission_origin(store, db_url):
    manual = {"latitude": 21.5, "longitude": -101.5, "altitudeM": 2300.0}
    body = {"mode": "planned", "launch": manual, "launchAltitudeReference": "MSL",
            "launchDatetime": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "targetRelativeAltitudeM": 15000.0, "ascentRateMs": 5.0, "descentRateMs": 6.5}
    before = deepcopy((await store.dashboard("test-flight"))["mission"])
    provider = AsyncMock()
    def response(request):
        start = datetime.fromisoformat(request["launch_datetime"].replace("Z", "+00:00"))
        def point(seconds, altitude):
            return {"datetime": (start + timedelta(seconds=seconds)).isoformat(), "altitude": altitude,
                    "latitude": request["launch_latitude"], "longitude": request["launch_longitude"]}
        transition = point(3000, request["burst_altitude"])
        return {"request": {**request, "dataset": "2026100700"}, "prediction": [
            {"stage": "ascent", "trajectory": [point(0, request["launch_altitude"]), transition]},
            {"stage": "descent", "trajectory": [deepcopy(transition), point(6000, 0.0)]}]}
    provider.predict.side_effect = response
    app = create_app(Settings(database_url=db_url, source="test-chirpstack", prediction_enabled=True,
                              prediction_references={}), store=store, prediction_provider=provider)
    async with AsyncClient(transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
                           base_url="http://localhost") as client:
        snapshot = (await client.get("/api/v1/missions/test-flight/dashboard")).json()
        assert snapshot["permissions"]["canPredict"] is True
        assert snapshot["predictionSettings"]["launchAltitudeReference"] == "unknown"
        headers = {"Origin": "http://localhost:5173", "X-CSRF-Token": snapshot["csrfToken"]}
        result = await client.post("/api/v1/missions/test-flight/predictions", json=body, headers=headers)
        assert result.status_code == 200, result.text
        prediction = result.json()
        assert prediction["parameters"] == body
        assert prediction["context"]["origin"] == manual
        assert prediction["release"]["altitudeM"] == 17300
        assert (await client.get("/api/v1/missions/test-flight/dashboard")).json()["mission"] == before
    async with store.sessions() as session:
        row = await session.get(MissionRow, "test-flight")
        assert row.configuration["launch"] == before["launch"]
        assert row.snapshot == before
    restarted = PostgresStore(db_url)
    try:
        snapshot = await restarted.dashboard("test-flight")
        assert snapshot["prediction"] == prediction
        assert snapshot["mission"] == before
    finally:
        await restarted.close()
