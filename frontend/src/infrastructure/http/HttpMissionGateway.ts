import type { MissionGateway } from '../../application/ports.ts'
import type {
  CommandType,
  ConnectionStatus,
  MissionMessage,
  PredictionParameters,
} from '../../domain/mission.ts'
import { subscribeMission } from '../websocket/missionStream.ts'
import { parseCommand, parsePrediction, parseSnapshot, parseHistory, parseWindow } from './validation.ts'
import type { TimeRange } from '../../domain/history.ts'

export class HttpMissionGateway implements MissionGateway {
  readonly mode = 'live' as const
  private base: string
  private missionId: string
  constructor(apiBase: string, missionId: string) {
    this.base = apiBase.replace(/\/$/, '') + '/missions/' + encodeURIComponent(missionId)
    this.missionId = missionId
  }
  private async request(path: string, options: RequestInit = {}): Promise<unknown> {
    const timeout = AbortSignal.timeout(12000)
    const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout
    try {
      const response = await fetch(this.base + path, {
        ...options,
        signal,
        credentials: 'include',
        headers: { Accept: 'application/json', ...options.headers },
      })
      if (!response.ok) {
        const messages: Record<number, string> = {
          401: 'Inicia sesión en la estación terrena.',
          403: 'Tu sesión no tiene permiso para esta acción.',
          404: 'La misión o el endpoint todavía no está disponible.',
          409: 'Existe una solicitud incompatible. Revisa la bitácora.',
          429: 'Espera antes de volver a solicitar una predicción.',
          502: 'Tawhiri no entregó una predicción válida. Se conserva la anterior.',
          504: 'Tawhiri agotó el tiempo de espera. Se conserva la anterior.',
        }
        const body: unknown = response.headers.get('content-type')?.includes('application/json')
          ? await response.json().catch(() => null) : null
        const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : null
        throw new Error(
          (response.status === 422 && typeof detail === 'string' ? detail : null) ??
          messages[response.status] ?? 'El servidor respondió con error ' + response.status + '.',
        )
      }
      const contentType = response.headers.get('content-type') ?? ''
      if (!contentType.includes('application/json'))
        throw new Error('El servidor no devolvió JSON. Comprueba la URL y el proxy de FastAPI.')
      return await response.json()
    } catch (error) {
      if (error instanceof DOMException && error.name === 'TimeoutError')
        throw new Error('Se agotó el tiempo de espera del servidor.')
      if (error instanceof TypeError)
        throw new Error('No se pudo conectar con la estación terrena.')
      throw error
    }
  }
  async load(signal: AbortSignal) {
    return parseSnapshot(await this.request('/dashboard?limit=1200', { signal }), this.missionId)
  }
  private interval(range: TimeRange): URLSearchParams {
    const query = new URLSearchParams({ to: range.to })
    if (range.from !== null) query.set('from', range.from)
    return query
  }
  async window(range: TimeRange, signal: AbortSignal) {
    return parseWindow(await this.request('/telemetry/window?' + this.interval(range), { signal }), this.missionId)
  }
  async history(range: TimeRange, cursor: string | null, signal: AbortSignal) {
    const query = this.interval(range)
    query.set('limit', '200')
    if (cursor) query.set('cursor', cursor)
    return parseHistory(await this.request('/telemetry?' + query, { signal }), this.missionId)
  }
  async exportCsv(range: TimeRange, signal: AbortSignal): Promise<Blob> {
    const response = await fetch(this.base + '/telemetry/export.csv?' + this.interval(range), { signal, credentials: 'include', headers: { Accept: 'text/csv' } })
    if (!response.ok || !response.headers.get('content-type')?.includes('text/csv')) {
      await response.body?.cancel()
      throw new Error('No se pudo exportar el archivo CSV. Comprueba el intervalo y la conexión.')
    }
    return await response.blob()
  }
  subscribe(
    onMessage: (message: MissionMessage) => void,
    onStatus: (status: ConnectionStatus) => void,
    onError: (message: string) => void,
  ) {
    const url = new URL(this.base + '/stream', window.location.href)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    return subscribeMission(url.href, onMessage, onStatus, onError)
  }
  async sendCommand(type: CommandType, clientRequestId: string, csrfToken: string | null) {
    const command = parseCommand(
      await this.request('/commands', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken ?? '',
          'Idempotency-Key': clientRequestId,
        },
        body: JSON.stringify({ type, clientRequestId }),
      }),
    )
    if (
      command.missionId !== this.missionId ||
      command.clientRequestId !== clientRequestId ||
      command.type !== type ||
      command.simulated
    )
      throw new Error('La respuesta no corresponde al comando solicitado.')
    return command
  }
  async predict(parameters: PredictionParameters, csrfToken: string | null) {
    const prediction = parsePrediction(
      await this.request('/predictions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken ?? '' },
        body: JSON.stringify({
          mode: parameters.mode,
          ...(parameters.mode === 'planned' ? { launchDatetime: parameters.launchDatetime } : {}),
          targetRelativeAltitudeM: parameters.targetRelativeAltitudeM,
          ascentRateMs: parameters.ascentRateMs,
          descentRateMs: parameters.descentRateMs,
        }),
      }),
    )
    if (prediction.missionId !== this.missionId || prediction.source !== 'tawhiri')
      throw new Error('La respuesta no corresponde a una predicción real de esta misión.')
    return prediction
  }
}
