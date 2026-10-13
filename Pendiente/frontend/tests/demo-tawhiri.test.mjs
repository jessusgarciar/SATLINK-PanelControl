import test from 'node:test'
import assert from 'node:assert/strict'
import { DemoMissionGateway } from '../src/infrastructure/demo/DemoMissionGateway.ts'
import { DemoPredictionClient } from '../src/infrastructure/http/DemoPredictionClient.ts'
import { MissionController } from '../src/application/MissionController.ts'

test('demo sends its GPS to the dedicated prediction route without winds or commands', async t => {
  const original = globalThis.fetch
  t.after(() => { globalThis.fetch = original })
  const snapshot = await new DemoMissionGateway().load(new AbortController().signal)
  let sent
  globalThis.fetch = async (url, options) => {
    sent = { url, options, body: JSON.parse(options.body) }
    return Response.json({ ...snapshot.prediction, source: 'tawhiri', parameters: sent.body.parameters,
      context: { mode: 'ascending', origin: { latitude: sent.body.sample.latitude, longitude: sent.body.sample.longitude,
        altitudeM: sent.body.sample.altitudeM }, originAt: sent.body.sample.time, telemetryId: null,
        dataset: '2026100700', altitudeReference: 'MSL', inputSource: 'simulated' } })
  }
  const result = await new DemoPredictionClient().predict({ ...snapshot.prediction.parameters, mode: 'ascending' },
    'demo-csrf', snapshot.telemetry.at(-1), 'ascending')
  assert.equal(sent.url, '/api/v1/demo/predictions')
  assert.equal(sent.options.headers['X-CSRF-Token'], 'demo-csrf')
  assert.equal(sent.body.phase, 'ascending')
  assert.equal(sent.body.sample.altitudeM, snapshot.telemetry.at(-1).altitudeGpsM)
  assert.equal('ascentWindMs' in sent.body.parameters, false)
  assert.equal('launchDatetime' in sent.body.parameters, false)
  assert.equal(result.context.inputSource, 'simulated')
})

test('backend failure retains visual demo and its last real prediction without a fake fallback', async () => {
  const local = await new DemoMissionGateway().load(new AbortController().signal)
  const real = { ...local.prediction, source: 'tawhiri' }
  let offline = false
  const client = { session: async () => {
    if (offline) throw new Error('offline')
    return { enabled: true, csrfToken: 'csrf', nextAllowedAt: null, prediction: real }
  }, predict: async () => { throw new Error('Tawhiri failed') } }
  const gateway = new DemoMissionGateway(true, client)
  const before = await gateway.load(new AbortController().signal)
  await assert.rejects(gateway.predict({ ...local.prediction.parameters, mode: 'ascending' }, 'csrf'), /failed/)
  offline = true
  const after = await gateway.load(new AbortController().signal)
  assert.deepEqual(after.telemetry, before.telemetry)
  assert.equal(after.prediction.source, 'tawhiri')
  assert.equal(after.permissions.canPredict, false)
  assert.equal(after.permissions.canCommand, true)
  assert.match(after.predictionError, /backend/)
})

test('controller enforces real cooldown in demo before sending another provider request', async () => {
  let calls = 0
  const gateway = new DemoMissionGateway(true, {
    session: async () => ({ enabled: true, csrfToken: 'csrf', nextAllowedAt: new Date(Date.now() + 60000).toISOString(), prediction: null }),
    predict: async () => { calls++; throw new Error('must not call') },
  })
  const controller = new MissionController(gateway)
  await controller.refresh()
  assert.equal(await controller.predict({ ...gateway.defaults(), mode: 'ascending' }), false)
  assert.equal(calls, 0)
  assert.match(controller.getSnapshot().actionError, /Espera/)
})
