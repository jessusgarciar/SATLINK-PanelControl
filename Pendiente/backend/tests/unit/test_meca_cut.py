import struct
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import pytest
from app.infrastructure.mqtt.picaro import decode_payload
from app.infrastructure.mqtt.commands import CommandProfile, ChirpStackCommands
from app.domain.entities.radiosonda import flight_state, command_result
from app.bootstrap.config import Settings

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
                             {"PING": "", "RELEASE_NOW": ""}, "radiosonda-meca-v1")
    client = AsyncMock(); client.__aenter__.return_value = client
    monkeypatch.setattr("app.infrastructure.mqtt.commands.aiomqtt.Client", lambda **kwargs: client)
    adapter = ChirpStackCommands(Settings(database_url="postgresql+psycopg://unused/unused"), profile)
    mission = {"id": "test-flight", "applicationId": "test-app", "deviceEui": profile.device_eui, "telemetryProtocol": "radiosonda-meca-v1"}
    import json, base64
    for kind, port, binary in [("PING", 30, bytes([7])), ("RELEASE_NOW", 31, b"CORT" + bytes([7]))]:
        command = {"id": "00000000-0000-0000-0000-000000000001", "type": kind, "seq": 7}
        await adapter.send(mission, command)
        raw = json.loads(client.publish.call_args.args[1])
        assert raw["fPort"] == port and raw["confirmed"] is False
        assert base64.b64decode(raw["data"]) == binary
        assert client.publish.call_args.kwargs["retain"] is False

