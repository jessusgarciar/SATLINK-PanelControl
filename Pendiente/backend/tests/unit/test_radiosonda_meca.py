import base64
import json
import struct
from unittest.mock import AsyncMock
import pytest
from app.infrastructure.mqtt.picaro import decode_payload
from app.infrastructure.mqtt.commands import CommandProfile, ChirpStackCommands
from app.application.use_cases.ingest import IngestTelemetry
from app.bootstrap.config import Settings
from app.domain.entities.telemetry import Mission
from app.presentation.schemas.api import TelemetryDTO
from app.presentation.schemas.uplink import ChirpStackDecoder

VECTORS = [(20, '047b350dd9060bc371070c'), (21, 'ff7fffffffffffffffff59'),
           (22, 'ff7fffffff7fffb90f8703'), (23, '48fec11f21ffffff7f0409'), (30, '07c0ff2c')]

@pytest.mark.parametrize('port,payload', VECTORS)
def test_observed_meca_payloads(port, payload):
    result = decode_payload(bytes.fromhex(payload), port)
    meta = result['metadata']
    assert meta['codecVersion'] == 'radiosonda-meca-v1'
    assert 'watchdogActive' not in meta
    if port == 20:
        assert result['altitudeGpsM'] == 1905 and meta['satellites'] == 12
        assert meta['gpsFix'] is True
    elif port == 21:
        assert result['temperatureC'] is result['pressureHpa'] is result['humidityPct'] is None
        assert meta['batteryPct'] == 89
    elif port == 22:
        assert result['batteryV'] == 4.025 and meta['uptimeS'] == 3612
    elif port == 23:
        assert meta['boardTemperatureC'] == -4.4 and meta['boardPressureHpa'] == 812.9
        assert meta['boardHumidityPct'] == 33 and meta['lectura'] == 4
        assert 'temperatureC' not in result
    else:
        assert (meta['seq'], meta['downlinkRssiDbm'], meta['downlinkSnrDb']) == (7, -64, 11)

@pytest.mark.parametrize('port,payload', VECTORS)
@pytest.mark.parametrize('size', [0, 1, 5, 10, 12, 19])
def test_bad_lengths(port, payload, size):
    with pytest.raises(ValueError): decode_payload(bytes(size), port)

@pytest.mark.parametrize('port', [0, 19, 24, 31, 255])
def test_unsupported_ports_and_invalid_cut_event(port):
    with pytest.raises(ValueError): decode_payload(bytes(11), port)

def test_documented_meca_flight_flags_and_zero_measurements():
    meta = decode_payload(bytes.fromhex('0000000000ffffff7f04ff'), 23)['metadata']
    assert meta['gpsActive'] is True and meta['usbPowered'] is True
    assert all(meta[k] for k in ('enVuelo', 'corteEnCurso', 'cortado'))
    decoded = decode_payload(bytes(11), 21)
    assert decoded['temperatureC'] == decoded['pressureHpa'] == decoded['humidityPct'] == 0
    nofix = decode_payload(bytes.fromhex('0000000000000000ffff00'), 20)
    assert nofix['altitudeGpsM'] is nofix['latitude'] is None
    assert nofix['metadata']['gpsFix'] is False

async def test_marco_transport_only_and_no_actual_broker(monkeypatch):
    profile = CommandProfile('test-flight', 'test-app', '0102030405060708', 'test', 30, {'PING': ''}, 'radiosonda-meca-v1')
    client = AsyncMock(); client.__aenter__.return_value = client
    monkeypatch.setattr('app.infrastructure.mqtt.commands.aiomqtt.Client', lambda **kw: client)
    adapter = ChirpStackCommands(Settings(database_url='postgresql+psycopg://unused/unused'), profile)
    mission = dict(id='test-flight', applicationId='test-app', deviceEui=profile.device_eui, telemetryProtocol=profile.protocol)
    await adapter.send(mission, dict(id='00000000-0000-0000-0000-000000000001', type='PING', seq=7))
    topic, payload = client.publish.call_args.args
    sent = json.loads(payload)
    assert topic == 'application/test-app/device/0102030405060708/command/down'
    assert sent['fPort'] == 30 and sent['confirmed'] is False
    assert base64.b64decode(sent['data']) == b'\x07'
    assert client.publish.call_args.kwargs['retain'] is False
    for kind in ('START_MISSION', 'STATUS', 'TELEMETRY'):
        with pytest.raises(ValueError): profile.encode(dict(type=kind, seq=7))
    for seq in (0, 256, True, None):
        with pytest.raises(ValueError): profile.encode(dict(type='PING', seq=seq))

@pytest.mark.parametrize('port,payload', VECTORS)
async def test_partial_packets_and_control_publication(port, payload, make_uplink, mission_config):
    store, publisher = AsyncMock(), AsyncMock()
    config = {**mission_config, 'telemetryProtocol': 'radiosonda-meca-v1'}
    store.find_mission.return_value = Mission(config['id'], config['source'], config['applicationId'], config['deviceEui'], config)
    store.persist.return_value = True
    ingest = IngestTelemetry(store, publisher, config['source'], ChirpStackDecoder(decode_payload))
    result = await ingest.execute(*make_uplink(bytes.fromhex(payload), fPort=port))
    TelemetryDTO.model_validate(result)
    if port == 30: publisher.publish.assert_not_awaited()
    else: publisher.publish.assert_awaited_once()

async def test_meca_payload_not_assigned_to_legacy_mission(make_uplink, mission_config):
    store, publisher = AsyncMock(), AsyncMock()
    store.find_mission.return_value = Mission(mission_config['id'], mission_config['source'], mission_config['applicationId'], mission_config['deviceEui'], mission_config)
    ingest = IngestTelemetry(store, publisher, mission_config['source'], ChirpStackDecoder(decode_payload))
    assert await ingest.execute(*make_uplink(bytes(11), fPort=21)) is None
    store.persist.assert_not_awaited()
    store.reject.assert_awaited_once()
