import test from 'node:test'
import assert from 'node:assert/strict'
import { setImmediate } from 'node:timers/promises'
import {
  MAX_TELEMETRY,
  dataAgeSeconds,
  latestSample,
  mergeCommands,
  mergeTelemetry,
} from '../src/domain/mission.ts'
import {
  parseMessage,
  parseSnapshot,
  parseTelemetry,
} from '../src/infrastructure/http/validation.ts'
import { DemoMissionGateway } from '../src/infrastructure/demo/DemoMissionGateway.ts'
import { MissionController } from '../src/application/MissionController.ts'

const fixture = await new DemoMissionGateway().load(new AbortController().signal)
const sample = fixture.telemetry.at(-1)
const command = {
  id: 'cmd-1',
  missionId: fixture.mission.id,
  clientRequestId: 'request-1',
  type: 'PING',
  status: 'pending',
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  evidence: 'Recorded',
  simulated: false,
}
function fakeGateway(options = {}) {
  let emit = () => {}
  let status = () => {}
  let sends = 0
  let disconnects = 0
  const snapshot = structuredClone(fixture)
  snapshot.csrfToken = 'test-csrf'
  const gateway = {
    mode: 'live',
    load: async () => structuredClone(snapshot),
    subscribe: (message, connection) => {
      emit = message
      status = connection
      connection('connected')
      return () => {
        disconnects++
      }
    },
    sendCommand: async (type, clientRequestId) => {
      sends++
      if (options.fail) throw new Error('Lost response')
      return { ...command, type, clientRequestId }
    },
    predict: async () => {
      throw new Error('Provider unavailable')
    },
  }
  return {
    gateway,
    snapshot,
    emit: (message) => emit(message),
    status: (value) => status(value),
    get sends() {
      return sends
    },
    get disconnects() {
      return disconnects
    },
  }
}

