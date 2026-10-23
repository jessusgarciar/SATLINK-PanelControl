import struct
from unittest.mock import AsyncMock
import pytest
from app.infrastructure.mqtt.picaro import decode_payload
from app.presentation.schemas.uplink import ChirpStackDecoder
from app.application.use_cases.ingest import IngestTelemetry
from app.domain.entities.telemetry import Mission
from app.presentation.schemas.api import TelemetryDTO


def test_position_packet_uses_little_endian_and_has_no_environment():
    raw = bytes([0x45]) + struct.pack("<iiH", 210000000, -1020000000, 2000)
    result = decode_payload(raw, 17)
    assert (result["latitude"], result["longitude"], result["altitudeGpsM"]) == (21, -102, 2000)
    assert result["temperatureC"] is result["batteryV"] is None
    assert result["metadata"]["burst"] == 5


def test_environment_packet_flags_are_distinct_from_full_codec():
    raw = bytes([0x85]) + struct.pack("<hHBHBBB", -1250, 8000, 49, 3700, 255, 9, 0x3b)
    result = decode_payload(raw, 17)
    assert (result["temperatureC"], result["pressureHpa"], result["humidityPct"], result["batteryV"]) == (-12.5, 800, 49, 3.7)
    assert result["latitude"] is result["longitude"] is result["altitudeGpsM"] is None
    assert result["metadata"]["gpsFix"] is True
    assert result["metadata"]["usbPowered"] is True
    assert result["metadata"]["charging"] is False
    assert result["metadata"]["batteryPct"] is None


def test_navigation_preserves_reported_vertical_speed_and_uptime():
    raw = bytes([0xc5]) + struct.pack("<HHBh", 125, 900, 10, -123) + (86400).to_bytes(3, "little")
    result = decode_payload(raw, 17)
    assert result["verticalSpeedMs"] == -12.3
    assert result["metadata"]["speedKmh"] == 12.5
    assert result["metadata"]["uptimeSeconds"] == 86400
    assert result["temperatureC"] is result["altitudeGpsM"] is None


@pytest.mark.parametrize("raw", [b"", bytes(10), bytes(12), bytes(11)])
def test_invalid_lengths_and_unknown_packet_type_are_rejected(raw):
    with pytest.raises(ValueError):
        decode_payload(raw, 17)


def test_no_fix_and_all_sentinels_stay_unknown():
    position = decode_payload(bytes([0x40]) + struct.pack("<iiH", 0, 0, 65535), 17)
    assert position["latitude"] is position["longitude"] is position["altitudeGpsM"] is None
    environment = decode_payload(bytes([0x80]) + struct.pack("<hHBHBBB", 32767, 65535, 255, 65535, 255, 255, 0), 17)
    assert all(environment[k] is None for k in ("temperatureC", "pressureHpa", "humidityPct", "batteryV"))
    navigation = decode_payload(bytes([0xc0]) + struct.pack("<HHBh", 65535, 65535, 255, 32767) + bytes(3), 17)
    assert navigation["verticalSpeedMs"] is None


async def test_port17_navigation_survives_envelope_persistence_and_publication(make_uplink, mission_config):
    raw = bytes([0xc1]) + struct.pack("<HHBh", 0, 0, 10, 52) + bytes(3)
    store, publisher = AsyncMock(), AsyncMock()
    store.find_mission.return_value = Mission("test-flight", "test-chirpstack", "test-app", "0102030405060708", mission_config)
    store.persist.return_value = True
    service = IngestTelemetry(store, publisher, "test-chirpstack", ChirpStackDecoder(decode_payload))
    result = await service.execute(*make_uplink(raw, fPort=17))
    assert result["verticalSpeedMs"] == 5.2
    assert result["latitude"] is result["relativeAltitudeM"] is None
    assert result["radio"]["fPort"] == 17
    assert TelemetryDTO.model_validate(result).verticalSpeedMs == 5.2
    publisher.publish.assert_awaited_once_with("test-flight", result)


async def test_environment_humidity_is_accepted_by_http_schema(make_uplink, mission_config):
    raw = bytes([0x81]) + struct.pack("<hHBHBBB", 2500, 8000, 45, 3800, 75, 8, 9)
    store, publisher = AsyncMock(), AsyncMock()
    store.find_mission.return_value = Mission("test-flight", "test-chirpstack", "test-app", "0102030405060708", mission_config)
    store.persist.return_value = True
    result = await IngestTelemetry(store, publisher, "test-chirpstack", ChirpStackDecoder(decode_payload)).execute(*make_uplink(raw, fPort=17))
    assert TelemetryDTO.model_validate(result).humidityPct == 45
