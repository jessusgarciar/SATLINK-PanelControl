import test from 'node:test'
import assert from 'node:assert/strict'
import { setImmediate } from 'node:timers/promises'
import { predictionUnavailableReason, predictionParametersChanged } from '../src/domain/mission.ts'
import { parsePrediction, parseSnapshot } from '../src/infrastructure/http/validation.ts'
import { DemoMissionGateway } from '../src/infrastructure/demo/DemoMissionGateway.ts'
import { HttpMissionGateway } from '../src/infrastructure/http/HttpMissionGateway.ts'
import { MissionController } from '../src/application/MissionController.ts'

const now = Date.now()
const fixture = await new DemoMissionGateway().load(new AbortController().signal)
const parameters = { ...fixture.prediction.parameters, mode: 'planned', launchDatetime: new Date(now + 3600000).toISOString() }
const settings = { enabled: true, launchAltitudeReference: 'MSL', gpsAltitudeReference: 'MSL', nextAllowedAt: null }
const snapshot = { ...fixture, mission: { ...fixture.mission, phase: 'unknown' }, permissions: { canPredict: true, canCommand: false }, csrfToken: 'csrf-test', predictionSettings: settings }
const real = { ...fixture.prediction, source: 'tawhiri', parameters, context: {
  mode: 'planned', origin: fixture.mission.launch, originAt: parameters.launchDatetime,
  telemetryId: null, dataset: '2026100400', altitudeReference: 'MSL',
} }

test('real parameter changes ignore demo winds, object order and equivalent time zones', () => {
  const equivalent = { descentRateMs: parameters.descentRateMs, ...parameters, ascentWindMs: 0,
    launchDatetime: parameters.launchDatetime.replace('Z', '+00:00') }
  assert.equal(predictionParametersChanged(parameters, equivalent, false), false)
  assert.equal(predictionParametersChanged(parameters, equivalent, true), true)
  assert.equal(predictionParametersChanged(parameters, { ...equivalent, ascentRateMs: 9 }, false), true)
})

test('manual prediction context permits unknown phase without declaring a physical phase', () => {
  assert.equal(predictionUnavailableReason(snapshot, parameters, now), null)
  assert.equal(snapshot.mission.phase, 'unknown')
  for (const phase of ['descending', 'landed'])
    assert.match(predictionUnavailableReason({ ...snapshot, mission: { ...snapshot.mission, phase } }, parameters, now), /descenso/)
  assert.match(predictionUnavailableReason(snapshot, { ...parameters, launchDatetime: '2026-01-01T00:00:00Z' }, now), /futura/)
  assert.match(predictionUnavailableReason({ ...snapshot, predictionSettings: { ...settings, nextAllowedAt: new Date(now + 60000).toISOString() } }, parameters, now), /60 s/)
})

test('ascending uses latest valid recent GPS, verified datum, and target relative to original launch', () => {
  const p = { ...parameters, mode: 'ascending', launchDatetime: undefined }
  const latest = { ...fixture.telemetry.at(-1), receivedAt: new Date(now).toISOString(), latitude: 21, longitude: -102, altitudeGpsM: 5000, device: { gpsFix: true } }
  const s = { ...snapshot, telemetry: [latest] }
  assert.equal(predictionUnavailableReason(s, p, now), null)
  assert.match(predictionUnavailableReason({ ...s, predictionSettings: { ...settings, gpsAltitudeReference: 'unknown' } }, p, now), /GPS/)
  for (const change of [{ latitude: null }, { device: { gpsFix: false } }, { receivedAt: new Date(now - 4000000).toISOString() }, { receivedAt: new Date(now + 6000).toISOString() }])
    assert.match(predictionUnavailableReason({ ...s, telemetry: [{ ...latest, ...change }] }, p, now), /reciente/)
  assert.match(predictionUnavailableReason({ ...s, telemetry: [{ ...latest, altitudeGpsM: 20000 }] }, p, now), /superar/)
})

test('real predictions require context and a usable trajectory while legacy demo remains readable', () => {
  assert.equal(parsePrediction(real).context.dataset, '2026100400')
  assert.equal(parsePrediction(fixture.prediction).source, 'demo')
  assert.throws(() => parsePrediction({ ...real, context: undefined }), /contexto/)
  assert.throws(() => parsePrediction({ ...real, trajectory: [] }), /incompleta/)
  assert.equal(parseSnapshot({ ...snapshot, prediction: real }, snapshot.mission.id).predictionSettings.enabled, true)
})

test('HTTP prediction sends explicit context and CSRF, omits demo winds and ascending launchDatetime', async (t) => {
  const original = globalThis.fetch
  t.after(() => { globalThis.fetch = original })
  const calls = []
  globalThis.fetch = async (_url, options) => {
    const body = JSON.parse(options.body)
    calls.push({ body, options })
    return new Response(JSON.stringify({ ...real, parameters: body, context: { ...real.context, mode: body.mode, telemetryId: body.mode === 'ascending' ? 'packet-test' : null } }), { headers: { 'Content-Type': 'application/json' } })
  }
  const gateway = new HttpMissionGateway('/api/v1', fixture.mission.id)
  await gateway.predict(parameters, 'csrf-test')
  assert.deepEqual(Object.keys(calls[0].body).sort(), ['ascentRateMs', 'descentRateMs', 'launchDatetime', 'mode', 'targetRelativeAltitudeM'])
  assert.equal(calls[0].options.headers['X-CSRF-Token'], 'csrf-test')
  await gateway.predict({ ...parameters, mode: 'ascending' }, 'csrf-test')
  assert.equal('launchDatetime' in calls[1].body, false)
  globalThis.fetch = async () => new Response(JSON.stringify({ ...real, source: 'demo' }), { headers: { 'Content-Type': 'application/json' } })
  await assert.rejects(gateway.predict(parameters, 'csrf-test'), /real/)
})

test('provider failure preserves real prediction and refreshes persistent attempt cooldown', async () => {
  let calls = 0
  const s = { ...snapshot, prediction: real }
  const gateway = {
    mode: 'live', load: async () => structuredClone(s),
    subscribe: (_message, status) => { status('connected'); return () => {} },
    predict: async () => {
      calls++
      s.predictionSettings = { ...settings, nextAllowedAt: new Date(Date.now() + 60000).toISOString() }
      throw new Error('Tawhiri timeout')
    },
  }
  const controller = new MissionController(gateway)
  const stop = controller.start()
  await setImmediate()
  assert.equal(await controller.predict(parameters), false)
  assert.equal(controller.getSnapshot().snapshot.prediction.id, real.id)
  assert.match(controller.getSnapshot().actionError, /timeout/)
  assert.equal(await controller.predict(parameters), false)
  assert.equal(calls, 1)
  assert.equal(controller.getSnapshot().snapshot.mission.phase, 'unknown')
  stop()
})
