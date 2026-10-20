import test from 'node:test'
import assert from 'node:assert/strict'
import { aggregateSamples, chartInterval } from '../src/presentation/chartReadings.ts'

const packet = (seconds, values = {}) => ({ id: String(seconds), missionId: 'synthetic',
  receivedAt: new Date(Date.UTC(2026, 9, 19) + seconds * 1000).toISOString(), ...values })

test('chart summary intervals cover the selected period with exact boundary handling', () => {
  assert.equal(chartInterval([]), 20_000)
  assert.equal(chartInterval([packet(1200), packet(0)]), 20_000)
  assert.equal(chartInterval([packet(0), packet(1201)]), 180_000)
  assert.equal(chartInterval([packet(0), packet(7200)]), 180_000)
  assert.equal(chartInterval([packet(0), packet(7201), { receivedAt: 'invalid' }]), 240_000)
})

test('chart summaries use per-sensor medians, retain zero and unknowns, and do not alter raw packets', () => {
  const samples = [packet(21, { temperatureC: 10 }), packet(2, { temperatureC: 100, batteryV: 0 }),
    packet(1, { temperatureC: 2, batteryV: null }), packet(3, { temperatureC: 4, batteryV: NaN }),
    packet(20, { temperatureC: 20 }), { receivedAt: 'invalid', temperatureC: 1000 }]
  const original = structuredClone(samples)
  const result = aggregateSamples(samples, 20_000, ['temperatureC', 'batteryV', 'humidityPct'])
  assert.deepEqual(result.map(({ receivedAt, temperatureC, batteryV, humidityPct }) =>
    ({ receivedAt, temperatureC, batteryV, humidityPct })), [
    { receivedAt: packet(0).receivedAt, temperatureC: 4, batteryV: 0, humidityPct: null },
    { receivedAt: packet(20).receivedAt, temperatureC: 15, batteryV: null, humidityPct: null },
  ])
  assert.deepEqual(samples, original)
  assert.deepEqual(aggregateSamples([], 20_000, ['temperatureC']), [])
})
