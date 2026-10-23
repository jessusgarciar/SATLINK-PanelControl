import json
from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.ingest import IngestTelemetry
from app.infrastructure.database.store import PostgresStore
from app.infrastructure.mission_settings import MissionSettings
from app.infrastructure.mqtt.picaro import decode_payload
from app.presentation.schemas.api import MissionParameters
from app.presentation.schemas.uplink import ChirpStackDecoder

pytestmark = pytest.mark.integration


async def test_chirpstack_name_survives_reconnect_and_late_uplinks(store, db_url, make_uplink):
    publisher = AsyncMock()
    service = IngestTelemetry(store, publisher, "test-chirpstack", ChirpStackDecoder(decode_payload))
    info = {"applicationId": "test-app", "devEui": "0102030405060708", "applicationName": "sci-fi"}
    await service.execute(*make_uplink(deviceInfo=info))
    assert (await store.dashboard("test-flight"))["mission"]["applicationName"] == "sci-fi"
    assert publisher.publish_mission.call_args.args[1]["applicationName"] == "sci-fi"
    await service.execute(*make_uplink(deviceInfo={**info, "applicationName": "outdated-name"},
                                       time="2026-10-01T12:00:00Z"))
    restarted = PostgresStore(db_url)
    try:
        assert (await restarted.dashboard("test-flight"))["mission"]["applicationName"] == "sci-fi"
    finally:
        await restarted.close()


async def test_local_name_and_map_coordinates_persist_to_database_and_file(store, mission_config, tmp_path):
    path = tmp_path / "mission.local.json"
    path.write_text(json.dumps({**mission_config, "applicationName": "sci-fi"}), encoding="utf-8")
    settings = MissionSettings(store, path)
    dashboard = await store.dashboard("test-flight")
    mission = await settings.populate_application_name(dashboard["mission"])
    assert mission["applicationName"] == "sci-fi"
    parameters = MissionParameters.model_validate({
        "plannedLaunchAt": "2026-11-01T08:30:00-06:00", "launchLabel": "Sitio seleccionado en mapa",
        "launch": {"latitude": 22.16, "longitude": -102.27, "altitudeM": 1911.0},
        "targetRelativeAltitudeM": 14000.0,
    })
    await settings.update("test-flight", parameters)
    saved = json.loads(path.read_text(encoding="utf-8"))
    mission = (await store.dashboard("test-flight"))["mission"]
    assert mission["launch"] == saved["launch"] == parameters.launch.model_dump()
    assert mission["applicationName"] == saved["applicationName"] == "sci-fi"
    assert mission["plannedLaunchAt"] == saved["plannedLaunchAt"] == "2026-11-01T14:30:00+00:00"
