import type { HistoryGateway } from './ports.ts'
import type { TelemetryWindow, TimeRange } from '../domain/history.ts'

export class WindowController {
  private state: { data: TelemetryWindow | null; loading: boolean; error: string | null } = { data: null, loading: false, error: null }
  private listeners = new Set<() => void>()
  private abort: AbortController | null = null
  private generation = 0
  private gateway: HistoryGateway
  constructor(gateway: HistoryGateway) { this.gateway = gateway }
  getSnapshot = () => this.state
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  private update(patch: Partial<typeof this.state>) { this.state = { ...this.state, ...patch }; this.listeners.forEach((listener) => listener()) }
  load = async (range: TimeRange) => {
    this.abort?.abort()
    const abort = new AbortController(), generation = ++this.generation
    this.abort = abort
    this.update({ loading: true, error: null })
    try {
      const data = await this.gateway.window(range, abort.signal)
      if (!abort.signal.aborted && generation === this.generation) this.update({ data, loading: false })
    } catch (error) {
      if (!abort.signal.aborted && generation === this.generation) this.update({ loading: false, error: error instanceof Error ? error.message : 'No se pudo consultar el archivo.' })
    }
  }
  dispose = () => { this.generation++; this.abort?.abort() }
}
