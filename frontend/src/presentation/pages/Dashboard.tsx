import { lazy, Suspense, useState } from 'react'
import type { MissionController } from '../../application/MissionController.ts'
import { dataAgeSeconds, latestSample } from '../../domain/mission.ts'
import type { MapSettings } from '../components/MissionMap.tsx'
import { ageLabel, clock, duration, km, number, phaseLabels } from '../format.ts'
import { useMission, useNow } from '../hooks/useMission.ts'
import CommandPanel from '../components/CommandPanel.tsx'
import { DataCard, Definition, PhaseChip, SectionTitle } from '../components/ui.tsx'

const MissionMap = lazy(() => import('../components/MissionMap.tsx'))
const TelemetryCharts = lazy(() => import('../components/TelemetryCharts.tsx'))
const RecoveryView = lazy(() => import('../components/RecoveryView.tsx'))

export interface DashboardProps {
  controller: MissionController
  mapSettings: MapSettings
  onModeChange: (mode: 'demo' | 'live') => void
}
export default function Dashboard({ controller, mapSettings, onModeChange }: DashboardProps) {
  const state = useMission(controller)
  const now = useNow()
  const [recoveryOpen, setRecoveryOpen] = useState(false)
  const snapshot = state.snapshot
  const mission = snapshot?.mission
  const latest = latestSample(snapshot?.telemetry ?? [])
  const age = dataAgeSeconds(latest, now)
  const stale = age === null || age > (mission?.staleAfterSeconds ?? 15)
  const demo = controller.gateway.mode === 'demo'
  const elapsed = mission?.startedAt
    ? ((mission.endedAt ? Date.parse(mission.endedAt) : now) - Date.parse(mission.startedAt)) / 1000
    : null
  const progress =
    latest?.relativeAltitudeM != null && mission
      ? Math.max(
          0,
          Math.min(100, (latest.relativeAltitudeM / mission.targetRelativeAltitudeM) * 100),
        )
      : null
  const releaseEvent = snapshot?.events.find((event) => event.type === 'release')
  return (
    <>
      <a className="skip-link" href="#mission-dashboard">
        Saltar al panel de telemetría
      </a>
      <header className="site-header">
        <div className="header-inner">
          <div className="brand">
            <span className="brand-indicator" />
            <div>
              <h1>
                SATLINK<span className="brand-divider">/</span>SYSTEM
              </h1>
              <p>ESTACIÓN TERRENA · CONTROL DE MISIÓN</p>
            </div>
          </div>
          <div className="header-actions">
            <label className="source-picker">
              <span className="sr-only">Fuente de datos</span>
              <select
                value={controller.gateway.mode}
                onChange={(e) => onModeChange(e.target.value as 'demo' | 'live')}
              >
                <option value="demo">DEMOSTRACIÓN</option>
                <option value="live">ESTACIÓN REAL</option>
              </select>
            </label>
            {mission && <PhaseChip phase={mission.phase} />}
            <span className="mission-clock">
              T+ <strong>{duration(elapsed)}</strong>
            </span>
          </div>
        </div>
      </header>
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
                  ? 'ESTACIÓN CONECTADA'
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
        {demo && (
          <p className="demo-disclosure">
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
                  latest?.verticalSpeedMs != null
                    ? (latest.verticalSpeedMs > 0 ? '+' : '') + number(latest.verticalSpeedMs)
                    : '—'
                }
                unit="m/s"
                detail="Derivada · backend"
                tone={mission.phase === 'descending' ? 'amber' : 'green'}
                stale={stale}
              />
              <DataCard
                label="RSSI LoRaWAN"
                value={number(latest?.rssiDbm, 0)}
                unit="dBm"
                detail={'SNR ' + number(latest?.snrDb) + ' dB · ' + mission.region}
                tone="green"
                stale={stale}
              />
            </section>
            <section className="metrics-secondary" aria-label="Lecturas de sensores">
              <DataCard
                label="Altitud GPS"
                value={km(latest?.altitudeGpsM)}
                unit="km"
                detail={'s. n. m. · Baro ' + km(latest?.altitudeBarometricM, 2) + ' km'}
                tone="cyan"
                stale={stale}
              />
              <DataCard
                label="Temp. interna"
                value={number(latest?.temperatureC)}
                unit="°C"
                detail="Sensor de la cápsula"
                stale={stale}
              />
              <DataCard
                label="Humedad rel."
                value={number(latest?.humidityPct)}
                unit="%"
                detail="Humedad relativa"
                stale={stale}
              />
              <DataCard
                label="Presión atm."
                value={number(latest?.pressureHpa)}
                unit="hPa"
                detail="Presión ambiente"
                stale={stale}
              />
              <DataCard
                label="Voltaje batería"
                value={number(latest?.batteryV, 3)}
                unit="V"
                detail="Medición de alimentación"
                tone={latest?.batteryV != null && latest.batteryV < 3.4 ? 'amber' : 'green'}
                stale={stale}
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
                <section className="panel map-panel">
                  <div className="section-heading">
                    <SectionTitle>Trayectoria GPS · Tiempo real</SectionTitle>
                    <button className="button amber small" onClick={() => setRecoveryOpen(true)}>
                      ⊞ Recuperación
                    </button>
                  </div>
                  <Suspense fallback={<div className="map-loading">Cargando mapa…</div>}>
                    <MissionMap snapshot={snapshot} settings={mapSettings} />
                  </Suspense>
                  <dl className="coordinates-grid">
                    <Definition label="Lat">{number(latest?.latitude, 5)}°</Definition>
                    <Definition label="Lon">{number(latest?.longitude, 5)}°</Definition>
                    <Definition label="Alt GPS · s. n. m.">
                      {km(latest?.altitudeGpsM)} km
                    </Definition>
                    <Definition label="Fase">{phaseLabels[mission.phase]}</Definition>
                  </dl>
                </section>
                <section className="panel altitude-panel">
                  <SectionTitle>Altitud relativa / Objetivo</SectionTitle>
                  <div className="altitude-body">
                    <div
                      className="altitude-track"
                      role="progressbar"
                      aria-label="Progreso hacia altitud objetivo"
                      aria-valuenow={progress ?? undefined}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuetext={progress === null ? 'No disponible' : number(progress) + '%'}
                    >
                      <div style={{ height: (progress ?? 0) + '%' }} />
                    </div>
                    <dl className="altitude-details">
                      <Definition label="Altura sobre lanzamiento" tone="cyan">
                        {km(latest?.relativeAltitudeM)} km
                      </Definition>
                      <Definition label="Progreso">{number(progress)}%</Definition>
                      <Definition label="Objetivo relativo">
                        {km(mission.targetRelativeAltitudeM)} km
                      </Definition>
                    </dl>
                    <span className="altitude-reference">
                      GPS
                      <br />+{km(mission.targetRelativeAltitudeM, 0)} km
                    </span>
                  </div>
                </section>
              </div>
              <Suspense fallback={<div className="panel chart-empty">Cargando gráficas…</div>}>
                <TelemetryCharts samples={snapshot.telemetry} />
              </Suspense>
            </div>
            {releaseEvent && (
              <div className="release-event" role="status">
                <strong>EVENTO DE LIBERACIÓN</strong>
                <span>
                  {releaseEvent.message} · {clock(releaseEvent.receivedAt)}
                </span>
              </div>
            )}
            <CommandPanel state={state} controller={controller} now={now} />
            <section className="panel mission-config" aria-label="Configuración de misión">
              <dl>
                <Definition label="Altitud objetivo">
                  +{km(mission.targetRelativeAltitudeM, 0)} km relativos
                </Definition>
                <Definition label="Zona lanzamiento">{mission.launchLabel}</Definition>
                <Definition label="Tasa ascenso nom.">
                  {number(mission.nominalAscentMs, 0)} m/s
                </Definition>
                <Definition label="ETA objetivo · nominal">
                  ~{Math.round(mission.targetRelativeAltitudeM / mission.nominalAscentMs / 60)} min
                </Definition>
                <Definition label="Watchdog">{mission.watchdogSeconds / 60} min</Definition>
                <Definition label="Descenso nominal">
                  {number(mission.nominalDescentMs)} m/s
                </Definition>
                <Definition label="Disparador primario">GPS · firmware</Definition>
                <Definition label="Disparador respaldo">Timer · firmware</Definition>
              </dl>
            </section>
            <footer className="site-footer">
              <span>SATLINK · MISSION DASHBOARD</span>
              <span>
                {demo ? 'SIMULACIÓN' : mission.deviceEui} · LoRaWAN {mission.region} · ChirpStack
              </span>
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
          </>
        )}
      </main>
    </>
  )
}
