import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import type { MissionController } from '../../application/MissionController.ts'
import { dataAgeSeconds, latestSample } from '../../domain/mission.ts'
import { latestReadings } from '../readings.ts'
import { batteryTone, rssiTone, temperatureTone } from '../metricTones.ts'
import type { MapSettings } from '../components/MissionMap.tsx'
import { ageLabel, clock, duration, km, number, phaseLabels } from '../format.ts'
import { useMission, useNow } from '../hooks/useMission.ts'
import { useArchive } from '../hooks/useArchive.ts'
import type { TimeRange, WindowKey } from '../../domain/history.ts'
import ArchiveToolbar from '../components/ArchiveToolbar.tsx'
import CommandPanel from '../components/CommandPanel.tsx'
import { DataCard, Definition, SectionTitle } from '../components/ui.tsx'
import MissionHeader from '../components/MissionHeader.tsx'
import MissionSummary from '../components/MissionSummary.tsx'
import MissionDetails from '../components/MissionDetails.tsx'
import MissionLog from '../components/MissionLog.tsx'
import InstitutionLogos from '../components/InstitutionLogos.tsx'

const MissionMap = lazy(() => import('../components/MissionMap.tsx'))
const TelemetryCharts = lazy(() => import('../components/TelemetryCharts.tsx'))
const RecoveryView = lazy(() => import('../components/RecoveryView.tsx'))
const HistoryView = lazy(() => import('../components/HistoryView.tsx'))
const mqttLabels = { disabled: 'MQTT deshabilitado', connecting: 'Conectando MQTT', connected: 'MQTT suscrito', reconnecting: 'Reconectando MQTT', offline: 'MQTT sin conexión' }

