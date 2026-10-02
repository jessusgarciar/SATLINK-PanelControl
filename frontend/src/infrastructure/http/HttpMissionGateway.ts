import type { MissionGateway } from '../../application/ports.ts'
import type {
  CommandType,
  ConnectionStatus,
  MissionMessage,
  PredictionParameters,
} from '../../domain/mission.ts'
import { subscribeMission } from '../websocket/missionStream.ts'
import { parseCommand, parsePrediction, parseSnapshot } from './validation.ts'

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
        }
        throw new Error(
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
