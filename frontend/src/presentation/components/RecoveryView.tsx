import { lazy, Suspense, useState } from 'react'
import type { MissionController, MissionState } from '../../application/MissionController.ts'
import type { PredictionParameters } from '../../domain/mission.ts'
import { distanceKm, latestSample } from '../../domain/mission.ts'
import { ageLabel, clock, dateTime, duration, km, number } from '../format.ts'
import type { MapSettings } from './MissionMap.tsx'
import { Definition, Dialog, PhaseChip, RangeInput, SectionTitle } from './ui.tsx'

const MissionMap = lazy(() => import('./MissionMap.tsx'))
export default function RecoveryView({
  state,
  controller,
  now,
  settings,
  onClose,
}: {
  state: MissionState
  controller: MissionController
  now: number
  settings: MapSettings
  onClose: () => void
}) {
  const snapshot = state.snapshot!
  const { mission, prediction } = snapshot
  const latest = latestSample(snapshot.telemetry)
  const demo = controller.gateway.mode === 'demo'
  const [parameters, setParameters] = useState<PredictionParameters>(
    prediction?.parameters ?? {
      targetRelativeAltitudeM: mission.targetRelativeAltitudeM,
      ascentRateMs: mission.nominalAscentMs,
      descentRateMs: mission.nominalDescentMs,
      ascentWindDirection: 45,
      ascentWindMs: 8,
      descentWindDirection: 120,
      descentWindMs: 5,
    },
  )
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState(false)
  const update = (key: keyof PredictionParameters) => (value: number) =>
    setParameters((old) => ({ ...old, [key]: value }))
  const age = prediction
    ? Math.max(0, Math.floor((now - Date.parse(prediction.generatedAt)) / 1000))
    : null
  const changed = prediction && JSON.stringify(parameters) !== JSON.stringify(prediction.parameters)
  const canPredict =
    snapshot.permissions.canPredict &&
    state.connection === 'connected' &&
    (demo || Boolean(snapshot.csrfToken)) &&
    (demo || !['descending', 'landed'].includes(mission.phase)) &&
    (demo || age === null || age >= 60)
  const dist =
    prediction && latest?.latitude != null && latest.longitude != null
      ? distanceKm({ latitude: latest.latitude, longitude: latest.longitude }, prediction.landing)
      : null
  const sliders = [
    {
      key: 'targetRelativeAltitudeM' as const,
      label: 'Altitud de liberación · relativa',
      min: 1000,
      max: 30000,
      step: 500,
      unit: 'm',
    },
    {
      key: 'ascentRateMs' as const,
      label: 'Vel. ascenso',
      min: 1,
      max: 10,
      step: 0.1,
      unit: 'm/s',
    },
    {
      key: 'descentRateMs' as const,
      label: 'Vel. descenso al nivel del mar',
      min: 1,
      max: 15,
      step: 0.1,
      unit: 'm/s',
    },
    ...(demo
      ? [
          {
            key: 'ascentWindDirection' as const,
            label: 'Viento asc. · dirección',
            min: 0,
            max: 360,
            step: 1,
            unit: '°',
          },
          {
            key: 'ascentWindMs' as const,
            label: 'Viento asc. · velocidad',
            min: 0,
            max: 30,
            step: 0.5,
            unit: 'm/s',
          },
          {
            key: 'descentWindDirection' as const,
            label: 'Viento desc. · dirección',
            min: 0,
            max: 360,
            step: 1,
            unit: '°',
          },
          {
            key: 'descentWindMs' as const,
            label: 'Viento desc. · velocidad',
            min: 0,
            max: 30,
            step: 0.5,
            unit: 'm/s',
          },
        ]
      : []),
  ]
  return (
    <Dialog
      title="Recuperación · Rastreo y predicción"
      onClose={onClose}
      className="recovery-dialog"
    >
      <div className="recovery-shell">
        <div className="recovery-status">
          <PhaseChip phase={mission.phase} />
          <span className="tiny-badge badge-amber">
            {demo ? 'ESCENARIO SIMULADO' : 'ESTIMACIÓN · NO ES ATERRIZAJE CONFIRMADO'}
          </span>
        </div>
        <div className="recovery-grid">
          <section className="panel recovery-map-panel">
            <SectionTitle>Mapa de trayectoria y aterrizaje predicho</SectionTitle>
            <Suspense fallback={<div className="map-loading">Cargando cartografía…</div>}>
              <MissionMap snapshot={snapshot} settings={settings} overview />
            </Suspense>
            <div className="map-legend">
              <span>
                <i className="legend-dot launch" />
                Lanzamiento
              </span>
              <span>
                <i className="legend-line" />
                Trayectoria recibida
              </span>
              <span>
                <i className="legend-dot release" />
                Liberación estimada
              </span>
              <span>
                <i className="legend-line predicted" />
                Ruta predicha / aterrizaje
              </span>
            </div>
            <p className="helper-text">
              {demo
                ? 'Origen y recorrido ficticios para probar la interfaz.'
                : 'La ruta medida se conserva separada de la predicción.'}
            </p>
          </section>
          <div className="recovery-data">
            <section className="panel">
              <SectionTitle>1 · Datos en tiempo real</SectionTitle>
              <dl className="detail-list">
                <Definition label="Latitud">{number(latest?.latitude, 6)}°</Definition>
                <Definition label="Longitud">{number(latest?.longitude, 6)}°</Definition>
                <Definition label="Altitud GPS · s. n. m." tone="cyan">
                  {km(latest?.altitudeGpsM)} km
                </Definition>
                <Definition label="Recepción local">{clock(latest?.receivedAt)}</Definition>
                <Definition label="Paquete">{latest ? '#' + latest.frameCounter : '—'}</Definition>
              </dl>
              <dl className="stacked-details">
                <Definition label="Lanzamiento">{dateTime(mission.startedAt)}</Definition>
                <Definition label="Punto de despegue">
                  {number(mission.launch.latitude, 5)}°, {number(mission.launch.longitude, 5)}°
                </Definition>
              </dl>
            </section>
            <section className="panel predictor-panel">
              <SectionTitle>2 · Parámetros del predictor</SectionTitle>
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  void controller.predict(parameters)
                }}
              >
                {sliders.map((s) => (
                  <RangeInput
                    key={s.key}
                    label={s.label}
                    value={parameters[s.key]}
                    min={s.min}
                    max={s.max}
                    step={s.step}
                    unit={s.unit}
                    onChange={update(s.key)}
                    disabled={state.predicting}
                  />
                ))}
                <button className="button full-width" disabled={!canPredict || state.predicting}>
                  {state.predicting
                    ? 'Calculando…'
                    : demo
                      ? 'Recalcular escenario'
                      : 'Solicitar predicción'}
                </button>
              </form>
              <p className="helper-text">
                {demo
                  ? 'Vientos constantes de ejemplo. Este escenario no sirve para planear un vuelo real.'
                  : ['descending', 'landed'].includes(mission.phase)
                    ? 'Se conserva la predicción previa. El perfil de descenso requiere validación del backend.'
                    : 'Meteorología y cálculo vía backend. Solicitudes separadas al menos 60 segundos.'}
              </p>
              {changed && (
                <p className="tone-amber helper-text">
                  Parámetros modificados. Recalcula para actualizar el resultado.
                </p>
              )}
              {state.actionError && (
                <p className="inline-error" role="alert">
                  {state.actionError}
                </p>
              )}
            </section>
            <section className="panel prediction-panel">
              <div className="section-heading">
                <SectionTitle amber>Predicción de aterrizaje</SectionTitle>
                {prediction && (
                  <span className={'tiny-badge' + (age! > 120 ? ' badge-amber' : '')}>
                    {ageLabel(age)}
                  </span>
                )}
              </div>
              {prediction ? (
                <>
                  <dl className="detail-list">
                    <Definition label="Lat. estimada" tone="amber">
                      {number(prediction.landing.latitude, 5)}°
                    </Definition>
                    <Definition label="Lon. estimada" tone="amber">
                      {number(prediction.landing.longitude, 5)}°
                    </Definition>
                    <Definition label="Hora de llegada local" tone="amber">
                      {clock(prediction.landing.time)}
                    </Definition>
                    <Definition label="Tiempo restante">
                      {duration((Date.parse(prediction.landing.time) - now) / 1000)}
                    </Definition>
                    <Definition label="Hora de liberación">
                      {clock(prediction.release.time)}
                    </Definition>
                    <Definition label="Dist. desde posición">{number(dist)} km</Definition>
                    <Definition label="Cálculo">{dateTime(prediction.generatedAt)}</Definition>
                    <Definition label="Meteorología">
                      {prediction.weatherAt
                        ? dateTime(prediction.weatherAt)
                        : prediction.source === 'demo'
                          ? 'No aplica · simulación'
                          : 'No disponible'}
                    </Definition>
                  </dl>
                  <button
                    className="button subtle full-width"
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(
                          number(prediction.landing.latitude, 6) +
                            ', ' +
                            number(prediction.landing.longitude, 6),
                        )
                        setCopied(true)
                        setCopyError(false)
                      } catch {
                        setCopyError(true)
                      }
                    }}
                  >
                    {copied ? '✓ Coordenadas copiadas' : 'Copiar coordenadas'}
                  </button>
                  {copyError && (
                    <p role="status" className="helper-text">
                      No se pudo copiar. Selecciona las coordenadas del resultado.
                    </p>
                  )}
                  <p className="helper-text">
                    {prediction.source === 'demo'
                      ? 'Predicción simplificada, sin datos meteorológicos ni incertidumbre validada.'
                      : 'Tawhiri · estimación conservada hasta el siguiente cálculo válido. No confirma recuperación.'}
                  </p>
                </>
              ) : (
                <p className="empty-state">
                  No hay una predicción disponible. Solicita el primer cálculo cuando la estación
                  esté conectada.
                </p>
              )}
            </section>
          </div>
        </div>
      </div>
    </Dialog>
  )
}
