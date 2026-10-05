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

export interface Ingestion {
  source: string
  status: 'disabled' | 'connecting' | 'connected' | 'reconnecting' | 'offline'
  updatedAt: string
}
export interface DeviceDetails {
  gpsActive: boolean | null
  gpsFix: boolean | null
  satellites: number | null
  batteryPct: number | null
  charging: boolean | null
  usbPowered: boolean | null
}
export interface RadioDetails {
  gatewayId: string | null
  frequencyHz: number | null
  dataRate: number | null
  fPort: number | null
}

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
  device: DeviceDetails | null
  radio: RadioDetails | null
}
export interface PredictionParameters {
  mode?: 'planned' | 'ascending'
  launchDatetime?: string
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
  context?: {
    mode: 'planned' | 'ascending'
    origin: Position
    originAt: string
    telemetryId: string | null
    dataset: string | null
    altitudeReference: 'MSL'
  }
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
  predictionSettings?: {
    enabled: boolean
    launchAltitudeReference: 'MSL' | 'unknown'
    gpsAltitudeReference: 'MSL' | 'unknown'
    nextAllowedAt: string | null
  }
  ingestion: Ingestion | null
  mission: Mission
  telemetry: Telemetry[]
  commands: Command[]
  events: MissionEvent[]
  prediction: Prediction | null
  permissions: { canCommand: boolean; canPredict: boolean }
  csrfToken: string | null
}
export type MissionMessage =
  | { type: 'ingestion'; data: Ingestion }
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

/** Eligibility is shared by the form and controller; it never changes the physical phase. */
export function predictionUnavailableReason(
  snapshot: DashboardSnapshot, p: PredictionParameters, now: number,
): string | null {
  if (!snapshot.permissions.canPredict || !snapshot.predictionSettings?.enabled)
    return 'Configura y habilita el predictor en la estación local.'
  if (!snapshot.csrfToken) return 'Actualiza la conexión para recuperar el permiso local.'
  if (['descending', 'landed'].includes(snapshot.mission.phase))
    return 'Se conserva la predicción previa durante descenso o aterrizaje.'
  if (!validPredictionParameters(p)) return 'Revisa los parámetros del cálculo.'
  if (snapshot.predictionSettings.launchAltitudeReference !== 'MSL')
    return 'Confirma la altitud del lanzamiento sobre el nivel del mar.'
  const next = snapshot.predictionSettings.nextAllowedAt
  if (next && Date.parse(next) > now)
    return `Espera ${Math.ceil((Date.parse(next) - now) / 1000)} s antes del siguiente cálculo.`
  if (p.mode === 'planned') {
    if (!p.launchDatetime || !/(Z|[+-]\d{2}:\d{2})$/.test(p.launchDatetime) ||
        !Number.isFinite(Date.parse(p.launchDatetime)) || Date.parse(p.launchDatetime) < now)
      return 'Elige una fecha y hora de lanzamiento futura.'
  } else if (p.mode === 'ascending') {
    if (snapshot.predictionSettings.gpsAltitudeReference !== 'MSL')
      return 'Confirma que la altitud GPS está sobre el nivel del mar.'
    const sample = latestSample(snapshot.telemetry)
    if (!sample || sample.latitude === null || sample.longitude === null || sample.altitudeGpsM === null ||
        sample.device?.gpsFix === false || Date.parse(sample.receivedAt) > now + 5000 ||
        now - Date.parse(sample.receivedAt) > snapshot.mission.staleAfterSeconds * 1000)
      return 'El ascenso requiere el último paquete con GPS válido y reciente.'
    if (snapshot.mission.launch.altitudeM + p.targetRelativeAltitudeM <= sample.altitudeGpsM)
      return 'La altitud de liberación debe superar la altitud GPS actual.'
  } else return 'Selecciona planificación o ascenso para calcular.'
  return null
}

export function predictionParametersChanged(a: PredictionParameters, b: PredictionParameters, demo: boolean): boolean {
  const keys: (keyof PredictionParameters)[] = ['targetRelativeAltitudeM', 'ascentRateMs', 'descentRateMs']
  if (demo) keys.push('ascentWindDirection', 'ascentWindMs', 'descentWindDirection', 'descentWindMs')
  if (keys.some((key) => a[key] !== b[key])) return true
  return !demo && (a.mode !== b.mode ||
    (a.mode === 'planned' && Date.parse(a.launchDatetime ?? '') !== Date.parse(b.launchDatetime ?? '')))
}
