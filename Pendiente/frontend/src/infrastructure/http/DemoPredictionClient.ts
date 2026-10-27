import type { PredictionParameters, Prediction, Telemetry, FlightPhase } from '../../domain/mission.ts'
import { parsePrediction } from './validation.ts'

/** Only prediction leaves the browser; demo telemetry and commands remain local. */
export class DemoPredictionClient {
  private base: string
  constructor(base = '/api/v1') { this.base = base }
  private async request(options: RequestInit = {}) {
    const response = await fetch(this.base.replace(/\/$/, '') + '/demo/predictions', {
      ...options, credentials: 'include', signal: options.signal ?? AbortSignal.timeout(options.method === 'POST' ? 35000 : 12000),
    })
    const body = await response.json()
    if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail :
      'No se pudo consultar Tawhiri. Se conserva la predicción anterior.')
    return body
  }
  async session(signal?: AbortSignal): Promise<{
    enabled: boolean; csrfToken: string | null; nextAllowedAt: string | null; prediction: Prediction | null; predictionHistory: Prediction[]
  }> {
    const body = await this.request({ signal })
    if (typeof body.enabled !== 'boolean' || (body.csrfToken !== null && typeof body.csrfToken !== 'string') ||
      (body.nextAllowedAt !== null && !Number.isFinite(Date.parse(body.nextAllowedAt))))
      throw new Error('Configuración de predicción inválida.')
    const predictionHistory = body.predictionHistory ?? []
    if (!Array.isArray(predictionHistory) || predictionHistory.length > 4) throw new Error('Historial de predicción inválido.')
    const parsedHistory = predictionHistory.map(parsePrediction)
    if (parsedHistory.some(p => p.missionId !== 'satlink-demo' || p.context?.inputSource !== 'simulated'))
      throw new Error('El historial no corresponde a la demostración.')
    return { ...body, prediction: body.prediction === null ? null : parsePrediction(body.prediction), predictionHistory: parsedHistory }
  }
  async predict(p: PredictionParameters, token: string | null, sample: Telemetry | undefined, phase: FlightPhase) {
    const prediction = parsePrediction(await this.request({ method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token ?? '' },
      body: JSON.stringify({ parameters: {
        mode: p.mode,
        ...(p.mode === 'ascending' ? {
          ...(p.launchAltitudeReference ? { launchAltitudeReference: p.launchAltitudeReference } : {}),
          ...(p.gpsAltitudeReference ? { gpsAltitudeReference: p.gpsAltitudeReference } : {}),
        } : {}),
        ...(p.mode === 'planned' ? { launchDatetime: p.launchDatetime,
          ...(p.launch ? { launch: p.launch, launchAltitudeReference: p.launchAltitudeReference } : {}) } : {}),
        targetRelativeAltitudeM: p.targetRelativeAltitudeM, ascentRateMs: p.ascentRateMs, descentRateMs: p.descentRateMs,
      }, phase, sample: sample?.latitude != null && sample.longitude != null && sample.altitudeGpsM != null ? {
        latitude: sample.latitude, longitude: sample.longitude, altitudeM: sample.altitudeGpsM, time: sample.receivedAt,
      } : null }),
    }))
    if (prediction.missionId !== 'satlink-demo' || prediction.source !== 'tawhiri' || prediction.context?.inputSource !== 'simulated')
      throw new Error('La respuesta no corresponde a la demostración con Tawhiri.')
    return prediction
  }
}
