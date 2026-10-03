/** Units are explicit. Derived values are supplied by the backend, never inferred by the UI. */
export type FlightPhase = 'preflight' | 'ascending' | 'descending' | 'landed' | 'unknown'
export type CommandType =
  | 'PING'
  | 'STATUS'
  | 'TELEMETRY'
  | 'BEACON_ON'
  | 'BEACON_OFF'
  | 'RELEASE_NOW'
export type CommandStatus = 'pending' | 'sent' | 'received' | 'executed' | 'rejected' | 'expired'
export type ConnectionStatus = 'connecting' | 'connected' | 'reconnecting' | 'offline'

export interface Position {
  latitude: number
  longitude: number
  altitudeM: number
}
export interface Mission {
  id: string
  name: string
  updatedAt: string
  startedAt: string | null
  endedAt: string | null
  phase: FlightPhase
  launch: Position
  launchLabel: string
  targetRelativeAltitudeM: number
  nominalAscentMs: number
  nominalDescentMs: number
  watchdogSeconds: number
  staleAfterSeconds: number
  deviceEui: string
  region: string
  beaconOn: boolean | null
}
export interface Telemetry {
  id: string
  missionId: string
  receivedAt: string
  frameCounter: number
  latitude: number | null
  longitude: number | null
  altitudeGpsM: number | null
  altitudeBarometricM: number | null
  relativeAltitudeM: number | null
  verticalSpeedMs: number | null
  temperatureC: number | null
  humidityPct: number | null
  pressureHpa: number | null
  batteryV: number | null
  rssiDbm: number | null
  snrDb: number | null
}
export interface PredictionParameters {
  targetRelativeAltitudeM: number
  ascentRateMs: number
  descentRateMs: number
  /** Demo scenarios only. Never sent to the real predictor. */
  ascentWindDirection: number
  ascentWindMs: number
  descentWindDirection: number
  descentWindMs: number
}
export interface Prediction {
  id: string
  missionId: string
  generatedAt: string
  weatherAt: string | null
  source: 'demo' | 'tawhiri'
  parameters: PredictionParameters
  trajectory: (Position & { time: string })[]
  landing: Position & { time: string }
  release: Position & { time: string }
}
export interface Command {
  id: string
  missionId: string
  clientRequestId: string
  type: CommandType
  status: CommandStatus
  createdAt: string
  updatedAt: string
  evidence: string
  simulated: boolean
}
export interface MissionEvent {
  id: string
  missionId: string
  receivedAt: string
  type: 'info' | 'warning' | 'release' | 'landed'
  message: string
  position: Position | null
}
export interface DashboardSnapshot {
  mission: Mission
  telemetry: Telemetry[]
  commands: Command[]
  events: MissionEvent[]
  prediction: Prediction | null
  permissions: { canCommand: boolean; canPredict: boolean }
  csrfToken: string | null
}
export type MissionMessage =
  | { type: 'telemetry'; data: Telemetry }
  | { type: 'command'; data: Command }
  | { type: 'event'; data: MissionEvent }
  | { type: 'mission'; data: Mission }
  | { type: 'prediction'; data: Prediction }

export const MAX_TELEMETRY = 1200
export const MAX_TARGET_RELATIVE_ALTITUDE_M = 15000
export function mergeTelemetry(
  current: Telemetry[],
  incoming: Telemetry[],
  missionId: string,
): Telemetry[] {
  const byId = new Map(current.map((sample) => [sample.id, sample]))
  for (const sample of incoming) {
    if (sample.missionId === missionId && !byId.has(sample.id)) byId.set(sample.id, sample)
  }
  return [...byId.values()]
    .sort((a, b) => Date.parse(a.receivedAt) - Date.parse(b.receivedAt) || a.id.localeCompare(b.id))
    .slice(-MAX_TELEMETRY)
}
const commandRank: Record<CommandStatus, number> = {
  pending: 0,
  sent: 1,
  received: 2,
  executed: 3,
  rejected: 3,
  expired: 3,
}
export function mergeCommands(
  current: Command[],
  incoming: Command[],
  missionId: string,
): Command[] {
  const byId = new Map(current.map((command) => [command.id, command]))
  for (const command of incoming) {
    if (command.missionId !== missionId) continue
    const old = byId.get(command.id)
    if (
      !old ||
      (Date.parse(command.updatedAt) >= Date.parse(old.updatedAt) &&
        commandRank[command.status] >= commandRank[old.status] &&
        commandRank[old.status] < 3)
    )
      byId.set(command.id, command)
  }
  return [...byId.values()]
    .sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt))
    .slice(0, 100)
}
export function mergeEvents(
  current: MissionEvent[],
  incoming: MissionEvent[],
  missionId: string,
): MissionEvent[] {
  const byId = new Map(current.map((event) => [event.id, event]))
  for (const event of incoming) if (event.missionId === missionId) byId.set(event.id, event)
  return [...byId.values()]
    .sort((a, b) => Date.parse(b.receivedAt) - Date.parse(a.receivedAt))
    .slice(0, 100)
}
export function latestSample(samples: Telemetry[]): Telemetry | null {
  return samples.at(-1) ?? null
}
export function dataAgeSeconds(sample: Telemetry | null, now: number): number | null {
  return sample ? Math.max(0, Math.floor((now - Date.parse(sample.receivedAt)) / 1000)) : null
}
export function distanceKm(
  a: Pick<Position, 'latitude' | 'longitude'>,
  b: Pick<Position, 'latitude' | 'longitude'>,
): number {
  const rad = Math.PI / 180
  const dLat = (b.latitude - a.latitude) * rad
  const dLon = (b.longitude - a.longitude) * rad
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a.latitude * rad) * Math.cos(b.latitude * rad) * Math.sin(dLon / 2) ** 2
  return 6371 * 2 * Math.asin(Math.sqrt(Math.min(1, h)))
}
export function validPredictionParameters(p: PredictionParameters): boolean {
  return (
    Number.isFinite(p.targetRelativeAltitudeM) &&
    p.targetRelativeAltitudeM >= 1000 &&
    p.targetRelativeAltitudeM <= MAX_TARGET_RELATIVE_ALTITUDE_M &&
    Number.isFinite(p.ascentRateMs) &&
    p.ascentRateMs >= 1 &&
    p.ascentRateMs <= 10 &&
    Number.isFinite(p.descentRateMs) &&
    p.descentRateMs >= 1 &&
    p.descentRateMs <= 15 &&
    [p.ascentWindDirection, p.descentWindDirection].every(
      (v) => Number.isFinite(v) && v >= 0 && v <= 360,
    ) &&
    [p.ascentWindMs, p.descentWindMs].every((v) => Number.isFinite(v) && v >= 0 && v <= 30)
  )
}
