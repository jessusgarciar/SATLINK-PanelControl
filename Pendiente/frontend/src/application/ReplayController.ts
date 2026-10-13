import type { HistoryGateway } from './ports.ts'
import type { TimeRange } from '../domain/history.ts'
import type { Telemetry } from '../domain/mission.ts'

export interface ReplayState {
  samples: Telemetry[]
  virtualNow: number | null
  playing: boolean
  loading: boolean
  ended: boolean
  speed: 1 | 5 | 10
  error: string | null
}
/** La reproducción del Ejercicio 10 conserva las fechas de las mediciones guardadas. */
export class ReplayController {
  private gateway: HistoryGateway
  readonly range: TimeRange
  private state: ReplayState = { samples: [], virtualNow: null, playing: false, loading: false, ended: false, speed: 1, error: null }
  private pending: Telemetry[] = []
  private cursor: string | null = null
  private hasMore = true
  private abort: AbortController | null = null
  private generation = 0
  private listeners = new Set<() => void>()
  private timer: ReturnType<typeof setInterval> | null = null
  private lastTick = 0
  constructor(gateway: HistoryGateway, range: TimeRange) { this.gateway = gateway; this.range = { ...range } }
  getSnapshot = () => this.state
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  private update(patch: Partial<ReplayState>) { this.state = { ...this.state, ...patch }; this.listeners.forEach((listener) => listener()) }
  private async page() {
    if (!this.hasMore || this.state.loading) return
    const abort = new AbortController(), generation = this.generation
    this.abort = abort
    this.update({ loading: true, error: null })
    try {
      const page = await this.gateway.history(this.range, this.cursor, abort.signal)
      if (abort.signal.aborted || generation !== this.generation) return
      if (page.nextCursor !== null && page.nextCursor === this.cursor) throw new Error('El archivo devolvió un cursor repetido.')
      this.pending = page.items
      this.cursor = page.nextCursor
      this.hasMore = page.nextCursor !== null
      this.update({ loading: false })
    } catch (error) {
      if (!abort.signal.aborted && generation === this.generation) this.update({ loading: false, playing: false, error: error instanceof Error ? error.message : 'No se pudo leer el histórico.' })
    }
  }
  start = () => {
    this.dispose()
    void this.reset()
    this.lastTick = performance.now()
    this.timer = setInterval(() => { const now = performance.now(); void this.advance(now - this.lastTick); this.lastTick = now }, 100)
    return this.dispose
  }
  reset = async () => {
    this.generation++; this.abort?.abort()
    const generation = this.generation
    this.pending = []; this.cursor = null; this.hasMore = true
    this.update({ samples: [], virtualNow: null, playing: false, ended: false, loading: false, error: null })
    await this.page()
    if (generation !== this.generation) return
    if (this.pending.length) {
      const first = this.pending.shift()!
      this.update({ samples: [first], virtualNow: Date.parse(first.receivedAt) })
    } else if (!this.hasMore && !this.state.error) this.update({ ended: true })
  }
  play = () => { if (!this.state.ended && !this.state.error) { this.lastTick = performance.now(); this.update({ playing: true }) } }
  pause = () => this.update({ playing: false })
  setSpeed = (speed: 1 | 5 | 10) => this.update({ speed })
  advance = async (elapsedMs: number) => {
    if (!this.state.playing || this.state.loading || this.state.virtualNow === null) return
    const now = this.state.virtualNow + Math.max(0, elapsedMs) * this.state.speed
    const emitted: Telemetry[] = []
    while (this.pending.length && Date.parse(this.pending[0].receivedAt) <= now) emitted.push(this.pending.shift()!)
    this.update({ virtualNow: now, samples: [...this.state.samples, ...emitted].slice(-1200) })
    if (!this.pending.length) {
      if (this.hasMore) await this.page()
      else this.update({ playing: false, ended: true, virtualNow: Date.parse(this.state.samples.at(-1)!.receivedAt) })
    }
  }
  dispose = () => {
    this.generation++; this.abort?.abort()
    if (this.timer) clearInterval(this.timer)
    this.timer = null
    this.update({ playing: false })
  }
}
