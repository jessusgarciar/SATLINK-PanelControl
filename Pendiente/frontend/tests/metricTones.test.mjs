import test from 'node:test'
import assert from 'node:assert/strict'
import { batteryTone, rssiTone, temperatureTone } from '../src/presentation/metricTones.ts'

test('temperature tone changes at the agreed cold, warm, and hot boundaries', () => {
  assert.equal(temperatureTone(15), 'blue')
  assert.equal(temperatureTone(15.1), 'amber')
  assert.equal(temperatureTone(24.9), 'amber')
  assert.equal(temperatureTone(25), 'red')
})

test('battery tone changes at critical and low voltage boundaries', () => {
  assert.equal(batteryTone(1.5), 'red')
  assert.equal(batteryTone(2.99), 'red')
  assert.equal(batteryTone(3), 'amber')
  assert.equal(batteryTone(3.39), 'amber')
  assert.equal(batteryTone(3.4), 'green')
})

test('RSSI tone treats stronger, less-negative readings as better signal', () => {
  assert.equal(rssiTone(-89), 'green')
  assert.equal(rssiTone(-90), 'green')
  assert.equal(rssiTone(-90.1), 'amber')
  assert.equal(rssiTone(-109.9), 'amber')
  assert.equal(rssiTone(-110), 'red')
})

test('missing and non-finite measurements remain neutral', () => {
  for (const tone of [temperatureTone, batteryTone, rssiTone]) {
    assert.equal(tone(null), 'neutral')
    assert.equal(tone(undefined), 'neutral')
    assert.equal(tone(Number.NaN), 'neutral')
    assert.equal(tone(Number.POSITIVE_INFINITY), 'neutral')
  }
})
