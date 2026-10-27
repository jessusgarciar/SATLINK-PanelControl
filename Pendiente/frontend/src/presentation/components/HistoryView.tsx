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
import MissionIcon from './MissionIcon.tsx'
import GlideSelect from './react-bits/GlideSelect.tsx'

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
  return <Dialog title="Reproducción histórica" onClose={onClose} className="history-dialog mission-dialog">
    <div className="history-shell">
      <section className="operation-hero">
        <p className="mission-eyebrow"><MissionIcon name="archive" /> ARCHIVO DE MISIÓN</p>
        <h3>Vuelve a recorrer el vuelo.</h3>
        <p>Explora las lecturas a su ritmo original o acelera la reproducción.</p>
      <p className="demo-disclosure">{gateway.mode === 'demo' ? 'HISTÓRICO SIMULADO' : 'DATOS HISTÓRICOS'} · Fechas originales · Acciones de operación deshabilitadas.</p>
      <p className="archive-caption">{range.from ? dateTime(range.from) : 'Desde el inicio'} → {dateTime(range.to)} · Fin exclusivo</p>
      </section>
      <div className="archive-toolbar history-controls">
        <button className="button" disabled={state.loading || state.ended || Boolean(state.error)} onClick={() => { onActivity('Histórico: ' + (state.playing ? 'pausa' : 'reproducción')); if (state.playing) controller.pause(); else controller.play() }}>{state.playing ? 'Ⅱ Pausar' : '▶ Reproducir'}</button>
        <button className="button subtle" onClick={() => { onActivity('Histórico: reinicio'); void controller.reset() }}>↺ Reiniciar</button>
        <div className="history-speed"><span>Velocidad</span><GlideSelect ariaLabel="Velocidad de reproducción" size="lg" radius={4} className="orbitium-glide" accentColor="#2563eb" surfaceColor="#ffffff" highlightColor="#dbeafe" textColor="#1e293b" value={String(state.speed)} options={[{ value: '1', label: '1×' }, { value: '5', label: '5×' }, { value: '10', label: '10×' }]} onChange={value => { const speed = Number(value) as 1 | 5 | 10; controller.setSpeed(speed); onActivity('Histórico: velocidad ' + speed + '×') }} /></div>
        <span role="status">{state.loading ? 'Leyendo página…' : state.ended ? 'Fin del histórico' : state.playing ? 'Reproduciendo' : 'En pausa'}</span>
      </div>
      {state.error && <p role="alert" className="tone-amber">{state.error} · Reinicia para reintentar.</p>}
      <dl className="operation-metrics history-readings">
        <Definition label="Reloj histórico">{state.virtualNow === null ? '—' : dateTime(new Date(state.virtualNow).toISOString())}</Definition>
        <Definition label="Última muestra">{dateTime(latest?.receivedAt)}</Definition>
        <Definition label="Temperatura">{number(latest?.temperatureC)} °C</Definition>
        <Definition label="Presión">{number(latest?.pressureHpa)} hPa</Definition>
        <Definition label="Batería">{number(latest?.batteryV, 3)} V</Definition>
      </dl>
      {!state.samples.length && !state.loading && !state.error && <p className="archive-caption">No hay muestras en el intervalo seleccionado.</p>}
      <Suspense fallback={<p>Cargando mapa y gráficas…</p>}>
        <div className="history-map"><MissionMap snapshot={historical} settings={settings} overview /></div>
        <TelemetryCharts samples={decimate(state.samples, 600)} protocol={snapshot.mission.telemetryProtocol} />
      </Suspense>
    </div>
  </Dialog>
}
