import type { Telemetry } from './mission.ts'

export const WINDOW_OPTIONS = [
  { key: '15m', label: '15 min', seconds: 900 },
  { key: '1h', label: '1 h', seconds: 3600 },
  { key: '6h', label: '6 h', seconds: 21600 },
  { key: '24h', label: '24 h', seconds: 86400 },
  { key: 'all', label: 'Todo', seconds: null },
] as const
export type WindowKey = (typeof WINDOW_OPTIONS)[number]['key']
export interface TimeRange { from: string | null; to: string }
export interface TelemetryWindow extends TimeRange {
  total: number
  series: Telemetry[]
  track: Telemetry[]
}
export interface HistoryPage { items: Telemetry[]; nextCursor: string | null }
export function timeRange(key: WindowKey, now: number): TimeRange {
  const seconds = WINDOW_OPTIONS.find((option) => option.key === key)!.seconds
  return { from: seconds === null ? null : new Date(now - seconds * 1000).toISOString(), to: new Date(now).toISOString() }
}
export function inRange(sample: Telemetry, range: TimeRange): boolean {
  const time = Date.parse(sample.receivedAt)
  return (range.from === null || time >= Date.parse(range.from)) && time < Date.parse(range.to)
}
// Se agregó esta reducción porque en el Ejercicio 10 se conserva la posición actual.
export function decimate<T>(items: T[], maximum: number): T[] {
  if (items.length <= maximum) return items
  return Array.from({ length: maximum }, (_, i) => items[Math.floor(i * (items.length - 1) / (maximum - 1))])
}
export function demoWindow(samples: Telemetry[], range: TimeRange): TelemetryWindow {
  const items = samples.filter((sample) => inRange(sample, range))
  return { ...range, total: items.length, series: decimate(items, 600), track: decimate(items.filter((t) => t.latitude !== null && t.longitude !== null), 500) }
}
export function demoCsv(samples: Telemetry[]): string {
  const fields = ['id', 'missionId', 'receivedAt', 'frameCounter', 'latitude', 'longitude', 'altitudeGpsM', 'relativeAltitudeM', 'altitudeBarometricM', 'verticalSpeedMs', 'temperatureC', 'humidityPct', 'pressureHpa', 'batteryV', 'rssiDbm', 'snrDb'] as const
  const deviceFields = ['gpsActive', 'gpsFix', 'satellites', 'batteryPct', 'charging', 'usbPowered'] as const
  const radioFields = ['gatewayId', 'frequencyHz', 'dataRate', 'fPort'] as const
  const quote = (value: unknown) => '"' + String(value ?? '').replaceAll('"', '""') + '"'
  return '\uFEFF' + [...fields, ...deviceFields.map((key) => 'device_' + key), ...radioFields.map((key) => 'radio_' + key), 'source', 'applicationId', 'devEui', 'raw_json'].join(',') + '\r\n' + samples.map((t) => [...fields.map((key) => t[key]), ...deviceFields.map((key) => t.device?.[key]), ...radioFields.map((key) => t.radio?.[key]), 'demo', '', '0000000000000000', ''].map(quote).join(',')).join('\r\n') + '\r\n'
}
