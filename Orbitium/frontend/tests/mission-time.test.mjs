import test from 'node:test'
import assert from 'node:assert/strict'
import { agsDateInput, agsDateTime, agsDateToUtc } from '../src/presentation/missionTime.ts'

test('AGS launch input round trips UTC−06:00 across midnight and summer without device timezone', () => {
  for (const [input, utc] of [
    ['2026-11-01T08:30', '2026-11-01T14:30:00.000Z'],
    ['2026-07-01T23:45', '2026-07-02T05:45:00.000Z'],
    ['2026-01-01T00:00', '2026-01-01T06:00:00.000Z'],
  ]) {
    assert.equal(agsDateToUtc(input), utc)
    assert.equal(agsDateInput(utc), input)
    assert.match(agsDateTime(utc), new RegExp(input.slice(11)))
  }
  assert.equal(agsDateInput(null), '')
  assert.equal(agsDateTime(undefined), '—')
  assert.equal(agsDateInput('2026-11-01T23:30:00+09:00'), '2026-11-01T08:30')
})
