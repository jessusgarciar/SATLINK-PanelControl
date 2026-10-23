import json
from contextlib import asynccontextmanager
from copy import deepcopy

import pytest
from httpx import ASGITransport, AsyncClient

from app.bootstrap.app import create_app
from app.bootstrap.config import Settings
from app.domain.entities.telemetry import MissionNotFound
from app.infrastructure.mission_settings import MissionSettings
from app.presentation.schemas.api import MissionParameters


class MemoryStore:
    def __init__(self, config):
        self.configuration = deepcopy(config)
        self.snapshot = {key: value for key, value in config.items() if key != "source"}
        self.snapshot.update(updatedAt="2026-10-01T12:00:00Z", startedAt=None,
                             endedAt=None, phase="unknown", beaconOn=None)
        self.fail_commit = False

    @asynccontextmanager
    async def edit_mission(self, mission_id):
        if mission_id != self.configuration["id"]:
            raise MissionNotFound(mission_id)
        config, snapshot = deepcopy(self.configuration), deepcopy(self.snapshot)
        yield config, snapshot
        if self.fail_commit:
            raise RuntimeError("Commit failed")
        self.configuration, self.snapshot = config, snapshot


@pytest.fixture
def setup_settings(tmp_path, mission_config):
    path = tmp_path / "mission.local.json"
    path.write_text(json.dumps(mission_config), encoding="utf-8")
    store = MemoryStore(mission_config)
    parameters = {"plannedLaunchAt": "2026-11-01T08:30:00-06:00", "launchLabel": "Sitio de prueba",
                  "launch": {"latitude": 22.0, "longitude": -103.0, "altitudeM": 2000.0},
                  "targetRelativeAltitudeM": 14000.0}
    return path, store, parameters


async def test_save_updates_file_and_active_mission_without_changing_identity_or_flight_times(setup_settings):
    path, store, parameters = setup_settings
    result = await MissionSettings(store, path).update("test-flight", MissionParameters.model_validate(parameters))
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["plannedLaunchAt"] == result["plannedLaunchAt"] == "2026-11-01T14:30:00+00:00"
    assert saved["launch"] == store.configuration["launch"] == result["launch"] == parameters["launch"]
    assert saved["deviceEui"] == result["deviceEui"] == "0102030405060708"
    assert saved["applicationId"] == result["applicationId"] == "test-app"
    assert result["startedAt"] is result["endedAt"] is None
    assert store.snapshot["targetRelativeAltitudeM"] == saved["targetRelativeAltitudeM"] == 14000


async def test_failed_commit_restores_original_file_and_mission(setup_settings):
    path, store, parameters = setup_settings
    original = path.read_bytes()
    snapshot = deepcopy(store.snapshot)
    store.fail_commit = True
    with pytest.raises(RuntimeError, match="Commit failed"):
        await MissionSettings(store, path).update("test-flight", MissionParameters.model_validate(parameters))
    assert path.read_bytes() == original
    assert store.snapshot == snapshot


async def test_local_application_name_backfills_existing_mission_and_survives_saves(setup_settings):
    path, store, parameters = setup_settings
    local = json.loads(path.read_text(encoding="utf-8"))
    local["applicationName"] = "sci-fi"
    path.write_text(json.dumps(local), encoding="utf-8")
    settings = MissionSettings(store, path)
    result = await settings.populate_application_name(store.snapshot)
    assert result["applicationName"] == store.snapshot["applicationName"] == store.configuration["applicationName"] == "sci-fi"
    # A name observed from ChirpStack takes precedence over the original local label.
    store.configuration["applicationName"] = store.snapshot["applicationName"] = "sci-fi-updated"
    result = await settings.update("test-flight", MissionParameters.model_validate(parameters))
    assert result["applicationName"] == json.loads(path.read_text(encoding="utf-8"))["applicationName"] == "sci-fi-updated"


async def test_local_name_is_not_applied_to_another_application(setup_settings):
    path, store, _ = setup_settings
    local = json.loads(path.read_text(encoding="utf-8"))
    local.update(applicationName="sci-fi", applicationId="different-application")
    path.write_text(json.dumps(local), encoding="utf-8")
    result = await MissionSettings(store, path).populate_application_name(store.snapshot)
    assert result.get("applicationName") is None
    assert store.configuration.get("applicationName") is None


async def test_failed_file_write_does_not_commit_mission(setup_settings, monkeypatch):
    path, store, parameters = setup_settings
    snapshot = deepcopy(store.snapshot)
    def denied(*args):
        raise PermissionError("Read-only file")
    monkeypatch.setattr("app.infrastructure.mission_settings.replace_file", denied)
    with pytest.raises(PermissionError):
        await MissionSettings(store, path).update("test-flight", MissionParameters.model_validate(parameters))
    assert store.snapshot == snapshot


async def test_parameters_api_requires_token_rejects_readonly_fields_and_publishes_mission(setup_settings):
    path, store, parameters = setup_settings
    app = create_app(Settings(database_url="postgresql+psycopg://localhost/unused"), store=store, mission_path=path)
    origin = "http://localhost:5173"
    headers = {"Origin": origin, "X-CSRF-Token": app.state.prediction_csrf_token}
    async with AsyncClient(transport=ASGITransport(app=app, client=("127.0.0.1", 50000)), base_url="http://localhost") as client:
        url = "/api/v1/missions/test-flight/parameters"
        assert (await client.put(url, json=parameters, headers={"Origin": origin})).status_code == 403
        for field in ("deviceEui", "applicationId", "applicationName", "name", "startedAt"):
            response = await client.put(url, json={**parameters, field: "not-editable"}, headers=headers)
            assert response.status_code == 422
        for invalid in ({"targetRelativeAltitudeM": 15001}, {"plannedLaunchAt": "2026-11-01T08:30:00"},
                        {"launchLabel": "   "}, {"launch": {"latitude": 91, "longitude": 0, "altitudeM": 0}}):
            assert (await client.put(url, json={**parameters, **invalid}, headers=headers)).status_code == 422
        with app.state.hub.subscribe("test-flight") as queue:
            response = await client.put(url, json=parameters, headers=headers)
            assert response.status_code == 200, response.text
            message = queue.get_nowait()
            assert message["type"] == "mission"
            assert message["data"]["plannedLaunchAt"] == response.json()["plannedLaunchAt"]
        schema = (await client.get("/openapi.json")).json()
        assert schema["paths"][url.replace("test-flight", "{mission_id}")]["put"]["requestBody"]