export interface DashboardProps {
  controller: MissionController
  mapSettings: MapSettings
  onModeChange: (mode: 'demo' | 'live') => void
}
export default function Dashboard({ controller, mapSettings, onModeChange }: DashboardProps) {
  const state = useMission(controller)
  const now = useNow()
  const [recoveryOpen, setRecoveryOpen] = useState(false)
  const [windowKey, setWindowKey] = useState<WindowKey>('1h')
  const [replayRange, setReplayRange] = useState<TimeRange | null>(null)
  const snapshot = state.snapshot
  const archive = useArchive(controller.gateway, windowKey, Boolean(snapshot))
  useEffect(() => { if (archive.error) controller.recordTechnical('Archivo: ' + archive.error) }, [controller, archive.error])
  const mission = snapshot?.mission
  const latest = latestSample(snapshot?.telemetry ?? [])
  const { values: readings, observedAt } = useMemo(
    () => latestReadings(snapshot?.telemetry ?? [], mission?.id ?? ''), [snapshot?.telemetry, mission?.id],
  )
  const readingStale = (key: keyof typeof observedAt) => !observedAt[key] ||
    now - Date.parse(observedAt[key]) > (mission?.staleAfterSeconds ?? 15) * 1000
  const age = dataAgeSeconds(latest, now)
  const stale = age === null || age > (mission?.staleAfterSeconds ?? 15)
  const demo = controller.gateway.mode === 'demo'
  const elapsed = mission?.startedAt
    ? ((mission.endedAt ? Date.parse(mission.endedAt) : now) - Date.parse(mission.startedAt)) / 1000
    : null
  const progress =
    readings?.relativeAltitudeM != null && mission
      ? Math.max(
          0,
          Math.min(100, (readings.relativeAltitudeM / mission.targetRelativeAltitudeM) * 100),
        )
      : null
  const releaseEvent = snapshot?.events.find((event) => event.type === 'release')
  return (
    <div className="orbitium-app">
      <a className="skip-link" href="#mission-dashboard">
        Saltar al panel de telemetría
      </a>
      <MissionHeader mission={mission} elapsed={elapsed} mode={controller.gateway.mode} onModeChange={onModeChange} deviceOnline={!stale && state.connection === 'connected' && snapshot?.ingestion?.status === 'connected'} mapSettings={mapSettings} onSaveParameters={controller.saveParameters} />
      <main id="mission-dashboard" className="dashboard-shell">
        <div
          className={
            'connection-strip' + (stale || state.connection !== 'connected' ? ' strip-warning' : '')
          }
        >
          <span className="connection-description">
            <i className="status-dot" />
            <span>
              {demo
                ? state.paused
                  ? 'SEÑAL SIMULADA EN PAUSA'
                  : 'SIMULACIÓN EN TIEMPO REAL'
                : state.connection === 'connected'
                  ? 'FASTAPI CONECTADO'
                  : state.connection === 'reconnecting'
                    ? 'RECONECTANDO CON LA ESTACIÓN'
                    : 'SIN CONEXIÓN A LA ESTACIÓN'}
            </span>
          </span>
          <div className="strip-actions">
            <span>
              {ageLabel(age)}
              {stale && latest ? ' · DATO ANTIGUO' : ''}
            </span>
            {demo ? (
              <button className="text-button" onClick={() => controller.setPaused(!state.paused)}>
                {state.paused ? '▶ Reanudar señal' : 'Ⅱ Pausar señal'}
              </button>
            ) : (
              <button className="text-button" onClick={() => controller.start()}>
                Reintentar
              </button>
            )}
          </div>
        </div>
        {!demo && <p className="mqtt-strip" role="status">{snapshot?.ingestion ? mqttLabels[snapshot.ingestion.status] : 'Estado MQTT no disponible'} · La conexión MQTT no confirma recepción de radio.</p>}
        {demo && (
          <p className="demo-disclosure">
            {controller.gateway.realPrediction && <strong>Predicción mediante Tawhiri real con entradas simuladas. </strong>}
            DATOS DE EJEMPLO · Sin enlace con la cápsula ni comandos físicos.
          </p>
        )}
        {state.error && (
          <div className="inline-error connection-error" role="alert">
            <strong>No se pudo actualizar la misión.</strong>
            <span>{state.error}</span>
            {latest && <span>Últimos datos conservados; comprueba su antigüedad.</span>}
            <button className="button subtle" onClick={() => controller.start()}>
              Reintentar conexión
            </button>
          </div>
        )}
        {state.loading && !snapshot && (
          <div className="loading-state" role="status">
            <span className="loading-pulse" />
            Cargando misión y telemetría…
          </div>
        )}
        {!state.loading && !snapshot && (
          <section className="panel empty-dashboard">
            <h2>La estación aún no está disponible</h2>
            <p>Comprueba que FastAPI esté activo y que la misión configurada exista.</p>
            <button className="button" onClick={() => onModeChange('demo')}>
              Explorar demostración
            </button>
          </section>
        )}
        {snapshot && mission && (
          <>
            <MissionSummary mission={mission} readings={readings} progress={progress} stale={readingStale('relativeAltitudeM')} observedAt={observedAt.relativeAltitudeM} />
            <section className="metrics-primary" aria-label="Estado de la misión">
              <DataCard
                label="Tiempo de vuelo"
                value={duration(elapsed)}
                detail={mission.endedAt ? 'Misión finalizada' : 'Desde el lanzamiento'}
                tone="cyan"
              />
              <DataCard
                label="Watchdog"
                value={elapsed === null ? '—' : duration(mission.watchdogSeconds - elapsed)}
                detail="Referencia · timer en firmware"
                tone="amber"
              />
              <DataCard
                label="Vel. ascenso/desc"
                value={
                  readings?.verticalSpeedMs != null
                    ? (readings.verticalSpeedMs > 0 ? '+' : '') + number(readings.verticalSpeedMs)
                    : '—'
                }
                unit="m/s"
                detail={readings?.verticalSpeedMs == null ? 'No disponible en la telemetría' : 'Reportada por el dispositivo'}
                tone={mission.phase === 'descending' ? 'amber' : 'green'}
                stale={readingStale('verticalSpeedMs')}
              />
              <DataCard
                label="RSSI LoRaWAN"
                value={number(readings?.rssiDbm, 0)}
                unit="dBm"
                detail={'SNR ' + number(readings?.snrDb) + ' dB · ' + mission.region}
                tone={rssiTone(readings?.rssiDbm)}
                stale={readingStale('rssiDbm')}
              />
            </section>
            <section id="mission-sensors" tabIndex={-1} className="metrics-secondary" aria-label="Lecturas de sensores">
              <DataCard
                label="Altitud GPS"
                value={km(readings?.altitudeGpsM)}
                unit="km"
                detail={'s. n. m. · Baro ' + km(readings?.altitudeBarometricM, 2) + ' km'}
                tone="cyan"
                stale={readingStale('altitudeGpsM')}
              />
              <DataCard
                label="Temp. interna"
                value={number(readings?.temperatureC)}
                unit="°C"
                detail="Sensor de la cápsula"
                tone={temperatureTone(readings?.temperatureC)}
                stale={readingStale('temperatureC')}
              />
              <DataCard
                label="Humedad rel."
                value={number(readings?.humidityPct)}
                unit="%"
                detail="Humedad relativa"
                tone="blue"
                stale={readingStale('humidityPct')}
              />
              <DataCard
                label="Presión atm."
                value={number(readings?.pressureHpa)}
                unit="hPa"
                detail="Presión ambiente"
                tone="cyan"
                stale={readingStale('pressureHpa')}
              />
              <DataCard
                label="Voltaje batería"
                value={number(readings?.batteryV, 3)}
                unit="V"
                detail="Medición de alimentación"
                tone={batteryTone(readings?.batteryV)}
                stale={readingStale('batteryV')}
              />
              <DataCard
                label="Último dato"
                value={clock(latest?.receivedAt)}
                detail={
                  latest
                    ? 'Pkt #' + latest.frameCounter + ' · ' + ageLabel(age)
                    : 'Esperando telemetría'
                }
                stale={stale}
              />
            </section>
            <div className="telemetry-layout">
              <div className="position-column">
                <section id="mission-map" tabIndex={-1} className="panel map-panel">
                  <div className="section-heading">
                    <SectionTitle>Trayectoria GPS · Intervalo</SectionTitle>
                    <button className="button amber small" onClick={() => setRecoveryOpen(true)}>
                      ⊞ Recuperación
                    </button>
                  </div>
                  <Suspense fallback={<div className="map-loading">Cargando mapa…</div>}>
                    <MissionMap snapshot={{ ...snapshot, telemetry: archive.data?.track ?? [] }} settings={mapSettings} />
                  </Suspense>
                  <dl className="coordinates-grid">
                    <Definition label="Lat">{number(readings?.latitude, 5)}°</Definition>
                    <Definition label="Lon">{number(readings?.longitude, 5)}°</Definition>
                    <Definition label="Alt GPS · s. n. m.">
                      {km(readings?.altitudeGpsM)} km
                    </Definition>
                    <Definition label="Fase">{phaseLabels[mission.phase]}</Definition>
                  </dl>
                </section>
              </div>
              <Suspense fallback={<div className="panel chart-empty">Cargando gráficas…</div>}>
                <TelemetryCharts samples={archive.data?.series ?? []} sectionId="mission-charts" />
              </Suspense>
            </div>
            <MissionDetails mission={mission} readings={readings} demo={demo} />
            {releaseEvent && (
              <div className="release-event" role="status">
                <strong>EVENTO DE LIBERACIÓN</strong>
                <span>
                  {releaseEvent.message} · {clock(releaseEvent.receivedAt)}
                </span>
              </div>
            )}
            <CommandPanel state={state} controller={controller} now={now} />
            <MissionLog entries={state.technicalLog} />
            <ArchiveToolbar gateway={controller.gateway} selected={windowKey} setSelected={(key) => { setWindowKey(key); controller.recordTechnical('Ventana: ' + key) }} range={archive.data} total={archive.data?.total ?? null} seriesCount={archive.data?.series.length ?? 0} trackCount={archive.data?.track.length ?? 0} loading={archive.loading} error={archive.error} onActivity={controller.recordTechnical} openHistory={() => { if (archive.data) { controller.recordTechnical('Reproducción histórica: intervalo fijado · ' + archive.data.to); setReplayRange({ from: archive.data.from, to: archive.data.to }) } }} />
            <footer className="site-footer">
              <span>SATLINK · system · MISSION DASHBOARD</span>
              <span>
                {demo ? 'SIMULACIÓN' : mission.deviceEui} · LoRaWAN {mission.region} · ChirpStack
              </span>
              <InstitutionLogos />
            </footer>
            {recoveryOpen && (
              <Suspense
                fallback={
                  <div className="loading-overlay" role="status">
                    Abriendo recuperación…
                  </div>
                }
              >
                <RecoveryView
                  state={state}
                  controller={controller}
                  now={now}
                  settings={mapSettings}
                  onClose={() => setRecoveryOpen(false)}
                />
              </Suspense>
            )}
            {replayRange && <Suspense fallback={<p role="status">Abriendo histórico…</p>}><HistoryView gateway={controller.gateway} snapshot={snapshot} range={replayRange} settings={mapSettings} onActivity={controller.recordTechnical} onClose={() => { controller.recordTechnical('Reproducción histórica: cerrada'); setReplayRange(null) }} /></Suspense>}
          </>
        )}
      </main>
    </div>
  )
}
