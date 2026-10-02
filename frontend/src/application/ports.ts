import type {
  Command,
  CommandType,
  ConnectionStatus,
  DashboardSnapshot,
  MissionMessage,
  Prediction,
  PredictionParameters,
} from '../domain/mission.ts'

export interface MissionGateway {
  readonly mode: 'demo' | 'live'
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
