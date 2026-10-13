from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func

from app.bootstrap.app import create_app
from app.bootstrap.config import Settings
from app.bootstrap.demo import DEMO_MISSION
from app.infrastructure.database.models import ReceivedEventRow, TelemetryRow
from tests.unit.test_manual_prediction import prediction_response


class Provider:
    async def predict(self, request):
        return prediction_response(request)

    async def close(self):
        pass


async def test_demo_prediction_survives_reconnect_without_inserting_fake_received_events(store, db_url):
    await store.initialize_mission(DEMO_MISSION)
    before = await store.prediction_context("satlink-demo")
    settings = Settings(database_url=db_url, demo_prediction_enabled=True)
    def app():
        return create_app(settings, store=store, prediction_provider=Provider())
    headers = {"Origin": "http://localhost:5173"}
    body = {"phase": "ascending", "parameters": {"mode": "ascending", "targetRelativeAltitudeM": 15000.0,
        "ascentRateMs": 5.0, "descentRateMs": 6.5}, "sample": {"latitude": 21.9, "longitude": -102.2,
        "altitudeM": 3000.0, "time": datetime.now(timezone.utc).isoformat()}}
    async with AsyncClient(transport=ASGITransport(app=app(), client=("127.0.0.1", 5000)), base_url="http://localhost") as client:
        headers["X-CSRF-Token"] = (await client.get("/api/v1/demo/predictions")).json()["csrfToken"]
        response = await client.post("/api/v1/demo/predictions", json=body, headers=headers)
        assert response.status_code == 200, response.text
        result = response.json()
    async with AsyncClient(transport=ASGITransport(app=app(), client=("127.0.0.1", 5000)), base_url="http://localhost") as client:
        session = (await client.get("/api/v1/demo/predictions")).json()
        assert session["prediction"]["id"] == result["id"]
        assert session["prediction"]["context"]["inputSource"] == "simulated"
        headers["X-CSRF-Token"] = session["csrfToken"]
        assert (await client.post("/api/v1/demo/predictions", json=body, headers=headers)).status_code == 429
    assert await store.prediction_context("satlink-demo") == before
    async with store.sessions() as session:
        for row in (ReceivedEventRow, TelemetryRow):
            assert await session.scalar(select(func.count()).select_from(row).where(row.mission_id == "satlink-demo")) == 0
