import test from 'node:test'
import assert from 'node:assert/strict'
import { setImmediate } from 'node:timers/promises'
import { DemoMissionGateway } from '../src/infrastructure/demo/DemoMissionGateway.ts'
import { MissionController } from '../src/application/MissionController.ts'
import { parseSnapshot } from '../src/infrastructure/http/validation.ts'
import { mergePredictionHistory, modePredictions, missionPredictionDraft } from '../src/domain/predictionWorkspace.ts'

const fixture = await new DemoMissionGateway().load(new AbortController().signal)
const make = (mode, index) => ({ ...fixture.prediction, id: `${mode}-${index}`,
  generatedAt: new Date(Date.now() + index * 1000).toISOString(),
  parameters: { ...fixture.prediction.parameters, mode } })

test('latest and previous results remain separate by mode, with bounded duplicate-free history', () => {
  const all = ['planned', 'ascending'].flatMap(mode => [0, 1, 2].map(index => make(mode, index)))
  const history = mergePredictionHistory(all, all)
  assert.equal(history.length, 4)
  const snapshot = { ...fixture, prediction: all.at(-1), predictionHistory: history }
  assert.deepEqual(modePredictions(snapshot, 'planned').map(p => p.id), ['planned-2', 'planned-1'])
  assert.deepEqual(modePredictions(snapshot, 'ascending').map(p => p.id), ['ascending-2', 'ascending-1'])
  assert.deepEqual(modePredictions({ ...fixture, prediction: make('planned', 0) }, 'ascending'), [])
})

test('mission settings seed forms, expired launch dates are renewed, and drafts do not mutate mission', () => {
  const now = Date.now()
  const mission = { ...fixture.mission, nominalAscentMs: 8, nominalDescentMs: 9, plannedLaunchAt: '2020-01-01T00:00:00Z' }
  const draft = missionPredictionDraft(mission, 'planned', now)
  assert.equal(draft.ascentRateMs, 8)
  assert.equal(draft.descentRateMs, 9)
  assert.ok(Date.parse(draft.launchDatetime) > now)
  draft.launch.latitude = 0
  assert.notEqual(mission.launch.latitude, 0)
  const ascending = missionPredictionDraft(mission, 'ascending', now)
  assert.equal(ascending.launch, undefined)
  assert.equal(ascending.launchDatetime, undefined)
})

test('history parser rejects other missions and oversized history, accepts older servers', () => {
  assert.deepEqual(parseSnapshot(fixture, fixture.mission.id).predictionHistory, [])
  assert.throws(() => parseSnapshot({ ...fixture, predictionHistory: [{ ...make('planned', 0), missionId: 'other' }] }, fixture.mission.id), /otra misión/)
  assert.throws(() => parseSnapshot({ ...fixture, predictionHistory: Array(5).fill(make('planned', 0)) }, fixture.mission.id), /grande/)
})

test('changing each velocity makes a new request; previous success survives failure and refresh', async () => {
  const requests = []
  const data = { ...fixture, prediction: make('planned', 0), predictionHistory: [make('ascending', 0)] }
  let failure = false
  const gateway = { mode: 'demo', load: async () => structuredClone(data),
    subscribe: (_receive, status) => { status('connected'); return () => {} },
    predict: async parameters => {
      requests.push(structuredClone(parameters))
      if (failure) throw new Error('Synthetic provider failure')
      return { ...make(parameters.mode, requests.length), parameters }
    } }
  const controller = new MissionController(gateway)
  const stop = controller.start()
  await setImmediate()
  const initial = { ...fixture.prediction.parameters, mode: 'planned' }
  assert.equal(await controller.predict({ ...initial, ascentRateMs: 6 }), true)
  assert.equal(await controller.predict({ ...initial, descentRateMs: 8 }), true)
  assert.equal(requests[0].ascentRateMs, 6)
  assert.equal(requests[1].descentRateMs, 8)
  const before = modePredictions(controller.getSnapshot().snapshot, 'planned')
  assert.equal(before.length, 2)
  failure = true
  assert.equal(await controller.predict({ ...initial, ascentRateMs: 7 }), false)
  assert.equal(controller.getSnapshot().actionError, null, 'prediction errors must not appear as command failures')
  assert.match(controller.getSnapshot().predictionActionError, /Synthetic provider failure/)
  assert.deepEqual(modePredictions(controller.getSnapshot().snapshot, 'planned'), before)
  assert.equal(modePredictions(controller.getSnapshot().snapshot, 'ascending')[0].id, 'ascending-0')
  stop()
})
