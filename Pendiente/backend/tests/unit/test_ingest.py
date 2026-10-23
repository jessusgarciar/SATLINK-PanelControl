import asyncio
from unittest.mock import AsyncMock
import pytest
from app.application.use_cases.ingest import IngestTelemetry
from app.domain.entities.telemetry import Mission
from app.infrastructure.mqtt.picaro import decode_payload
from app.presentation.schemas.uplink import ChirpStackDecoder


@pytest.mark.parametrize("gps_m,relative", [(1870, 0), (16870, 15000), (18000, 16130)])
async def test_relative_height(gps_m, relative, make_uplink, mission_config):
    raw = bytearray.fromhex("0100000000000000000000000fa06400002710")
    raw[9:11] = gps_m.to_bytes(2, "big", signed=True)
    store, publisher = AsyncMock(), AsyncMock()
    store.find_mission.return_value = Mission("test-flight", "test-chirpstack", "test-app", "0102030405060708", mission_config)
    store.persist.return_value = True
    service = IngestTelemetry(store, publisher, "test-chirpstack", ChirpStackDecoder(decode_payload))
    result = await service.execute(*make_uplink(bytes(raw)))
    assert result["relativeAltitudeM"] == relative
    assert result["altitudeBarometricM"] is result["verticalSpeedMs"] is None


async def test_no_publication_before_commit_and_rollback(make_uplink, mission_config):
    committed = asyncio.Event()
    store, publisher = AsyncMock(), AsyncMock()
    store.find_mission.return_value = Mission("test-flight", "test-chirpstack", "test-app", "0102030405060708", mission_config)
    async def persist(*args):
        await committed.wait()
        raise RuntimeError("rollback")
    store.persist.side_effect = persist
    service = IngestTelemetry(store, publisher, "test-chirpstack", ChirpStackDecoder(decode_payload))
    task = asyncio.create_task(service.execute(*make_uplink()))
    await asyncio.sleep(0)
    publisher.publish.assert_not_awaited()
    committed.set()
    with pytest.raises(RuntimeError):
        await task
    publisher.publish.assert_not_awaited()


async def test_duplicates_and_unmapped_devices_do_not_publish(make_uplink, mission_config):
    store, publisher = AsyncMock(), AsyncMock()
    store.find_mission.return_value = Mission("test-flight", "test-chirpstack", "test-app", "0102030405060708", mission_config)
    store.persist.return_value = False
    service = IngestTelemetry(store, publisher, "test-chirpstack", ChirpStackDecoder(decode_payload))
    assert await service.execute(*make_uplink()) is None
    store.find_mission.return_value = None
    assert await service.execute(*make_uplink()) is None
    publisher.publish.assert_not_awaited()
    store.reject.assert_awaited_once()


async def test_chirpstack_application_name_is_published_from_committed_mission(make_uplink, mission_config):
    store, publisher = AsyncMock(), AsyncMock()
    original = Mission("test-flight", "test-chirpstack", "test-app", "0102030405060708", mission_config)
    updated = Mission(original.id, original.source, original.application_id, original.dev_eui,
                      {**mission_config, "applicationName": "sci-fi", "updatedAt": "2026-10-02T12:00:00Z"})
    store.find_mission.side_effect = [original, updated]
    store.persist.return_value = True
    service = IngestTelemetry(store, publisher, original.source, ChirpStackDecoder(decode_payload))
    await service.execute(*make_uplink(deviceInfo={"applicationId": "test-app", "devEui": original.dev_eui,
                                                  "applicationName": "sci-fi"}))
    publisher.publish_mission.assert_awaited_once()
    mission = publisher.publish_mission.call_args.args[1]
    assert mission["applicationName"] == "sci-fi"
    assert mission["applicationId"] == "test-app"


@pytest.mark.parametrize("value", [None, "", "  ", 123, "x" * 257])
async def test_missing_or_invalid_application_names_do_not_clear_identity(value, make_uplink, mission_config):
    store, publisher = AsyncMock(), AsyncMock()
    store.find_mission.return_value = Mission("test-flight", "test-chirpstack", "test-app", "0102030405060708",
                                             {**mission_config, "applicationName": "sci-fi"})
    store.persist.return_value = True
    service = IngestTelemetry(store, publisher, "test-chirpstack", ChirpStackDecoder(decode_payload))
    await service.execute(*make_uplink(deviceInfo={"applicationId": "test-app", "devEui": "0102030405060708",
                                                  "applicationName": value}))
    publisher.publish_mission.assert_not_awaited()
