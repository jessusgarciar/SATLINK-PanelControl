import { lazy, Suspense, useEffect, useMemo, useSyncExternalStore } from 'react'
import type { MissionGateway } from '../../application/ports.ts'
import { ReplayController } from '../../application/ReplayController.ts'
import type { DashboardSnapshot } from '../../domain/mission.ts'
import { latestSample } from '../../domain/mission.ts'
import { decimate } from '../../domain/history.ts'
import type { TimeRange } from '../../domain/history.ts'
import type { MapSettings } from './MissionMap.tsx'
import { Dialog, Definition } from './ui.tsx'
import { dateTime, number } from '../format.ts'

const MissionMap = lazy(() => import('./MissionMap.tsx'))
const TelemetryCharts = lazy(() => import('./TelemetryCharts.tsx'))
export default function HistoryView({ gateway, snapshot, range, settings, onClose, onActivity }: {
  gateway: MissionGateway; snapshot: DashboardSnapshot; range: TimeRange; settings: MapSettings; onClose: () => void; onActivity: (message: string) => void
}) {
  const controller = useMemo(() => new ReplayController(gateway, range), [gateway, range])
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot)
  useEffect(() => controller.start(), [controller])
  useEffect(() => { if (state.error) onActivity('Histórico: ' + state.error) }, [state.error, onActivity])
  const latest = latestSample(state.samples)
  const historical: DashboardSnapshot = { ...snapshot, telemetry: decimate(state.samples.filter((t) => t.latitude !== null && t.longitude !== null), 500), commands: [], events: [], prediction: null, ingestion: null, permissions: { canCommand: false, canPredict: false }, csrfToken: null }
  return <Dialog title="Reproducción histórica" onClose={onClose} className="history-dialog">
    <div className="history-shell">
      <p className="demo-disclosure">{gateway.mode === 'demo' ? 'HISTÓRICO SIMULADO' : 'DATOS HISTÓRICOS'} · Fechas originales · Acciones de operación deshabilitadas.</p>
      <p className="archive-caption">{range.from ? dateTime(range.from) : 'Desde el inicio'} → {dateTime(range.to)} · Fin exclusivo</p>
      <div className="archive-toolbar">
        <button className="button" disabled={state.loading || state.ended || Boolean(state.error)} onClick={() => { onActivity('Histórico: ' + (state.playing ? 'pausa' : 'reproducción')); if (state.playing) controller.pause(); else controller.play() }}>{state.playing ? 'Ⅱ Pausar' : '▶ Reproducir'}</button>
        <button className="button subtle" onClick={() => { onActivity('Histórico: reinicio'); void controller.reset() }}>↺ Reiniciar</button>
        <label>Velocidad <select value={state.speed} onChange={(e) => { const speed = Number(e.target.value) as 1 | 5 | 10; controller.setSpeed(speed); onActivity('Histórico: velocidad ' + speed + '×') }}><option value={1}>1×</option><option value={5}>5×</option><option value={10}>10×</option></select></label>
        <span role="status">{state.loading ? 'Leyendo página…' : state.ended ? 'Fin del histórico' : state.playing ? 'Reproduciendo' : 'En pausa'}</span>
      </div>
      {state.error && <p role="alert" className="tone-amber">{state.error} · Reinicia para reintentar.</p>}
      <dl className="device-grid">
        <Definition label="Reloj histórico">{state.virtualNow === null ? '—' : dateTime(new Date(state.virtualNow).toISOString())}</Definition>
        <Definition label="Última muestra">{dateTime(latest?.receivedAt)}</Definition>
        <Definition label="Temperatura">{number(latest?.temperatureC)} °C</Definition>
        <Definition label="Presión">{number(latest?.pressureHpa)} hPa</Definition>
        <Definition label="Batería">{number(latest?.batteryV, 3)} V</Definition>
      </dl>
      {!state.samples.length && !state.loading && !state.error && <p className="archive-caption">No hay muestras en el intervalo seleccionado.</p>}
      <Suspense fallback={<p>Cargando mapa y gráficas…</p>}>
        <div className="history-map"><MissionMap snapshot={historical} settings={settings} overview /></div>
        <TelemetryCharts samples={decimate(state.samples, 600)} />
      </Suspense>
    </div>
  </Dialog>
}
