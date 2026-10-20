import test from 'node:test'
import assert from 'node:assert/strict'
import { latestReadings, telemetryPoints } from '../src/presentation/readings.ts'

const empty = { missionId: 'test', latitude: null, longitude: null, altitudeGpsM: null,
  altitudeBarometricM: null, relativeAltitudeM: null, verticalSpeedMs: null,
  temperatureC: null, humidityPct: null, pressureHpa: null, batteryV: null,
  rssiDbm: null, snrDb: null, device: null, radio: null }
const packet = (second, data) => ({ ...empty, id: String(second), frameCounter: second,
  receivedAt: `2026-10-15T12:00:${String(second).padStart(2, '0')}Z`, ...data })
const position = packet(0, { latitude: 20, longitude: -100, altitudeGpsM: 2000, relativeAltitudeM: 100,
  device: { gpsFix: true, gpsActive: null, satellites: null, batteryPct: null, charging: null, usbPowered: null } })
const environment = packet(20, { temperatureC: 25, humidityPct: 50, pressureHpa: 800, batteryV: 3.7,
  device: { gpsFix: true, gpsActive: true, satellites: 9, batteryPct: 0, charging: false, usbPowered: false } })
const navigation = packet(40, { verticalSpeedMs: 0, rssiDbm: -80 })

test('alternating packets retain last readings with their original ages and preserve false/zero', () => {
  const packets = [navigation, position, environment]
  const original = structuredClone(packets)
  const { values, observedAt } = latestReadings(packets, 'test')
  assert.equal(values.altitudeGpsM, 2000)
  assert.equal(values.temperatureC, 25)
  assert.equal(values.humidityPct, 50)
  assert.equal(values.pressureHpa, 800)
  assert.equal(values.batteryV, 3.7)
  assert.equal(values.verticalSpeedMs, 0)
  assert.equal(values.rssiDbm, -80)
  assert.equal(values.device.charging, false)
  assert.equal(values.device.batteryPct, 0)
  assert.equal(values.device.satellites, 9)
  assert.equal(values.receivedAt, navigation.receivedAt)
  assert.equal(observedAt.altitudeGpsM, position.receivedAt)
  assert.equal(observedAt.temperatureC, environment.receivedAt)
  assert.deepEqual(packets, original)
})

test('new readings replace older values without mixing missions; empty fields remain unknown', () => {
  const { values } = latestReadings([position, environment, packet(50, { temperatureC: 26 }),
    packet(59, { missionId: 'other', batteryV: 4.2 })], 'test')
  assert.equal(values.temperatureC, 26)
  assert.equal(values.batteryV, 3.7)
  assert.equal(values.verticalSpeedMs, null)
  assert.equal(latestReadings([], 'test').values, null)
})

test('chart points retain reception times and omit unrelated empty packets without inventing values', () => {
  const secondPosition = packet(59, { altitudeGpsM: 2010 })
  assert.deepEqual(telemetryPoints([navigation, secondPosition, environment, position], 'altitudeGpsM', 0.001),
    [[Date.parse(position.receivedAt), 2], [Date.parse(secondPosition.receivedAt), 2.0100000000000002]])
  assert.deepEqual(telemetryPoints([position, environment, navigation], 'verticalSpeedMs'),
    [[Date.parse(navigation.receivedAt), 0]])
  assert.deepEqual(telemetryPoints([packet(1, { temperatureC: NaN }), packet(2, { receivedAt: 'invalid', temperatureC: 2 })], 'temperatureC'), [])
})
