import asyncio
import struct
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import httpx
import pytest
from app.application.use_cases.ingest import IngestTelemetry
from app.bootstrap.app import create_app
from app.bootstrap.config import Settings
from app.domain.entities.commands import CommandConflict
from app.infrastructure.mqtt.picaro import decode_payload
from app.presentation.schemas.uplink import ChirpStackDecoder
from app.presentation.websocket.hub import TelemetryHub

pytestmark = pytest.mark.integration

async def setup_radio(store):
    async with store.edit_mission('test-flight') as (config, snapshot):
        config.update(telemetryProtocol='radiosonda-meca-v1', altitudeTargetMode='absolute', staleAfterSeconds=1200)
        snapshot.update(telemetryProtocol='radiosonda-meca-v1', altitudeTargetMode='absolute', staleAfterSeconds=1200)

async def test_packets_feedback_deduplication_and_legacy_isolation(store, make_uplink, mission_config, db_url):
    await setup_radio(store)
    old = {**mission_config, 'id': 'legacy', 'deviceEui': '9999999999999999'}
    await store.initialize_mission(old)
    hub = TelemetryHub()
    ingest = IngestTelemetry(store, hub, 'test-chirpstack', ChirpStackDecoder(decode_payload))
    now = datetime.now(timezone.utc)
    ping, _ = await store.reserve_command('test-flight', str(uuid4()), 'PING', now)
    async def up(port, binary, count):
        return await ingest.execute(*make_uplink(binary, fPort=port, fCnt=count, time=(now + timedelta(seconds=count)).isoformat()))
    await up(20, bytes.fromhex('047b350dd9060bc371070c'), 1)
    await up(30, struct.pack('<Bhb', ping['seq'], -64, 44), 2)
    await up(21, bytes.fromhex('ff7fffffffffffffffff59'), 3)
    await up(22, bytes.fromhex('ff7fffffff7fffb90f8703'), 4)
    args = make_uplink(bytes.fromhex('48fec11f21ffffff7f04ff'), fPort=23, fCnt=9, time=(now + timedelta(seconds=5)).isoformat())
    assert await ingest.execute(*args)
    assert await ingest.execute(*args) is None
    dashboard = await store.dashboard('test-flight')
    assert len(dashboard['telemetry']) == 4
    assert dashboard['commands'][0]['status'] == 'executed'
    assert dashboard['commands'][0]['result']['rttSeconds'] == 2
    assert dashboard['commands'][0]['result']['rssiDbm'] == -64
    assert dashboard['mission']['flightState']['cortado'] is True
    assert dashboard['mission']['startedAt'] is None
    assert not (await store.dashboard('legacy'))['telemetry']
    await up(31, bytes(11), 10)
    first = await store.packets('test-flight', limit=2)
    assert len(first['items']) == 2 and first['items'][0]['status'] == 'rejected'
    second = await store.packets('test-flight', first['nextCursor'], 2)
    assert not {p['id'] for p in first['items']} & {p['id'] for p in second['items']}
    all_packets = await store.packets('test-flight')
    assert len(all_packets['items']) == 6
    assert next(p for p in all_packets['items'] if p['decoded'].get('fPort') == 23)['decoded']['boardTemperatureC'] == -4.4
    assert not (await store.packets('legacy'))['items']
    settings = Settings(database_url=db_url, source='test-chirpstack')
    app = create_app(settings, store=store)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost:8000') as client:
        response = await client.get('/api/v1/missions/test-flight/dashboard')
        assert response.status_code == 200
        command = response.json()['commands'][0]
        assert command['status'] == 'executed'
        assert datetime.fromisoformat(command['feedbackAt']) == now + timedelta(seconds=2)
        assert command['result']['rttSeconds'] == 2
        assert len(response.json()['telemetry']) == 4
        response = await client.get('/api/v1/missions/test-flight/packets?limit=2')
        assert response.status_code == 200 and len(response.json()['items']) == 2
        assert (await client.get('/api/v1/missions/test-flight/packets?limit=101')).status_code == 422
        assert (await client.get('/api/v1/missions/test-flight/packets?cursor=invalid')).status_code == 422

