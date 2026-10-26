import type {
  Command,
  CommandType,
  ConnectionStatus,
  DashboardSnapshot,
  MissionMessage,
  Mission,
  MissionParameters,
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
  packets?(cursor: string | null, signal: AbortSignal): Promise<PacketPage>
  readonly mode: 'demo' | 'live'
  readonly realPrediction?: boolean
  load(signal: AbortSignal): Promise<DashboardSnapshot>
  saveParameters(parameters: MissionParameters, csrfToken: string | null): Promise<Mission>
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

export interface PacketRecord {
  id: string
  receivedAt: string | null
  ingestedAt: string
  status: 'accepted' | 'rejected'
  reason: string | null
  decoded: Record<string, unknown>
  raw: Record<string, unknown>
  rawBase64: string
}
export interface PacketPage { items: PacketRecord[]; nextCursor: string | null }
