import {
  dataAgeSeconds,
  latestSample,
  mergeCommands,
  mergeEvents,
  mergeTelemetry,
  validPredictionParameters,
} from '../domain/mission.ts'
import type {
  CommandType,
  ConnectionStatus,
  DashboardSnapshot,
  MissionMessage,
  PredictionParameters,
} from '../domain/mission.ts'
import type { MissionGateway } from './ports.ts'

export interface MissionState {
  snapshot: DashboardSnapshot | null
  connection: ConnectionStatus
  loading: boolean
  error: string | null
  actionError: string | null
  commanding: boolean
  predicting: boolean
  paused: boolean
}
export class MissionController {
  private state: MissionState = {
    snapshot: null,
    connection: 'connecting',
    loading: true,
    error: null,
    actionError: null,
    commanding: false,
    predicting: false,
    paused: false,
  }
  private listeners = new Set<() => void>()
  private generation = 0
  private abort: AbortController | null = null
  private disconnect: (() => void) | null = null
  private buffer: MissionMessage[] = []
  private refreshGeneration = 0
  readonly gateway: MissionGateway
  constructor(gateway: MissionGateway) {
    this.gateway = gateway
  }
  getSnapshot = (): MissionState => this.state
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }
  private update(patch: Partial<MissionState>) {
    this.state = { ...this.state, ...patch }
    this.listeners.forEach((listener) => listener())
  }
  start = (): (() => void) => {
    this.stop()
    const generation = this.generation
    this.update({
      loading: !this.state.snapshot,
      error: null,
      connection: 'connecting',
      commanding: false,
      predicting: false,
    })
    // Subscribe before loading history; buffer until the first consistent snapshot arrives.
    this.disconnect = this.gateway.subscribe(
      (message) => {
        if (generation !== this.generation) return
        if (!this.state.snapshot) {
          this.buffer = [...this.buffer, message].slice(-2400)
          return
        }
        this.receive(message)
      },
      (connection) => {
        if (generation !== this.generation) return
        this.update({ connection })
        if (connection === 'connected') void this.refresh()
      },
      (error) => {
        if (generation === this.generation) this.update({ error })
      },
    )
    void this.refresh()
    // The owning view must also dispose a connection restarted by its Retry button.
    return () => this.stop()
  }
  private stop() {
    this.generation += 1
    this.abort?.abort()
    this.disconnect?.()
    this.disconnect = null
    this.buffer = []
  }
  refresh = async () => {
    this.abort?.abort()
    const abort = new AbortController()
    this.abort = abort
    const generation = this.generation
    const refreshGeneration = ++this.refreshGeneration
    try {
      const incoming = await this.gateway.load(abort.signal)
      if (
        abort.signal.aborted ||
        generation !== this.generation ||
        refreshGeneration !== this.refreshGeneration
      )
        return
      const old = this.state.snapshot
      const same = old?.mission.id === incoming.mission.id ? old : null
      const mission =
        same && Date.parse(same.mission.updatedAt) > Date.parse(incoming.mission.updatedAt)
          ? same.mission
          : incoming.mission
      const prediction =
        same?.prediction &&
        (!incoming.prediction ||
          Date.parse(same.prediction.generatedAt) > Date.parse(incoming.prediction.generatedAt))
          ? same.prediction
          : incoming.prediction
      this.update({
        snapshot: {
          ...incoming,
          mission,
          prediction,
          telemetry: mergeTelemetry(same?.telemetry ?? [], incoming.telemetry, mission.id),
          commands: mergeCommands(same?.commands ?? [], incoming.commands, mission.id),
          events: mergeEvents(same?.events ?? [], incoming.events, mission.id),
        },
        loading: false,
        error: null,
      })
      const buffered = this.buffer
      this.buffer = []
      buffered.forEach((message) => this.receive(message))
    } catch (error) {
      if (!abort.signal.aborted && generation === this.generation)
        this.update({
          loading: false,
          error: error instanceof Error ? error.message : 'No se pudo cargar la misión.',
          snapshot: this.state.snapshot
            ? {
                ...this.state.snapshot,
                permissions: { canCommand: false, canPredict: false },
                csrfToken: null,
              }
            : null,
        })
    }
  }
  private receive(message: MissionMessage) {
    const old = this.state.snapshot
    if (!old) return
    const missionId = message.type === 'mission' ? message.data.id : message.data.missionId
    if (missionId !== old.mission.id) return
    let snapshot = old
    switch (message.type) {
      case 'telemetry':
        snapshot = { ...old, telemetry: mergeTelemetry(old.telemetry, [message.data], missionId) }
        break
      case 'command':
        snapshot = { ...old, commands: mergeCommands(old.commands, [message.data], missionId) }
        break
      case 'event':
        snapshot = { ...old, events: mergeEvents(old.events, [message.data], missionId) }
        break
      case 'mission':
        if (Date.parse(message.data.updatedAt) >= Date.parse(old.mission.updatedAt))
          snapshot = { ...old, mission: message.data }
        break
      case 'prediction':
        if (
          !old.prediction ||
          Date.parse(message.data.generatedAt) >= Date.parse(old.prediction.generatedAt)
        )
          snapshot = { ...old, prediction: message.data }
        break
    }
    this.update({ snapshot })
  }
  setPaused = (paused: boolean) => {
    this.gateway.setPaused?.(paused)
    this.update({ paused })
  }
  clearActionError = () => this.update({ actionError: null })
  sendCommand = async (type: CommandType, releaseConfirmed = false): Promise<boolean> => {
    const s = this.state.snapshot
    const age = dataAgeSeconds(latestSample(s?.telemetry ?? []), Date.now())
    if (
      !s ||
      this.state.commanding ||
      !s.permissions.canCommand ||
      this.state.connection !== 'connected' ||
      age === null ||
      age > s.mission.staleAfterSeconds ||
      (this.gateway.mode === 'live' && !s.csrfToken)
    ) {
      this.update({
        actionError:
          'Comando no disponible: verifica conexión, datos recientes y permiso de operador.',
      })
      return false
    }
    if (
      type === 'RELEASE_NOW' &&
      (!releaseConfirmed ||
        s.mission.phase !== 'ascending' ||
        s.commands.some((c) => c.type === type && !['rejected', 'expired'].includes(c.status)))
    ) {
      this.update({
        actionError:
          'La liberación requiere confirmación, fase de ascenso y ausencia de otra solicitud activa.',
      })
      return false
    }
    this.update({ commanding: true, actionError: null })
    const generation = this.generation
    try {
      // A POST is never retried automatically, even when the response is lost.
      const command = await this.gateway.sendCommand(type, crypto.randomUUID(), s.csrfToken)
      if (generation === this.generation) this.receive({ type: 'command', data: command })
      return true
    } catch (error) {
      if (generation === this.generation)
        this.update({
          actionError:
            (error instanceof Error ? error.message : 'Sin respuesta del servidor.') +
            ' Verifica la bitácora antes de volver a solicitarlo.',
        })
      return false
    } finally {
      if (generation === this.generation) this.update({ commanding: false })
    }
  }
  predict = async (parameters: PredictionParameters): Promise<boolean> => {
    const s = this.state.snapshot
    const latest = latestSample(s?.telemetry ?? [])
    const age = dataAgeSeconds(latest, Date.now())
    const invalidAscent =
      s?.mission.phase === 'ascending' &&
      (age === null ||
        age > s.mission.staleAfterSeconds ||
        latest?.latitude == null ||
        latest.longitude === null ||
        latest.altitudeGpsM === null ||
        s.mission.launch.altitudeM + parameters.targetRelativeAltitudeM <= latest.altitudeGpsM)
    if (
      !s ||
      this.state.predicting ||
      !s.permissions.canPredict ||
      !validPredictionParameters(parameters) ||
      this.state.connection !== 'connected' ||
      (this.gateway.mode === 'live' &&
        (!s.csrfToken || !['preflight', 'ascending'].includes(s.mission.phase) || invalidAscent))
    ) {
      this.update({
        actionError: 'Predicción no disponible para estos parámetros, permisos o fase.',
      })
      return false
    }
    this.update({ predicting: true, actionError: null })
    const generation = this.generation
    try {
      const prediction = await this.gateway.predict(parameters, s.csrfToken)
      if (generation === this.generation) this.receive({ type: 'prediction', data: prediction })
      return true
    } catch (error) {
      if (generation === this.generation)
        this.update({
          actionError:
            error instanceof Error
              ? error.message
              : 'No se pudo actualizar la predicción. Se conserva la anterior.',
        })
      return false
    } finally {
      if (generation === this.generation) this.update({ predicting: false })
    }
  }
}