async def test_only_marco_reservable_idempotent_sequences_and_unrelated_polo(store, make_uplink):
    await setup_radio(store)
    now = datetime.now(timezone.utc)
    for kind in ('START_MISSION', 'STATUS', 'TELEMETRY'):
        with pytest.raises(CommandConflict): await store.reserve_command('test-flight', str(uuid4()), kind, now)
    request = str(uuid4())
    one, two = await asyncio.gather(*[store.reserve_command('test-flight', request, 'PING', now) for _ in range(2)])
    assert one[0]['id'] == two[0]['id'] and one[0]['seq'] == 1
    ingest = IngestTelemetry(store, TelemetryHub(), 'test-chirpstack', ChirpStackDecoder(decode_payload))
    async def polo(seq, at):
        return await ingest.execute(*make_uplink(struct.pack('<Bhb', seq, -80, 20), fPort=30, time=at.isoformat()))
    await polo(2, now + timedelta(seconds=1))
    assert (await store.dashboard('test-flight'))['commands'][0]['status'] == 'pending'
    await polo(1, now - timedelta(seconds=1))
    assert (await store.dashboard('test-flight'))['commands'][0]['status'] == 'pending'
    await polo(1, now + timedelta(minutes=16))
    assert (await store.dashboard('test-flight'))['commands'][0]['status'] == 'pending'
    await polo(1, now + timedelta(seconds=2))
    assert (await store.dashboard('test-flight'))['commands'][0]['status'] == 'executed'
    next_command, _ = await store.reserve_command('test-flight', str(uuid4()), 'PING', now + timedelta(seconds=3))
    assert next_command['seq'] == 2

async def test_expiry_and_sequence_exhaustion_do_not_reuse_or_resend(store):
    from app.infrastructure.database.models import CommandRow
    from sqlalchemy import select
    await setup_radio(store)
    now = datetime.now(timezone.utc)
    first, _ = await store.reserve_command('test-flight', str(uuid4()), 'PING', now - timedelta(minutes=16))
    assert (await store.dashboard('test-flight'))['commands'][0]['status'] == 'expired'
    second, _ = await store.reserve_command('test-flight', str(uuid4()), 'PING', now)
    assert second['seq'] == 2
    async with store.sessions.begin() as session:
        active = await session.scalar(select(CommandRow).where(CommandRow.id == second['id']))
        active.status = 'executed'
        active.data = {**active.data, 'status': 'executed'}
        for seq in range(3, 256):
            identifier, request = str(uuid4()), str(uuid4())
            data = {**first, 'id': identifier, 'clientRequestId': request, 'status': 'executed', 'seq': seq}
            session.add(CommandRow(id=identifier, mission_id='test-flight', client_request_id=request,
                kind='PING', status='executed', created_at=now, data=data))
    with pytest.raises(CommandConflict, match='Secuencias agotadas'):
        await store.reserve_command('test-flight', str(uuid4()), 'PING', now)

async def test_marco_endpoint_limits_supported_commands_and_preserves_csrf(store, db_url):
    from unittest.mock import AsyncMock
    await setup_radio(store)
    transport = AsyncMock()
    transport.supports = lambda mission: True
    app = create_app(Settings(database_url=db_url), store, command_transport=transport)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1') as client:
        dashboard = (await client.get('/api/v1/missions/test-flight/dashboard')).json()
        assert dashboard['commandSettings']['supportedTypes'] == ['PING', 'RELEASE_NOW']
        assert dashboard['commandSettings']['uplinkIntervalSeconds'] == 900
        request = str(uuid4())
        body = {'type': 'PING', 'clientRequestId': request}
        endpoint = '/api/v1/missions/test-flight/commands'
        assert (await client.post(endpoint, json=body)).status_code == 403
        headers = {'Origin': 'http://127.0.0.1:5173', 'X-CSRF-Token': dashboard['csrfToken'], 'Idempotency-Key': request}
        response = await client.post(endpoint, json=body, headers=headers)
        assert response.status_code == 202 and response.json()['seq'] == 1
        assert (await client.post(endpoint, json=body, headers=headers)).json()['id'] == response.json()['id']
        transport.send.assert_awaited_once()
        for kind in ('RELEASE_NOW', 'START_MISSION'):
            request = str(uuid4())
            response = await client.post(endpoint, json={'type': kind, 'clientRequestId': request}, headers={**headers, 'Idempotency-Key': request})
            assert response.status_code in (409, 422)
