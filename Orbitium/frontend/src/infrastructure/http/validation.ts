import { MAX_TARGET_RELATIVE_ALTITUDE_M, validPredictionParameters } from '../../domain/mission.ts'
import type {
  Command,
  CommandStatus,
  CommandType,
  DashboardSnapshot,
  FlightPhase,
  Mission,
  MissionEvent,
  MissionMessage,
  Position,
  Prediction,
  PredictionParameters,
  Telemetry,
  Ingestion,
} from '../../domain/mission.ts'
import type { HistoryPage, TelemetryWindow } from '../../domain/history.ts'

type JsonRecord = Record<string, unknown>
function record(value: unknown): JsonRecord {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('Respuesta inválida: se esperaba un objeto.')
  return value as JsonRecord
}
function str(value: unknown): string {
  if (typeof value !== 'string' || !value.trim() || value.length > 4096)
    throw new Error('Respuesta inválida: texto ausente o demasiado largo.')
  return value
}
function num(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value))
    throw new Error('Respuesta inválida: número no finito.')
  return value
}
function between(value: unknown, min: number, max: number): number {
  const n = num(value)
  if (n < min || n > max) throw new Error('Respuesta inválida: valor fuera de rango.')
  return n
}
function sensor(value: unknown, min: number, max: number): number | null {
  // Invalid/missing sensor values never become a plausible zero.
  return typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max
    ? value
    : null
}
function bool(value: unknown): boolean {
  if (typeof value !== 'boolean')
    throw new Error('Respuesta inválida: permiso o estado no booleano.')
  return value
}
function optionalBool(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}
function optionalInteger(value: unknown, min: number, max: number): number | null {
  const result = sensor(value, min, max)
  return result !== null && Number.isInteger(result) ? result : null
}
export function parseIngestion(value: unknown): Ingestion | null {
  if (value == null) return null
  const ingestion = record(value)
  return { source: str(ingestion.source), status: oneOf(ingestion.status, ['disabled', 'connecting', 'connected', 'reconnecting', 'offline'] as const), updatedAt: timestamp(ingestion.updatedAt) }
}
function oneOf<T extends string>(value: unknown, options: readonly T[]): T {
  if (typeof value !== 'string' || !options.includes(value as T))
    throw new Error('Respuesta inválida: estado desconocido.')
  return value as T
}
export function timestamp(value: unknown): string {
  const text = str(value)
  if (
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/.test(text) ||
    !Number.isFinite(Date.parse(text))
  )
    throw new Error('Respuesta inválida: fecha sin zona horaria.')
  return new Date(text).toISOString()
}
function optionalTimestamp(value: unknown): string | null {
  return value === null || value === undefined ? null : timestamp(value)
}
function array<T>(value: unknown, parse: (item: unknown) => T, max = 5000): T[] {
  if (!Array.isArray(value) || value.length > max)
    throw new Error('Respuesta inválida: lista ausente o demasiado grande.')
  return value.map(parse)
}
function position(value: unknown): Position {
  const p = record(value)
  return {
    latitude: between(p.latitude, -90, 90),
    longitude: between(p.longitude, -180, 180),
    altitudeM: between(p.altitudeM, -500, 65534),
  }
}
export function parseMission(value: unknown): Mission {
  const m = record(value)
  return {
    id: str(m.id),
    name: str(m.name),
    updatedAt: timestamp(m.updatedAt),
    startedAt: optionalTimestamp(m.startedAt),
    endedAt: optionalTimestamp(m.endedAt),
    phase: oneOf<FlightPhase>(m.phase, [
      'preflight',
      'ascending',
      'descending',
      'landed',
      'unknown',
    ]),
    launch: position(m.launch),
    launchLabel: str(m.launchLabel),
    targetRelativeAltitudeM: between(m.targetRelativeAltitudeM, 1000, MAX_TARGET_RELATIVE_ALTITUDE_M),
    nominalAscentMs: between(m.nominalAscentMs, 1, 10),
    nominalDescentMs: between(m.nominalDescentMs, 1, 15),
    watchdogSeconds: between(m.watchdogSeconds, 1, 86400),
    staleAfterSeconds: between(m.staleAfterSeconds, 1, 3600),
    deviceEui: str(m.deviceEui),
    region: str(m.region),
    beaconOn: m.beaconOn === null ? null : bool(m.beaconOn),
  }
}
export function parseTelemetry(value: unknown): Telemetry {
  const t = record(value)
  const device = t.device == null ? null : record(t.device)
  const radio = t.radio == null ? null : record(t.radio)
  const frameCounter = between(t.frameCounter, 0, 4294967295)
  if (!Number.isInteger(frameCounter)) throw new Error('Contador de trama inválido.')
  const latitude = sensor(t.latitude, -90, 90)
  const longitude = sensor(t.longitude, -180, 180)
  const gpsValid = latitude !== null && longitude !== null
  return {
    id: str(t.id),
    missionId: str(t.missionId),
    receivedAt: timestamp(t.receivedAt),
    frameCounter,
    latitude: gpsValid ? latitude : null,
    longitude: gpsValid ? longitude : null,
    altitudeGpsM: sensor(t.altitudeGpsM, -500, 65534),
    altitudeBarometricM: sensor(t.altitudeBarometricM, -500, 65534),
    relativeAltitudeM: sensor(t.relativeAltitudeM, -66034, 65534),
    verticalSpeedMs: sensor(t.verticalSpeedMs, -200, 200),
    temperatureC: sensor(t.temperatureC, -127, 127),
    humidityPct: sensor(t.humidityPct, 0, 100),
    pressureHpa: sensor(t.pressureHpa, 5, 1270),
    batteryV: sensor(t.batteryV, 0, 5.08),
    rssiDbm: sensor(t.rssiDbm, -200, 20),
    snrDb: sensor(t.snrDb, -40, 40),
    device: device === null ? null : {
      gpsActive: optionalBool(device.gpsActive), gpsFix: optionalBool(device.gpsFix),
      satellites: optionalInteger(device.satellites, 0, 255), batteryPct: optionalInteger(device.batteryPct, 0, 100),
      charging: optionalBool(device.charging), usbPowered: optionalBool(device.usbPowered),
    },
    radio: radio === null ? null : {
      gatewayId: typeof radio.gatewayId === 'string' && radio.gatewayId.length <= 128 && radio.gatewayId.trim() ? radio.gatewayId : null,
      frequencyHz: optionalInteger(radio.frequencyHz, 1, 10_000_000_000),
      dataRate: optionalInteger(radio.dataRate, 0, 15), fPort: optionalInteger(radio.fPort, 1, 255),
    },
  }
}
export function parseCommand(value: unknown): Command {
  const c = record(value)
  return {
    id: str(c.id),
    missionId: str(c.missionId),
    clientRequestId: str(c.clientRequestId),
    type: oneOf<CommandType>(c.type, [
      'PING',
      'STATUS',
      'TELEMETRY',
      'BEACON_ON',
      'BEACON_OFF',
      'RELEASE_NOW',
    ]),
    status: oneOf<CommandStatus>(c.status, [
      'pending',
      'sent',
      'received',
      'executed',
      'rejected',
      'expired',
    ]),
    createdAt: timestamp(c.createdAt),
    updatedAt: timestamp(c.updatedAt),
    evidence: str(c.evidence),
    simulated: bool(c.simulated),
  }
}
export function parseEvent(value: unknown): MissionEvent {
  const e = record(value)
  return {
    id: str(e.id),
    missionId: str(e.missionId),
    receivedAt: timestamp(e.receivedAt),
    type: oneOf(e.type, ['info', 'warning', 'release', 'landed'] as const),
    message: str(e.message),
    position: e.position === null ? null : position(e.position),
  }
}
function parameters(value: unknown): PredictionParameters {
  const p = record(value)
  const parsed = {
    ...(p.mode === undefined ? {} : { mode: oneOf(p.mode, ['planned', 'ascending'] as const) }),
    ...(p.launchDatetime === undefined ? {} : { launchDatetime: timestamp(p.launchDatetime) }),
    ...(p.launch == null ? {} : { launch: position(p.launch), launchAltitudeReference: oneOf(p.launchAltitudeReference, ['MSL'] as const) }),
    targetRelativeAltitudeM: num(p.targetRelativeAltitudeM),
    ascentRateMs: num(p.ascentRateMs),
    descentRateMs: num(p.descentRateMs),
    ascentWindDirection: p.ascentWindDirection === undefined ? 0 : num(p.ascentWindDirection),
    ascentWindMs: p.ascentWindMs === undefined ? 0 : num(p.ascentWindMs),
    descentWindDirection: p.descentWindDirection === undefined ? 0 : num(p.descentWindDirection),
    descentWindMs: p.descentWindMs === undefined ? 0 : num(p.descentWindMs),
  }
  if (!validPredictionParameters(parsed)) throw new Error('Parámetros de predicción inválidos.')
  return parsed
}
function timedPosition(value: unknown) {
  const p = record(value)
  return { ...position(p), time: timestamp(p.time) }
}
export function parsePrediction(value: unknown): Prediction {
  const p = record(value)
  const source = oneOf(p.source, ['demo', 'tawhiri'] as const)
  const c = p.context == null ? null : record(p.context)
  if (source === 'tawhiri' && !c) throw new Error('Predicción real sin contexto verificable.')
  const trajectory = array(p.trajectory, timedPosition, 10000)
  if (source === 'tawhiri' && trajectory.length < 2) throw new Error('Trayectoria de predicción incompleta.')
  return {
    id: str(p.id),
    missionId: str(p.missionId),
    generatedAt: timestamp(p.generatedAt),
    weatherAt: optionalTimestamp(p.weatherAt),
    source,
    ...(c === null ? {} : { context: {
      ...(c.inputSource == null ? {} : { inputSource: oneOf(c.inputSource, ['simulated'] as const) }),
      mode: oneOf(c.mode, ['planned', 'ascending'] as const),
      origin: position(c.origin), originAt: timestamp(c.originAt),
      telemetryId: c.telemetryId === null ? null : str(c.telemetryId),
      dataset: c.dataset === null ? null : str(c.dataset),
      altitudeReference: oneOf(c.altitudeReference, ['MSL'] as const),
    } }),
    parameters: parameters(p.parameters),
    trajectory,
    landing: timedPosition(p.landing),
    release: timedPosition(p.release),
  }
}
export function parseSnapshot(value: unknown, missionId: string): DashboardSnapshot {
  const s = record(value)
  const mission = parseMission(s.mission)
  if (mission.id !== missionId) throw new Error('El servidor devolvió otra misión.')
  const permissions = record(s.permissions)
  const telemetry = array(s.telemetry, parseTelemetry)
  const commands = array(s.commands, parseCommand)
  const events = array(s.events, parseEvent)
  const prediction = s.prediction === null ? null : parsePrediction(s.prediction)
  const settings = s.predictionSettings == null ? null : record(s.predictionSettings)
  if (
    [...telemetry, ...commands, ...events, ...(prediction ? [prediction] : [])].some(
      (item) => item.missionId !== missionId,
    )
  )
    throw new Error('La respuesta contiene datos de otra misión.')
  return {
    mission,
    ...(settings === null ? {} : { predictionSettings: {
      enabled: bool(settings.enabled),
      launchAltitudeReference: oneOf(settings.launchAltitudeReference, ['MSL', 'unknown'] as const),
      gpsAltitudeReference: oneOf(settings.gpsAltitudeReference, ['MSL', 'unknown'] as const),
      nextAllowedAt: optionalTimestamp(settings.nextAllowedAt),
    } }),
    ingestion: parseIngestion(s.ingestion),
    telemetry,
    commands,
    events,
    prediction,
    permissions: {
      canCommand: bool(permissions.canCommand),
      canPredict: bool(permissions.canPredict),
    },
    csrfToken: s.csrfToken == null ? null : str(s.csrfToken),
  }
}
export function parseMessage(value: unknown): MissionMessage | null {
  const message = record(value)
  switch (message.type) {
    case 'ingestion': {
      const data = parseIngestion(message.data)
      if (!data) throw new Error('Estado MQTT ausente.')
      return { type: 'ingestion', data }
    }
    case 'heartbeat':
      return null
    case 'telemetry':
      return { type: 'telemetry', data: parseTelemetry(message.data) }
    case 'command':
      return { type: 'command', data: parseCommand(message.data) }
    case 'event':
      return { type: 'event', data: parseEvent(message.data) }
    case 'mission':
      return { type: 'mission', data: parseMission(message.data) }
    case 'prediction':
      return { type: 'prediction', data: parsePrediction(message.data) }
    default:
      throw new Error('Mensaje no compatible con el contrato v1.')
  }
}

export function parseHistory(value: unknown, missionId: string): HistoryPage {
  const page = record(value)
  const items = array(page.items, parseTelemetry, 1200)
  if (items.some((t) => t.missionId !== missionId)) throw new Error('El archivo contiene otra misión.')
  return { items, nextCursor: page.nextCursor == null ? null : str(page.nextCursor) }
}
export function parseWindow(value: unknown, missionId: string): TelemetryWindow {
  const w = record(value)
  const series = array(w.series, parseTelemetry, 600)
  const track = array(w.track, parseTelemetry, 500)
  if ([...series, ...track].some((t) => t.missionId !== missionId)) throw new Error('El archivo contiene otra misión.')
  const from = optionalTimestamp(w.from), to = timestamp(w.to)
  if (from !== null && Date.parse(from) >= Date.parse(to)) throw new Error('Intervalo inválido.')
  return { from, to, total: between(w.total, 0, Number.MAX_SAFE_INTEGER), series, track }
}
