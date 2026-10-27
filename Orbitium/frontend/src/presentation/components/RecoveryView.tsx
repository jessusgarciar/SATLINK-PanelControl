import { lazy, Suspense, useState } from 'react'
import type { MissionController, MissionState } from '../../application/MissionController.ts'
import type { PredictionParameters, Position } from '../../domain/mission.ts'
import { distanceKm, latestPosition, MAX_TARGET_RELATIVE_ALTITUDE_M, predictionUnavailableReason, predictionParametersChanged, validPredictionParameters } from '../../domain/mission.ts'
import { missionPredictionDraft, modePredictions } from '../../domain/predictionWorkspace.ts'
import type { PredictionMode } from '../../domain/predictionWorkspace.ts'
import { ageLabel, clock, dateTime, duration, number } from '../format.ts'
import type { MapSettings } from './MissionMap.tsx'
import { Definition, Dialog, PhaseChip, RangeInput, SectionTitle } from './ui.tsx'
import InstitutionLogos from './InstitutionLogos.tsx'
import './RecoveryView.css'

const MissionMap = lazy(() => import('./MissionMap.tsx'))
function localDatetime(value: string): string {
  const date = new Date(value)
  return Number.isFinite(date.getTime())
    ? new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16) : ''
}
const modeLabel = { planned: 'Planificación', ascending: 'Ascenso' }

