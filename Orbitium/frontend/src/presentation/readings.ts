import type { Telemetry } from '../domain/mission.ts'

const fields = ['latitude', 'longitude', 'altitudeGpsM', 'altitudeBarometricM',
  'relativeAltitudeM', 'verticalSpeedMs', 'temperatureC', 'humidityPct',
  'pressureHpa', 'batteryV', 'rssiDbm', 'snrDb'] as const

/** Display projection only: archived packets and their timestamps stay untouched. */
export function latestReadings(samples: Telemetry[], missionId: string) {
  const ordered = samples.filter(s => s.missionId === missionId)
    .sort((a, b) => Date.parse(b.receivedAt) - Date.parse(a.receivedAt) || b.id.localeCompare(a.id))
  let values: Telemetry | null = ordered[0] ? { ...ordered[0], device: null, radio: null } : null
  const observedAt: Partial<Record<typeof fields[number], string>> = {}
  if (!values) return { values, observedAt }
  for (const key of fields) {
    const source = ordered.find(s => s.packet
      ? s.packet.presentFields?.includes(key)
      : typeof s[key] === 'number' && Number.isFinite(s[key]))
    values = { ...values, [key]: source?.[key] ?? null }
    if (source) observedAt[key] = source.receivedAt
  }
  // Merge nested details field by field, preserving reported false and zero.
  for (const sample of [...ordered].reverse()) {
    if (sample.device) values.device = { ...values.device,
      ...Object.fromEntries(Object.entries(sample.device).filter(([k, v]) => sample.packet
        ? sample.packet.presentDeviceFields?.includes(k) : v != null)) } as Telemetry['device']
    if (sample.radio) values.radio = { ...values.radio,
      ...Object.fromEntries(Object.entries(sample.radio).filter(([, v]) => v != null)) } as Telemetry['radio']
  }
  return { values, observedAt }
}

/** Plot only measurements actually received; never forward-fill chart data. */
export function telemetryPoints(samples: Telemetry[], key: keyof Telemetry, scale = 1): [number, number][] {
  return samples.flatMap(sample => {
    const time = Date.parse(sample.receivedAt)
    const value = sample[key]
    return Number.isFinite(time) && typeof value === 'number' && Number.isFinite(value)
      ? [[time, value * scale] as [number, number]] : []
  }).sort((a, b) => a[0] - b[0])
}