test('invalid sensor values are unavailable, never zero or a valid GPS fix', () => {
  const parsed = parseTelemetry({
    ...sample,
    latitude: 100,
    humidityPct: 255,
    pressureHpa: 0,
    altitudeGpsM: 65535,
    temperatureC: -128,
    batteryV: Number.NaN,
  })
  for (const field of [
    'latitude',
    'longitude',
    'humidityPct',
    'pressureHpa',
    'altitudeGpsM',
    'temperatureC',
    'batteryV',
  ])
    assert.equal(parsed[field], null)
  assert.throws(
    () => parseTelemetry({ ...sample, receivedAt: '2026-10-01T12:00:00' }),
    /zona horaria/,
  )
  assert.throws(() => parseTelemetry({ ...sample, frameCounter: 1.5 }), /Contador/)
})
test('duplicates and late packets do not move the latest value backwards', () => {
  const first = { ...sample, id: 'old', receivedAt: '2026-10-01T12:00:00Z' }
  const last = { ...sample, id: 'new', receivedAt: '2026-10-01T12:00:02Z' }
  const middle = { ...sample, id: 'middle', receivedAt: '2026-10-01T12:00:01Z' }
  const merged = mergeTelemetry(
    [last],
    [middle, first, last, { ...middle, missionId: 'other', id: 'foreign' }],
    sample.missionId,
  )
  assert.deepEqual(
    merged.map((s) => s.id),
    ['old', 'middle', 'new'],
  )
  assert.equal(latestSample(merged).id, 'new')
  assert.equal(dataAgeSeconds(last, Date.parse('2026-10-01T12:00:12Z')), 10)
})
test('telemetry storage is bounded and preserves most recent samples', () => {
  const history = Array.from({ length: MAX_TELEMETRY + 20 }, (_, i) => ({
    ...sample,
    id: String(i),
    receivedAt: new Date(1700000000000 + i * 1000).toISOString(),
  }))
  const merged = mergeTelemetry([], history, sample.missionId)
  assert.equal(merged.length, MAX_TELEMETRY)
  assert.equal(merged[0].id, '20')
})
test('received and executed are distinct; late command state cannot regress', () => {
  const received = { ...command, status: 'received' }
  const pending = {
    ...command,
    updatedAt: new Date(Date.parse(command.updatedAt) + 500).toISOString(),
  }
  assert.equal(mergeCommands([received], [pending], command.missionId)[0].status, 'received')
  const executed = { ...pending, status: 'executed' }
  assert.equal(mergeCommands([received], [executed], command.missionId)[0].status, 'executed')
  assert.equal(
    mergeCommands([executed], [{ ...pending, status: 'rejected' }], command.missionId)[0].status,
    'executed',
  )
})
test('snapshot rejects mismatched missions and malformed permissions', () => {
  assert.equal(parseSnapshot(fixture, fixture.mission.id).telemetry.length, 157)
  assert.throws(() => parseSnapshot(fixture, 'another-mission'), /otra misión/)
  assert.throws(
    () =>
      parseSnapshot(
        { ...fixture, permissions: { canCommand: 'true', canPredict: true } },
        fixture.mission.id,
      ),
    /booleano/,
  )
  assert.throws(
    () =>
      parseSnapshot(
        { ...fixture, telemetry: [{ ...sample, missionId: 'foreign' }] },
        fixture.mission.id,
      ),
    /otra misión/,
  )
  assert.equal(parseMessage({ type: 'heartbeat' }), null)
  assert.throws(() => parseMessage({ type: 'unknown', data: {} }), /no compatible/)
})
test('controller merges real-time packets with snapshot, keeps data through disconnection', async () => {
  const f = fakeGateway()
  const controller = new MissionController(f.gateway)
  const stop = controller.start()
  const newer = { ...sample, id: 'stream', receivedAt: new Date(Date.now() + 1000).toISOString() }
  f.emit({ type: 'telemetry', data: newer })
  await setImmediate()
  assert.equal(latestSample(controller.getSnapshot().snapshot.telemetry).id, 'stream')
  f.status('offline')
  assert.equal(controller.getSnapshot().connection, 'offline')
  assert.equal(latestSample(controller.getSnapshot().snapshot.telemetry).id, 'stream')
  f.status('connected')
  await setImmediate()
  assert.equal(latestSample(controller.getSnapshot().snapshot.telemetry).id, 'stream')
  stop()
  assert.equal(f.disconnects, 1)
})
test('commands need recent data, operator permission and connected transport', async () => {
  const f = fakeGateway()
  const controller = new MissionController(f.gateway)
  const stop = controller.start()
  await setImmediate()
  f.status('offline')
  assert.equal(await controller.sendCommand('PING'), false)
  f.status('connected')
  f.snapshot.permissions.canCommand = false
  await controller.refresh()
  assert.equal(await controller.sendCommand('PING'), false)
  f.snapshot.permissions.canCommand = true
  f.snapshot.telemetry = f.snapshot.telemetry.map((s) => ({
    ...s,
    receivedAt: new Date(Date.now() - 120000).toISOString(),
  }))
  const stale = new MissionController(f.gateway)
  const stopStale = stale.start()
  await setImmediate()
  assert.equal(await stale.sendCommand('PING'), false)
  assert.equal(f.sends, 0)
  stopStale()
  stop()
})
test('release requires explicit confirmation and cannot be queued twice', async () => {
  const f = fakeGateway()
  const controller = new MissionController(f.gateway)
  const stop = controller.start()
  await setImmediate()
  assert.equal(await controller.sendCommand('RELEASE_NOW'), false)
  assert.equal(await controller.sendCommand('RELEASE_NOW', true), true)
  assert.equal(controller.getSnapshot().snapshot.commands[0].status, 'pending')
  assert.equal(await controller.sendCommand('RELEASE_NOW', true), false)
  assert.equal(f.sends, 1)
  assert.equal(controller.getSnapshot().snapshot.mission.phase, 'ascending')
  stop()
})
test('lost command response is never retried automatically', async () => {
  const f = fakeGateway({ fail: true })
  const controller = new MissionController(f.gateway)
  const stop = controller.start()
  await setImmediate()
  assert.equal(await controller.sendCommand('PING'), false)
  await setImmediate()
  assert.equal(f.sends, 1)
  assert.match(controller.getSnapshot().actionError, /Verifica la bitácora/)
  stop()
})
test('prediction failures preserve the last valid prediction', async () => {
  const f = fakeGateway()
  const controller = new MissionController(f.gateway)
  const stop = controller.start()
  await setImmediate()
  const id = controller.getSnapshot().snapshot.prediction.id
  assert.equal(await controller.predict(fixture.prediction.parameters), false)
  assert.equal(controller.getSnapshot().snapshot.prediction.id, id)
  stop()
})
test('cleanup ignores late messages and obsolete history requests', async () => {
  const f = fakeGateway()
  const controller = new MissionController(f.gateway)
  const stop = controller.start()
  await setImmediate()
  const before = controller.getSnapshot()
  stop()
  f.emit({ type: 'telemetry', data: { ...sample, id: 'late' } })
  assert.equal(controller.getSnapshot(), before)
})

test('the view cleanup disposes a connection restarted with Retry', async () => {
  const f = fakeGateway()
  const controller = new MissionController(f.gateway)
  const unmount = controller.start()
  await setImmediate()
  controller.start()
  await setImmediate()
  assert.equal(f.disconnects, 1)
  unmount()
  assert.equal(f.disconnects, 2)
  const before = controller.getSnapshot()
  f.emit({ type: 'telemetry', data: { ...sample, id: 'after-unmount' } })
  assert.equal(controller.getSnapshot(), before)
})

test('a failed refresh preserves readings but revokes action permissions', async () => {
  const f = fakeGateway()
  const controller = new MissionController(f.gateway)
  const stop = controller.start()
  await setImmediate()
  const before = controller.getSnapshot().snapshot.telemetry
  f.gateway.load = async () => {
    throw new Error('Session expired')
  }
  await controller.refresh()
  assert.deepEqual(controller.getSnapshot().snapshot.telemetry, before)
  assert.equal(controller.getSnapshot().snapshot.permissions.canCommand, false)
  assert.equal(controller.getSnapshot().snapshot.csrfToken, null)
  assert.equal(await controller.sendCommand('PING'), false)
  stop()
})
