from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.ingest import IngestTelemetry
from app.domain.entities.telemetry import Mission
from app.infrastructure.mqtt.picaro import decode_payload
from app.presentation.schemas.uplink import ChirpStackDecoder


async def ingest_sample(make_uplink, mission_config, binary=None, **changes):
    store, publisher = AsyncMock(), AsyncMock()
    store.find_mission.return_value = Mission(
        "test-flight", "test-chirpstack", "test-app", "0102030405060708", mission_config
    )
    store.persist.return_value = True
    service = IngestTelemetry(store, publisher, "test-chirpstack", ChirpStackDecoder(decode_payload))
    return await service.execute(*make_uplink(binary, **changes))


async def test_device_and_radio_metadata_reach_the_dashboard_contract(make_uplink, mission_config):
    # GPS activo/fix, carga y USB; siete satélites y batería al 100%.
    binary = bytearray.fromhex("0100000000000000000000000fa06400002710")
    binary[0] = 39
    binary[11] = 7
    sample = await ingest_sample(make_uplink, mission_config, bytes(binary), dr=3,
                                 txInfo={"frequency": 902300000})
    assert sample["device"] == {
        "gpsActive": True, "gpsFix": True, "satellites": 7,
        "batteryPct": 100, "charging": True, "usbPowered": True,
    }
    assert sample["radio"] == {
        "gatewayId": "strong", "frequencyHz": 902300000, "dataRate": 3, "fPort": 10,
    }
    assert (sample["snrDb"], sample["rssiDbm"]) == (6, -100)


@pytest.mark.parametrize("dr", [None, True, "3", -1, 16, 2.5])
async def test_invalid_or_absent_data_rate_stays_unknown(dr, make_uplink, mission_config):
    sample = await ingest_sample(make_uplink, mission_config, dr=dr,
        txInfo={"modulation": {"lora": {"spreadingFactor": 7, "bandwidth": 125000}}})
    assert sample["radio"]["dataRate"] is None
    assert sample["radio"]["frequencyHz"] is None


async def test_partial_radio_metadata_never_becomes_zero_or_mixes_gateways(make_uplink, mission_config):
    sample = await ingest_sample(make_uplink, mission_config, rxInfo=[], txInfo={})
    assert sample["snrDb"] is sample["rssiDbm"] is None
    assert sample["radio"] == {
        "gatewayId": None, "frequencyHz": None, "dataRate": None, "fPort": 10,
    }
    partial = await ingest_sample(make_uplink, mission_config,
        rxInfo=[{"gatewayId": "snr-only", "snr": 8}, {"gatewayId": "rssi-only", "rssi": -40}])
    assert partial["radio"]["gatewayId"] == "snr-only"
    assert partial["snrDb"] == 8
    assert partial["rssiDbm"] is None


async def test_absent_fix_and_battery_sentinel_preserve_other_sensor_readings(make_uplink, mission_config):
    binary = bytearray.fromhex("04000000000000000000000001cc000a341fdb")
    binary[14] = 255
    sample = await ingest_sample(make_uplink, mission_config, bytes(binary))
    assert sample["device"]["gpsFix"] is False
    assert sample["device"]["batteryPct"] is None
    assert sample["latitude"] is sample["longitude"] is sample["altitudeGpsM"] is None
    assert sample["relativeAltitudeM"] is None
    assert (sample["temperatureC"], sample["pressureHpa"], sample["batteryV"]) == (26.12, 815.5, 0.46)
