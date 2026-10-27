from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.bootstrap.app import create_app
from app.bootstrap.config import Settings


@pytest.mark.parametrize("feedback", [{}, {"feedbackAt": "2026-10-26T18:05:48.905000+00:00"}])
async def test_dashboard_serializes_commands_with_and_without_firmware_feedback(mission_config, feedback):
    timestamp = "2026-10-26T18:05:48.905000+00:00"
    mission = {key: value for key, value in mission_config.items() if key != "source"}
    mission.update(updatedAt=timestamp, startedAt=None, endedAt=None, phase="unknown", beaconOn=None)
    command = {
        "id": "synthetic-command", "missionId": mission["id"], "clientRequestId": "synthetic-request",
        "type": "PING", "status": "executed" if feedback else "pending",
        "createdAt": timestamp, "updatedAt": timestamp, "evidence": "Synthetic test",
        "watchdogSeconds": 3600, "simulated": False, "seq": 1,
        "result": {"rttMs": 100} if feedback else None, **feedback,
    }
    store = AsyncMock()
    store.dashboard.return_value = {"mission": mission, "telemetry": [], "commands": [command]}
    app = create_app(Settings(database_url="postgresql+psycopg://localhost/unused"), store=store)
    async with AsyncClient(transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
                           base_url="http://localhost") as client:
        response = await client.get(f"/api/v1/missions/{mission['id']}/dashboard")
        assert response.status_code == 200
        returned = response.json()["commands"][0]
        assert returned["feedbackAt"] == feedback.get("feedbackAt")
        assert returned["status"] == command["status"]
        assert returned["result"] == command["result"]
        schema = (await client.get("/openapi.json")).json()["components"]["schemas"]["CommandDTO"]
        assert "feedbackAt" in schema["properties"]
        assert "feedbackAt" not in schema["required"]
