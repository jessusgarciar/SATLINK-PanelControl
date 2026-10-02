import type { MissionGateway } from '../../application/ports.ts'
import type {
  Command,
  CommandType,
  ConnectionStatus,
  DashboardSnapshot,
  MissionMessage,
  Prediction,
  PredictionParameters,
  Telemetry,
} from '../../domain/mission.ts'

/** Deterministic visual scenario. No radio, predictor, actuator or backend is contacted. */
export class DemoMissionGateway implements MissionGateway {
  readonly mode = 'demo' as const
  private epoch = Date.now() - 156000
  private elapsed = 156
  private paused = false
  private releaseAt: number | null = null
  private timers = new Set<ReturnType<typeof setTimeout>>()
  private emit: (message: MissionMessage) => void = () => {}
  private data: DashboardSnapshot
  constructor() {
    const startedAt = new Date(this.epoch).toISOString()
    this.data = {
      mission: {
        id: 'satlink-demo',
        name: 'SATLINK · Misión de demostración',
        updatedAt: startedAt,
        startedAt,
        endedAt: null,
        phase: 'ascending',
        launch: { latitude: 21.88535, longitude: -102.29167, altitudeM: 1870 },
        launchLabel: 'AGS · Origen de ejemplo',
        targetRelativeAltitudeM: 15000,
        nominalAscentMs: 5,
        nominalDescentMs: 6.5,
        watchdogSeconds: 3300,
        staleAfterSeconds: 15,
        deviceEui: '0000000000000000',
        region: 'US915',
        beaconOn: false,
      },
      telemetry: [],
      commands: [],
      events: [],
      prediction: null,
      permissions: { canCommand: true, canPredict: true },
      csrfToken: null,
    }
    this.data.telemetry = Array.from({ length: 157 }, (_, i) => this.sample(i))
    this.data.prediction = this.makePrediction(this.defaults())
  }
  defaults(): PredictionParameters {
    return {
      targetRelativeAltitudeM: 15000,
      ascentRateMs: 5,
      descentRateMs: 6.5,
      ascentWindDirection: 45,
      ascentWindMs: 8,
      descentWindDirection: 120,
      descentWindMs: 5,
    }
  }
  private sample(seconds: number): Telemetry {
    const launch = this.data.mission.launch
    const released = this.releaseAt !== null && seconds >= this.releaseAt
    const relative = released
      ? Math.max(0, this.releaseAt! * 5 - (seconds - this.releaseAt!) * 6.5)
      : seconds * 5
    const altitude = launch.altitudeM + relative
    const driftSeconds = released
      ? Math.min(seconds, this.releaseAt! + (this.releaseAt! * 5) / 6.5)
      : seconds
    const pressure = 1013.25 * (1 - altitude / 44330) ** 5.255
    return {
      id: 'demo-' + seconds,
      missionId: this.data.mission.id,
      receivedAt: new Date(this.epoch + seconds * 1000).toISOString(),
      frameCounter: seconds,
      latitude: launch.latitude + driftSeconds * 0.000006,
      longitude: launch.longitude + driftSeconds * 0.000011,
      altitudeGpsM: altitude,
      relativeAltitudeM: relative,
      altitudeBarometricM: pressure >= 300 ? altitude + Math.sin(seconds * 0.07) * 2 : null,
      temperatureC: 22 - relative * 0.006 + Math.sin(seconds) * 0.1,
      humidityPct: 58 - relative * 0.002 + Math.sin(seconds * 0.03),
      pressureHpa: Math.max(5, pressure),
      batteryV: 4.12 - seconds * 0.000001 + Math.sin(seconds * 2.3) * 0.004,
      rssiDbm: -87 - Math.round(Math.sin(seconds / 5) * 3),
      snrDb: 8.5 + Math.sin(seconds / 5),
      verticalSpeedMs:
        relative === 0 && released ? 0 : released ? -6.5 : 5 + Math.sin(seconds * 0.02) * 0.1,
    }
  }
  async load(signal: AbortSignal) {
    signal.throwIfAborted()
    return structuredClone(this.data)
  }
  subscribe(
    onMessage: (message: MissionMessage) => void,
    onStatus: (status: ConnectionStatus) => void,
  ) {
    this.emit = onMessage
    onStatus('connected')
    const interval = setInterval(() => {
      if (this.paused) return
      this.elapsed = Math.floor((Date.now() - this.epoch) / 1000)
      if (this.releaseAt === null && this.elapsed >= this.data.mission.targetRelativeAltitudeM / 5)
        this.releaseAt = this.elapsed
      const sample = this.sample(this.elapsed)
      this.data.telemetry = [...this.data.telemetry, sample].slice(-1200)
      onMessage({ type: 'telemetry', data: sample })
      if (this.releaseAt !== null && this.data.mission.phase !== 'landed') {
        const stable = this.data.telemetry.slice(-5).every((s) => s.relativeAltitudeM === 0)
        const phase = stable ? 'landed' : 'descending'
        if (phase !== this.data.mission.phase) {
          this.data.mission = {
            ...this.data.mission,
            phase,
            updatedAt: sample.receivedAt,
            endedAt: stable ? sample.receivedAt : null,
          }
          onMessage({ type: 'mission', data: this.data.mission })
        }
      }
    }, 1000)
    return () => {
      clearInterval(interval)
      this.timers.forEach(clearTimeout)
      this.timers.clear()
      this.emit = () => {}
    }
  }
  setPaused(paused: boolean) {
    this.paused = paused
  }
  private later(action: () => void, delay: number) {
    const timer = setTimeout(() => {
      this.timers.delete(timer)
      action()
    }, delay)
    this.timers.add(timer)
  }
  async sendCommand(type: CommandType, clientRequestId: string): Promise<Command> {
    const now = new Date().toISOString()
    const command: Command = {
      id: crypto.randomUUID(),
      missionId: this.data.mission.id,
      clientRequestId,
      type,
      status: 'pending',
      createdAt: now,
      updatedAt: now,
      evidence: 'Solicitud registrada por el simulador.',
      simulated: true,
    }
    this.data.commands = [command, ...this.data.commands].slice(0, 100)
    const advance = (status: Command['status'], evidence: string) => {
      const updated = { ...command, status, evidence, updatedAt: new Date().toISOString() }
      this.data.commands = this.data.commands.map((c) => (c.id === command.id ? updated : c))
      this.emit({ type: 'command', data: updated })
    }
    this.later(() => advance('sent', 'SIMULADO · transmisión del gateway.'), 600)
    this.later(
      () => advance('received', 'SIMULADO · recepción del dispositivo; todavía no es ejecución.'),
      1400,
    )
    this.later(() => {
      advance('executed', 'SIMULADO · respuesta de ejecución del firmware.')
      if (type === 'BEACON_ON' || type === 'BEACON_OFF') {
        this.data.mission = {
          ...this.data.mission,
          beaconOn: type === 'BEACON_ON',
          updatedAt: new Date().toISOString(),
        }
        this.emit({ type: 'mission', data: this.data.mission })
      }
      if (type === 'RELEASE_NOW') {
        this.releaseAt = Math.floor((Date.now() - this.epoch) / 1000)
        const sample = this.sample(this.releaseAt)
        const event = {
          id: crypto.randomUUID(),
          missionId: this.data.mission.id,
          receivedAt: new Date().toISOString(),
          type: 'release' as const,
          message: 'Liberación SIMULADA confirmada por el escenario.',
          position: {
            latitude: sample.latitude!,
            longitude: sample.longitude!,
            altitudeM: sample.altitudeGpsM!,
          },
        }
        this.data.events = [event, ...this.data.events]
        this.emit({ type: 'event', data: event })
      }
    }, 2200)
    return structuredClone(command)
  }
  private makePrediction(p: PredictionParameters): Prediction {
    const current = this.data.telemetry.at(-1) ?? this.sample(this.elapsed)
    const origin = {
      latitude: current.latitude!,
      longitude: current.longitude!,
      altitudeM: current.altitudeGpsM!,
    }
    const now = Date.now()
    const target = this.data.mission.launch.altitudeM + p.targetRelativeAltitudeM
    const ascentSeconds =
      this.releaseAt === null ? Math.max(0, target - origin.altitudeM) / p.ascentRateMs : 0
    const releaseAltitude = ascentSeconds ? target : origin.altitudeM
    const descentSeconds =
      Math.max(0, releaseAltitude - this.data.mission.launch.altitudeM) / p.descentRateMs
    const drift = (
      start: typeof origin,
      seconds: number,
      heading: number,
      speed: number,
      altitudeM: number,
    ) => {
      const radians = (heading * Math.PI) / 180
      return {
        latitude: start.latitude + (Math.cos(radians) * speed * seconds) / 111320,
        longitude:
          start.longitude +
          (Math.sin(radians) * speed * seconds) /
            (111320 * Math.cos((start.latitude * Math.PI) / 180)),
        altitudeM,
      }
    }
    const release = {
      ...drift(origin, ascentSeconds, p.ascentWindDirection, p.ascentWindMs, releaseAltitude),
      time: new Date(now + ascentSeconds * 1000).toISOString(),
    }
    const landing = {
      ...drift(
        release,
        descentSeconds,
        p.descentWindDirection,
        p.descentWindMs,
        this.data.mission.launch.altitudeM,
      ),
      time: new Date(now + (ascentSeconds + descentSeconds) * 1000).toISOString(),
    }
    const trajectory = Array.from({ length: 41 }, (_, i) => {
      const ascending = i <= 20
      const fraction = (ascending ? i : i - 20) / 20
      const start = ascending ? origin : release
      const seconds = (ascending ? ascentSeconds : descentSeconds) * fraction
      const altitudeM = ascending
        ? origin.altitudeM + (releaseAltitude - origin.altitudeM) * fraction
        : releaseAltitude - (releaseAltitude - landing.altitudeM) * fraction
      return {
        ...drift(
          start,
          seconds,
          ascending ? p.ascentWindDirection : p.descentWindDirection,
          ascending ? p.ascentWindMs : p.descentWindMs,
          altitudeM,
        ),
        time: new Date(now + (ascending ? seconds : ascentSeconds + seconds) * 1000).toISOString(),
      }
    })
    return {
      id: crypto.randomUUID(),
      missionId: this.data.mission.id,
      generatedAt: new Date(now).toISOString(),
      weatherAt: null,
      source: 'demo',
      parameters: { ...p },
      trajectory,
      release,
      landing,
    }
  }
  async predict(parameters: PredictionParameters) {
    const prediction = this.makePrediction(parameters)
    this.data.prediction = prediction
    return structuredClone(prediction)
  }
}
