import struct
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import pytest
from app.infrastructure.mqtt.picaro import decode_payload
from app.infrastructure.mqtt.commands import CommandProfile, ChirpStackCommands
from app.domain.entities.radiosonda import flight_state, command_result
from app.application.use_cases.ingest import IngestTelemetry
from app.domain.entities.telemetry import Mission
from app.presentation.schemas.uplink import ChirpStackDecoder
from app.presentation.schemas.api import TelemetryDTO
from app.bootstrap.config import Settings

VECTORS = [(20, "0000000000000000ffffff"), (21, "720cbe1f64ffffffffffff"),
           (22, "ff7fffffff7fffffff0100"), (23, "ff7fffffffffffff7f0002"),
           (30, "07c0ff2c"), (31, "010500001f07ffffff7f00")]

@pytest.mark.parametrize("port,hex_data", VECTORS)
def test_documented_vectors(port, hex_data):
    decoded = decode_payload(bytes.fromhex(hex_data), port)
    meta = decoded["metadata"]
    assert meta["codecVersion"] == "radiosonda-v1"
    if port == 20:
        assert decoded["latitude"] is decoded["longitude"] is decoded["altitudeGpsM"] is None
        assert meta["gpsFix"] is False and meta["satellites"] is None
    elif port == 21:
        assert (decoded["temperatureC"], decoded["pressureHpa"], decoded["humidityPct"]) == (31.86, 812.6, 100)
        assert meta["batteryPct"] is None
    elif port == 22:
        assert decoded["batteryV"] is None and meta["uptimeS"] == 4
    elif port == 23:
        assert meta["usbPowered"] is True and meta["enVuelo"] is False
        assert "temperatureC" not in decoded
    elif port == 30:
        assert (meta["seq"], meta["downlinkRssiDbm"], meta["downlinkSnrDb"]) == (7, -64, 11)
    else:
        assert (meta["evento"], meta["motivo"], meta["altitudeM"]) == ("inicio", "consola", 1823)
        assert meta["tVueloS"] is meta["verticalSpeedMs"] is None

@pytest.mark.parametrize("port,_", VECTORS)
@pytest.mark.parametrize("size", [0, 1, 5, 10, 12, 19])
def test_reject_wrong_lengths(port, _, size):
    with pytest.raises(ValueError): decode_payload(bytes(size), port)

def test_unsigned_altitude_and_bmp_null_humidity():
    d = decode_payload(struct.pack("<iiHB", 210000000, -1020000000, 40000, 9), 20)
    assert d["altitudeGpsM"] == 40000
    d = decode_payload(bytes.fromhex("00000000ffffffffffffff"), 21)
    assert d["temperatureC"] == d["pressureHpa"] == 0
    assert d["humidityPct"] is None

def test_flight_state_does_not_invent_start_and_rejects_old_state():
    now = datetime.now(timezone.utc)
    packet = decode_payload(bytes.fromhex("ff7fffffffffffff7f0010"), 23)["metadata"]
    state = flight_state(None, packet, now)
    assert state["watchdogActive"] is True and state["phase"] == "EN VUELO"
    assert "startedAt" not in state and "tVueloS" not in state
    packet["enVuelo"] = False
    assert flight_state(state, packet, now - timedelta(seconds=1)) == state
    packet.update(fPort=31, evento="sin_confirmar", motivo="downlink", seq=1, intento=3,
                  altitudeM=1800, altitudeSource="gps", tVueloS=100, verticalSpeedMs=None)
    state = flight_state(state, packet, now + timedelta(seconds=1))
    assert state["cutResult"] == "sin_confirmar"
    assert command_result(packet, now, now + timedelta(seconds=1))[1].endswith("SIN CONFIRMAR separación.")

async def test_command_bytes_ports_and_no_lorawan_confirmation(monkeypatch):
    profile = CommandProfile("test-flight", "test-app", "0102030405060708", "test", 30,
                             {"PING": "", "RELEASE_NOW": ""}, "radiosonda-v1")
    client = AsyncMock(); client.__aenter__.return_value = client
    monkeypatch.setattr("app.infrastructure.mqtt.commands.aiomqtt.Client", lambda **kwargs: client)
    adapter = ChirpStackCommands(Settings(database_url="postgresql+psycopg://unused/unused"), profile)
    mission = {"id": "test-flight", "applicationId": "test-app", "deviceEui": profile.device_eui, "telemetryProtocol": "radiosonda-v1"}
    import json, base64
    for kind, port, binary in [("PING", 30, bytes([7])), ("RELEASE_NOW", 31, b"CORT" + bytes([7]))]:
        command = {"id": "00000000-0000-0000-0000-000000000001", "type": kind, "seq": 7}
        await adapter.send(mission, command)
        raw = json.loads(client.publish.call_args.args[1])
        assert raw["fPort"] == port and raw["confirmed"] is False
        assert base64.b64decode(raw["data"]) == binary
        assert client.publish.call_args.kwargs["retain"] is False

@pytest.mark.parametrize("port,hex_data", VECTORS)
async def test_partial_ingestion_does_not_require_gps(port, hex_data, make_uplink, mission_config):
    store, publisher = AsyncMock(), AsyncMock()
    store.find_mission.return_value = Mission("test-flight", "test-chirpstack", "test-app", "0102030405060708", mission_config)
    store.persist.return_value = True
    ingestor = IngestTelemetry(store, publisher, "test-chirpstack", ChirpStackDecoder(decode_payload))
    result = await ingestor.execute(*make_uplink(bytes.fromhex(hex_data), fPort=port))
    assert result is not None
    TelemetryDTO.model_validate(result)
    if port in (30,31): publisher.publish.assert_not_awaited()
    else: publisher.publish.assert_awaited_once()


@pytest.mark.parametrize("hex_data", ["00000000feffffffffffff", "00000000ffffffffff0065", "fe7fffffffffffffffffff"])
def test_out_of_range_sensor_fields_do_not_poison_api(hex_data):
    with pytest.raises(ValueError): decode_payload(bytes.fromhex(hex_data), 21)
