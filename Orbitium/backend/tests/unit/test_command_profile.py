import base64
import json
from uuid import UUID
from unittest.mock import AsyncMock
import pytest
from app.bootstrap.config import Settings
from app.infrastructure.mqtt.commands import CommandProfile, ChirpStackCommands


def profile_data():
    # Formato SINTÉTICO, no representa un protocolo de firmware aprobado.
    return {"missionId": "synthetic", "applicationId": "synthetic-app", "source": "synthetic-source",
            "deviceEui": "0102030405060708", "fPort": 20,
            "payloadHex": {"PING": "01{requestId}", "START_MISSION": "04{requestId}{watchdogSeconds}"}}


@pytest.mark.parametrize("change", [
    {"fPort": 0}, {"fPort": True}, {"deviceEui": "bad"}, {"payloadHex": {"PING": "e1e6ff00"}},
    {"payloadHex": {"START_MISSION": "04{requestId}"}}, {"payloadHex": {"RELEASE_NOW": "05{requestId}"}},
    {"payloadHex": {"PING": "GG{requestId}"}}, {"payloadHex": {}},
])
def test_profile_rejects_invalid_or_uncorrelatable_commands(tmp_path, change):
    path = tmp_path / "commands.json"
    path.write_text(json.dumps({**profile_data(), **change}), encoding="utf-8")
    with pytest.raises(ValueError):
        CommandProfile.load(path)


async def test_publish_exact_device_id_payload_and_no_retained_message(tmp_path, monkeypatch):
    path = tmp_path / "commands.json"
    path.write_text(json.dumps(profile_data()), encoding="utf-8")
    profile = CommandProfile.load(path)
    adapter = ChirpStackCommands(Settings(database_url="postgresql+psycopg://unused/unused"), profile)
    client = AsyncMock()
    client.__aenter__.return_value = client
    monkeypatch.setattr("app.infrastructure.mqtt.commands.aiomqtt.Client", lambda **kwargs: client)
    mission = {"id": "synthetic", "applicationId": "synthetic-app", "deviceEui": "0102030405060708"}
    identifier = str(UUID(int=1))
    command = {"id": identifier, "type": "START_MISSION", "watchdogSeconds": 3300}
    await adapter.send(mission, command)
    topic, serialized = client.publish.call_args.args
    assert topic == "application/synthetic-app/device/0102030405060708/command/down"
    message = json.loads(serialized)
    assert message["id"] == identifier and message["confirmed"] is True and message["fPort"] == 20
    assert base64.b64decode(message["data"]) == b"\x04" + UUID(identifier).bytes + (3300).to_bytes(4, "big")
    assert client.publish.call_args.kwargs == {"qos": 1, "retain": False, "timeout": 4}
    with pytest.raises(ValueError):
        await adapter.send({**mission, "deviceEui": "ffffffffffffffff"}, command)
    assert client.publish.await_count == 1
