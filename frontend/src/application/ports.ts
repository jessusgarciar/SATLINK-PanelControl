import type {
  Command,
  CommandType,
  ConnectionStatus,
  DashboardSnapshot,
  MissionMessage,
  Prediction,
  PredictionParameters,
} from '../domain/mission.ts'
import type { HistoryPage, TelemetryWindow, TimeRange } from '../domain/history.ts'

export interface HistoryGateway {
  window(range: TimeRange, signal: AbortSignal): Promise<TelemetryWindow>
  history(range: TimeRange, cursor: string | null, signal: AbortSignal): Promise<HistoryPage>
  exportCsv(range: TimeRange, signal: AbortSignal): Promise<Blob>
}

export interface MissionGateway extends HistoryGateway {
  readonly mode: 'demo' | 'live'
  readonly realPrediction?: boolean
  load(signal: AbortSignal): Promise<DashboardSnapshot>
  subscribe(
    onMessage: (message: MissionMessage) => void,
    onStatus: (status: ConnectionStatus) => void,
    onError: (message: string) => void,
  ): () => void
  sendCommand(
    type: CommandType,
    clientRequestId: string,
    csrfToken: string | null,
  ): Promise<Command>
  predict(parameters: PredictionParameters, csrfToken: string | null): Promise<Prediction>
  setPaused?(paused: boolean): void
}
