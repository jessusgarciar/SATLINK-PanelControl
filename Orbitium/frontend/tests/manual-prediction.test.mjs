import test from 'node:test'
import assert from 'node:assert/strict'
import { predictionUnavailableReason, predictionParametersChanged } from '../src/domain/mission.ts'
import { DemoMissionGateway } from '../src/infrastructure/demo/DemoMissionGateway.ts'
import { HttpMissionGateway } from '../src/infrastructure/http/HttpMissionGateway.ts'

const now = Date.now()
const fixture = await new DemoMissionGateway().load(new AbortController().signal)
const launch = { latitude: 21.5, longitude: -101.5, altitudeM: 2300 }
const parameters = {
  ...fixture.prediction.parameters, mode: 'planned', launch, launchAltitudeReference: 'MSL',
  launchDatetime: new Date(now + 3600000).toISOString(),
}
const snapshot = {
  ...fixture, mission: { ...fixture.mission, phase: 'unknown' },
  permissions: { canPredict: true, canCommand: false }, csrfToken: 'csrf-manual',
  predictionSettings: { enabled: true, launchAltitudeReference: 'unknown', gpsAltitudeReference: 'unknown', nextAllowedAt: null },
}

test('manual planning uses explicit MSL even when the configured launch datum is unknown', () => {
  assert.equal(predictionUnavailableReason(snapshot, parameters, now), null)
  assert.equal(predictionUnavailableReason(snapshot, { ...parameters, launch: { latitude: 0, longitude: 0, altitudeM: 0 } }, now), null)
  for (const origin of [
    { ...launch, latitude: 91 }, { ...launch, longitude: -181 },
    { ...launch, altitudeM: -501 }, { ...launch, altitudeM: Number.NaN },
  ]) assert.match(predictionUnavailableReason(snapshot, { ...parameters, launch: origin }, now), /coordenadas/)
  assert.match(predictionUnavailableReason(snapshot, { ...parameters, launchAltitudeReference: undefined }, now), /altitud/)
  assert.equal(snapshot.mission.phase, 'unknown')
  assert.deepEqual(snapshot.mission.launch, fixture.mission.launch)
})

test('manual parameter changes compare coordinate values rather than object key order', () => {
  const equivalent = { ...parameters, launch: { altitudeM: 2300, longitude: -101.5, latitude: 21.5 } }
  assert.equal(predictionParametersChanged(parameters, equivalent, false), false)
  assert.equal(predictionParametersChanged(parameters, { ...equivalent, launch: { ...launch, altitudeM: 2400 } }, false), true)
})

test('HTTP preserves manual origin and MSL in both request and parsed prediction', async (t) => {
  const original = globalThis.fetch
  t.after(() => { globalThis.fetch = original })
  let sent
  globalThis.fetch = async (url, options) => {
    sent = { url, options, body: JSON.parse(options.body) }
    return new Response(JSON.stringify({
      ...fixture.prediction, source: 'tawhiri', parameters: sent.body,
      context: { mode: 'planned', origin: launch, originAt: parameters.launchDatetime,
        telemetryId: null, dataset: '2026100700', altitudeReference: 'MSL' },
    }), { headers: { 'Content-Type': 'application/json' } })
  }
  const result = await new HttpMissionGateway('/api/v1', fixture.mission.id).predict(parameters, 'csrf-manual')
  assert.deepEqual(sent.body, {
    mode: 'planned', launchDatetime: parameters.launchDatetime, launch, launchAltitudeReference: 'MSL',
    targetRelativeAltitudeM: parameters.targetRelativeAltitudeM, ascentRateMs: parameters.ascentRateMs,
    descentRateMs: parameters.descentRateMs,
  })
  assert.equal(sent.options.headers['X-CSRF-Token'], 'csrf-manual')
  assert.equal(sent.options.credentials, 'include')
  assert.deepEqual(result.parameters.launch, launch)
  assert.equal(result.parameters.launchAltitudeReference, 'MSL')
  assert.deepEqual(result.context.origin, launch)
})

test('demo planning starts at manual origin and requested time without changing mission', async () => {
  const gateway = new DemoMissionGateway()
  const before = await gateway.load(new AbortController().signal)
  const result = await gateway.predict(parameters)
  const first = result.trajectory[0]
  assert.equal(result.source, 'demo')
  assert.deepEqual({ latitude: first.latitude, longitude: first.longitude, altitudeM: first.altitudeM }, launch)
  assert.equal(first.time, parameters.launchDatetime)
  assert.equal(result.release.altitudeM, launch.altitudeM + parameters.targetRelativeAltitudeM)
  assert.deepEqual(result.context.origin, launch)
  const after = await gateway.load(new AbortController().signal)
  assert.deepEqual(after.mission, before.mission)
  assert.deepEqual(after.telemetry, before.telemetry)
})