export default function RecoveryView({ state, controller, now, settings, onClose }: {
  state: MissionState; controller: MissionController; now: number; settings: MapSettings; onClose: () => void
}) {
  const snapshot = state.snapshot!
  const { mission } = snapshot
  const latest = latestPosition(snapshot.telemetry)
  const simulated = controller.gateway.mode === 'demo'
  const demo = simulated && !controller.gateway.realPrediction
  const [mode, setMode] = useState<PredictionMode>(controller.getPredictionWorkspace().mode)
  const [drafts, setDrafts] = useState(() => {
    const draft = (m: PredictionMode) => controller.getPredictionWorkspace().drafts[m] ?? {
      ...missionPredictionDraft(mission, m, now),
      ...(m === 'planned' && (demo || snapshot.predictionSettings?.launchAltitudeReference === 'MSL')
        ? { launchAltitudeReference: 'MSL' as const } : {}),
      ...(m === 'ascending' && (demo || (snapshot.predictionSettings?.launchAltitudeReference === 'MSL' && snapshot.predictionSettings?.gpsAltitudeReference === 'MSL'))
        ? { launchAltitudeReference: 'MSL' as const, gpsAltitudeReference: 'MSL' as const } : {}),
    }
    return { planned: draft('planned'), ascending: draft('ascending') }
  })
  const [copied, setCopied] = useState<string | null>(null)
  const [compare, setCompare] = useState(false)
  const parameters = drafts[mode]
  const [prediction, previous] = modePredictions(snapshot, mode)
  const changed = prediction && predictionParametersChanged(parameters, {
    ...prediction.parameters, ...(mode === 'planned' && prediction.context ? { launch: prediction.context.origin } : {}),
  }, demo)
  const next = snapshot.predictionSettings?.nextAllowedAt
  const wait = next ? Math.max(0, Math.ceil((Date.parse(next) - now) / 1000)) : 0
  const position = parameters.launch ?? mission.launch
  const invalidOrigin = mode === 'planned' && (!Number.isFinite(position.latitude) || Math.abs(position.latitude) > 90 ||
    !Number.isFinite(position.longitude) || Math.abs(position.longitude) > 180 || !Number.isFinite(position.altitudeM) ||
    position.altitudeM < -500 || position.altitudeM > 65534)
  const draftError = !validPredictionParameters(parameters) ? 'Revisa los parámetros del cálculo.'
    : invalidOrigin ? 'Revisa las coordenadas y la altitud de lanzamiento.'
    : mode === 'planned' && (!parameters.launchDatetime || !Number.isFinite(Date.parse(parameters.launchDatetime)) || Date.parse(parameters.launchDatetime) <= now)
      ? 'Elige una fecha y hora de lanzamiento futura.'
    : mode === 'planned' && parameters.launchAltitudeReference !== 'MSL' ? 'Confirma la altitud de lanzamiento sobre el nivel del mar.' : null
  const unavailable = state.connection !== 'connected' ? 'Conecta con la estación para calcular.'
    : draftError ?? (demo ? null : snapshot.predictionError ?? predictionUnavailableReason(snapshot, parameters, now))
  const canPredict = snapshot.permissions.canPredict && !unavailable && !state.predicting
  const age = prediction ? Math.max(0, Math.floor((now - Date.parse(prediction.generatedAt)) / 1000)) : null
  const dist = prediction && latest?.latitude != null && latest.longitude != null
    ? distanceKm({ latitude: latest.latitude, longitude: latest.longitude }, prediction.landing) : null
  const patch = (changes: Partial<PredictionParameters>) => {
    const updated = { ...parameters, ...changes }
    setDrafts(old => ({ ...old, [mode]: updated }))
    controller.savePredictionDraft(mode, updated)
    controller.clearPredictionError()
  }
  const selectMode = (value: PredictionMode) => {
    controller.savePredictionDraft(mode, parameters)
    controller.selectPredictionMode(value)
    setMode(value); setCompare(false); setCopied(null); controller.clearPredictionError()
  }
  const reset = () => patch({ ...missionPredictionDraft(mission, mode, now),
    launchAltitudeReference: demo || snapshot.predictionSettings?.launchAltitudeReference === 'MSL' ? 'MSL' : undefined,
    gpsAltitudeReference: mode === 'ascending' && (demo || snapshot.predictionSettings?.gpsAltitudeReference === 'MSL') ? 'MSL' : undefined })
  const setPosition = (key: keyof Position, value: string) => patch({ launch: { ...position, [key]: value === '' ? NaN : Number(value) } })
  const fields = [
    { key: 'targetRelativeAltitudeM' as const, label: mission.altitudeTargetMode === 'absolute' ? 'Altitud de corte · m s. n. m.' : 'Altitud de corte · m sobre el lanzamiento', min: 1000, max: MAX_TARGET_RELATIVE_ALTITUDE_M, step: 1 },
    { key: 'ascentRateMs' as const, label: 'Velocidad de ascenso · m/s', min: 1, max: 10, step: 0.1 },
    { key: 'descentRateMs' as const, label: 'Velocidad de descenso · m/s', min: 1, max: 15, step: 0.1 },
  ]
  const copy = async (kind: string, value: string) => {
    try { await navigator.clipboard.writeText(value); setCopied(kind) }
    catch { setCopied('error') }
  }
  return <Dialog title="Rastreo y predicción" onClose={onClose} className="recovery-dialog mission-dialog">
    <div className="recovery-shell prediction-workspace">
      <header className="prediction-intro">
        <div><p className="mission-eyebrow">PREDICCIÓN DE ATERRIZAJE</p><h3>¿Qué predicción quieres consultar?</h3><p>Elige el momento del vuelo, revisa los datos y calcula.</p></div>
        <div className="recovery-status"><PhaseChip phase={mission.phase} /><span className="tiny-badge badge-amber">{demo ? 'ESCENARIO SIMULADO' : simulated ? 'TAWHIRI · ENTRADAS SIMULADAS' : 'ESTIMACIÓN'}</span></div>
      </header>
      <div className="prediction-mode-picker" role="group" aria-label="Tipo de predicción">
        {(['planned', 'ascending'] as const).map(value => <button key={value} type="button" aria-pressed={mode === value}
          disabled={state.predicting} onClick={() => selectMode(value)}>
          <strong>{modeLabel[value]}</strong><span>{value === 'planned' ? 'Antes del vuelo · lugar y hora de lanzamiento' : 'Durante la subida · último GPS recibido'}</span>
        </button>)}
      </div>
      <div className={'prediction-readiness' + (unavailable ? ' is-blocked' : '')} role="status" aria-live="polite">
        <strong>{state.predicting ? 'Calculando la trayectoria…' : unavailable ?? 'Listo para calcular'}</strong>
        <span>{state.predicting ? 'El resultado anterior se conserva mientras llega la respuesta.'
          : unavailable ? 'Tus ajustes se conservan. Resuelve este paso para continuar.' : `${modeLabel[mode]}: revisa los parámetros y pulsa el botón de cálculo.`}</span>
        {!demo && (!snapshot.predictionSettings?.enabled || snapshot.predictionError || state.connection !== 'connected') &&
          <button type="button" className="button subtle" onClick={() => void controller.refresh()}>Comprobar conexión y permisos</button>}
      </div>
      <div className="recovery-grid">
        <div className="recovery-data prediction-controls">
          <section className="panel predictor-panel" id="recovery-parameters" aria-label={`Configurar ${modeLabel[mode]}`}>
            <SectionTitle>1 · Configura {modeLabel[mode].toLowerCase()}</SectionTitle>
            <form onSubmit={async event => {
              event.preventDefault()
              if (!canPredict) return
              controller.savePredictionDraft(mode, parameters)
              await controller.predict(parameters)
            }}>
              <fieldset disabled={state.predicting}>
                {mode === 'planned' ? <>
                  <label className="prediction-field"><span>Fecha y hora de lanzamiento</span>
                    <input type="datetime-local" required value={localDatetime(parameters.launchDatetime ?? '')} onChange={event => {
                      const date = new Date(event.target.value)
                      patch({ launchDatetime: Number.isFinite(date.getTime()) ? date.toISOString() : undefined })
                    }} />
                    <small>Hora local · {Intl.DateTimeFormat().resolvedOptions().timeZone}</small>
                  </label>
                  <div className="prediction-origin-summary"><strong>Lugar de lanzamiento</strong><span>{number(position.latitude, 5)}°, {number(position.longitude, 5)}° · {number(position.altitudeM, 0)} m s. n. m.</span></div>
                  <details className="prediction-location-editor"><summary>Editar lugar y altitud</summary>
                    {([{ key: 'latitude', label: 'Latitud · grados', min: -90, max: 90 }, { key: 'longitude', label: 'Longitud · grados', min: -180, max: 180 }, { key: 'altitudeM', label: 'Altitud de lanzamiento · m s. n. m.', min: -500, max: 65534 }] as const).map(field =>
                      <label key={field.key} className="prediction-field"><span>{field.label}</span><input type="number" required step="any" min={field.min} max={field.max} value={Number.isFinite(position[field.key]) ? position[field.key] : ''} onChange={e => setPosition(field.key, e.target.value)} /></label>)}
                    <p className="helper-text">Estos cambios se usan en esta planificación. El sitio oficial de misión se conserva.</p>
                  </details>
                  <label className="prediction-confirm"><input type="checkbox" checked={parameters.launchAltitudeReference === 'MSL'} onChange={e => patch({ launchAltitudeReference: e.target.checked ? 'MSL' : undefined })} /> Altitud de lanzamiento referida al nivel del mar (MSL).</label>
                </> : <><div className="prediction-gps-summary">
                  <strong>Origen automático · último GPS válido</strong>
                  <p>{latest ? `${number(latest.latitude, 5)}°, ${number(latest.longitude, 5)}° · ${number(latest.altitudeGpsM, 0)} m s. n. m.` : 'Todavía no hay una posición GPS.'}</p>
                  <p className="helper-text">{latest ? `Recibido: ${dateTime(latest.receivedAt)} · ${ageLabel(Math.max(0, Math.floor((now - Date.parse(latest.receivedAt)) / 1000)))}` : 'Espera un paquete con ubicación para calcular.'}</p>
                  <p className="helper-text">El próximo cálculo usará el paquete válido más reciente. Seleccionar Ascenso no cambia la fase de misión.</p>
                </div><label className="prediction-confirm"><input type="checkbox"
                  checked={parameters.launchAltitudeReference === 'MSL' && parameters.gpsAltitudeReference === 'MSL'}
                  onChange={e => patch({ launchAltitudeReference: e.target.checked ? 'MSL' : undefined, gpsAltitudeReference: e.target.checked ? 'MSL' : undefined })} />
                  Las altitudes de lanzamiento y GPS están referidas al nivel del mar (MSL).
                </label></>}
                <div className="prediction-numbers">{fields.map(field => <label className="prediction-field" key={field.key}>
                  <span>{field.label}</span><input type="number" required min={field.min} max={field.max} step={field.step}
                    value={Number.isFinite(parameters[field.key]) ? parameters[field.key] : ''} onChange={e => patch({ [field.key]: e.target.value === '' ? NaN : Number(e.target.value) })} />
                </label>)}</div>
                <p className="helper-text">Descenso: velocidad de referencia al nivel del mar; varía con la altura en el modelo.</p>
                {demo && <details><summary>Vientos del escenario simulado</summary>{([
                  ['ascentWindDirection', 'Dirección en ascenso', 360, '°'], ['ascentWindMs', 'Viento en ascenso', 30, 'm/s'],
                  ['descentWindDirection', 'Dirección en descenso', 360, '°'], ['descentWindMs', 'Viento en descenso', 30, 'm/s'],
                ] as const).map(([key, label, max, unit]) => <RangeInput key={key} label={label} value={parameters[key]} min={0} max={max} step={1} unit={unit} onChange={value => patch({ [key]: value })} />)}</details>}
                <button type="button" className="text-button prediction-reset" onClick={reset}>Restaurar valores de misión</button>
              </fieldset>
              {changed && <div className="prediction-pending" role="status"><strong>Cambios pendientes de calcular</strong>
                <p>El mapa conserva el resultado anterior de {modeLabel[mode].toLowerCase()}.</p>
                {(['ascentRateMs', 'descentRateMs'] as const).filter(key => parameters[key] !== prediction.parameters[key]).map(key =>
                  <p key={key}>{key === 'ascentRateMs' ? 'Ascenso' : 'Descenso'}: {number(prediction.parameters[key], 1)} → {number(parameters[key], 1)} m/s</p>)}
              </div>}
              <button className="button full-width prediction-calculate" disabled={!canPredict}>
                {state.predicting ? 'Calculando…' : wait > 0 && !demo ? `Disponible en ${wait} s` : mode === 'planned' ? 'Calcular planificación' : 'Actualizar predicción de ascenso'}
              </button>
              {unavailable && <p className="helper-text tone-amber" role="status">{unavailable}</p>}
              {mode === 'ascending' && unavailable?.includes('GPS válido y reciente') &&
                <button type="button" className="button subtle full-width" onClick={() => selectMode('planned')}>Usar Planificación mientras llega GPS</button>}
              <p className="helper-text">{demo ? 'Escenario simulado con vientos de ejemplo.' : 'Un cálculo por minuto. La espera también aplica si falla la consulta.'}</p>
              {state.predictionActionError && <p className="inline-error" role="alert">{state.predictionActionError}</p>}
            </form>
          </section>
          <details className="panel prediction-telemetry"><summary>Ver telemetría recibida</summary><dl className="detail-list">
            <Definition label="Posición">{number(latest?.latitude, 5)}°, {number(latest?.longitude, 5)}°</Definition>
            <Definition label="Altitud GPS">{number(latest?.altitudeGpsM, 0)} m s. n. m.</Definition>
            <Definition label="Recepción">{dateTime(latest?.receivedAt)}</Definition>
            <Definition label="Paquete">{latest ? `#${latest.frameCounter}` : '—'}</Definition>
          </dl></details>
        </div>
        <div className="prediction-output">
          <section className="panel prediction-panel" id="recovery-result">
            <div className="section-heading"><SectionTitle amber>2 · Resultado de {modeLabel[mode].toLowerCase()}</SectionTitle>{prediction && <span className="tiny-badge">{ageLabel(age)}</span>}</div>
            {prediction ? <>
              <p className="helper-text">Calculado: {dateTime(prediction.generatedAt)}{changed ? ' · Conservado mientras ajustas los parámetros.' : ''}</p>
              <dl className="prediction-result-metrics">
                <Definition label="Aterrizaje estimado" tone="amber">{number(prediction.landing.latitude, 5)}°, {number(prediction.landing.longitude, 5)}°</Definition>
                <Definition label="Llegada local">{dateTime(prediction.landing.time)}</Definition>
                <Definition label="Tiempo hasta llegada">{duration((Date.parse(prediction.landing.time) - now) / 1000)}</Definition>
                <Definition label="Distancia desde GPS">{number(dist, 2)} km</Definition>
              </dl>
              <p className="prediction-used">Usó ascenso <strong>{number(prediction.parameters.ascentRateMs, 1)} m/s</strong> · descenso <strong>{number(prediction.parameters.descentRateMs, 1)} m/s</strong> · corte <strong>{number(prediction.parameters.targetRelativeAltitudeM, 0)} m</strong> {mission.altitudeTargetMode === 'absolute' ? 's. n. m.' : 'sobre lanzamiento'}</p>
              {previous && <><button type="button" className="button subtle" aria-expanded={compare} onClick={() => setCompare(!compare)}>Comparar con anterior</button>
                {compare && <div className="prediction-comparison"><strong>Comparación con {dateTime(previous.generatedAt)}</strong>
                  <p>Separación entre aterrizajes: {number(distanceKm(previous.landing, prediction.landing), 3)} km.</p>
                  <p>Diferencia de llegada (nuevo − anterior): {number((Date.parse(prediction.landing.time) - Date.parse(previous.landing.time)) / 60, 1)} min.</p>
                  <p>Ascenso: {number(previous.parameters.ascentRateMs, 1)} → {number(prediction.parameters.ascentRateMs, 1)} m/s · descenso: {number(previous.parameters.descentRateMs, 1)} → {number(prediction.parameters.descentRateMs, 1)} m/s.</p>
                  <small>También pueden variar origen, hora, altitud y meteorología. Esta comparación no aísla el efecto de las velocidades.</small>
                </div>}</>}
            </> : <p className="empty-state">Aún no hay un resultado de {modeLabel[mode].toLowerCase()}. Revisa los datos del paso 1 y calcula para ver la ruta.</p>}
          </section>
          <section className="panel recovery-map-panel" id="recovery-map">
            <SectionTitle>Mapa · {modeLabel[mode]}</SectionTitle>
            <Suspense fallback={<div className="map-loading">Cargando mapa…</div>}><MissionMap snapshot={{ ...snapshot, prediction: prediction ?? null }} settings={settings} overview /></Suspense>
            <div className="map-legend"><span><i className="legend-line" /> Trayectoria {simulated ? 'simulada' : 'recibida'}</span><span><i className="legend-line predicted" /> Predicción de {modeLabel[mode].toLowerCase()}</span></div>
            <p className="helper-text">La ruta recibida y la estimación se muestran por separado. La estimación no confirma el aterrizaje.</p>
          </section>
          {prediction && <details className="panel prediction-technical"><summary>Detalles del cálculo y exportación</summary>
            <dl className="detail-list"><Definition label="Fuente">{prediction.source === 'demo' ? 'Simulación' : 'Tawhiri'}</Definition>
              <Definition label="Meteorología">{prediction.weatherAt ? dateTime(prediction.weatherAt) : 'Fecha no disponible'}</Definition>
              <Definition label="Dataset">{prediction.context?.dataset ?? 'No disponible'}</Definition>
              <Definition label="Origen">{number(prediction.context?.origin.latitude, 5)}°, {number(prediction.context?.origin.longitude, 5)}°</Definition>
              <Definition label="Hora de liberación">{clock(prediction.release.time)}</Definition>
            </dl>
            <div className="prediction-export"><button className="button subtle" onClick={() => void copy('coordinates', `${prediction.landing.latitude}, ${prediction.landing.longitude}`)}>Copiar coordenadas</button>
              {prediction.context && <><button className="button subtle" onClick={() => {
                const c = prediction.context!
                void copy('parameters', JSON.stringify({ profile: 'standard_profile', launch_latitude: c.origin.latitude, launch_longitude: (c.origin.longitude + 360) % 360,
                  launch_altitude: c.origin.altitudeM, launch_datetime: c.originAt, burst_altitude: prediction.release.altitudeM,
                  ascent_rate: prediction.parameters.ascentRateMs, descent_rate: prediction.parameters.descentRateMs, dataset: c.dataset }, null, 2))
              }}>Copiar parámetros para SondeHub</button><a className="button subtle" href="https://predict.sondehub.org/" target="_blank" rel="noreferrer">Abrir SondeHub Predictor ↗</a></>}
            </div>{copied && <p role="status" className="helper-text">{copied === 'error' ? 'No se pudo copiar. Selecciona los datos del resultado.' : 'Datos copiados.'}</p>}
          </details>}
        </div>
      </div>
      <InstitutionLogos />
    </div>
  </Dialog>
}
