import { lazy, Suspense, useState } from 'react'
import type { PredictionParameters, Position } from '../../domain/mission.ts'
import { predictionUnavailableReason } from '../../domain/mission.ts'
import type { MissionController, MissionState } from '../../application/MissionController.ts'
import type { MapSettings } from './MissionMap.tsx'
import { Dialog } from './ui.tsx'

const PlanningMap = lazy(() => import('./PlanningMap.tsx'))
export default function PlanningDialog({ state, controller, parameters, settings, now, onClose, onGenerated }: {
  state: MissionState; controller: MissionController; parameters: PredictionParameters; settings: MapSettings;
  now: number; onClose: () => void; onGenerated: (p: PredictionParameters) => void;
}) {
  const [position, setPosition] = useState<Position>(parameters.launch ?? state.snapshot!.mission.launch)
  const [date, setDate] = useState(() => {
    const value = new Date(parameters.launchDatetime ?? Date.now() + 3600000)
    return new Date(value.getTime() - value.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
  })
  const [msl, setMsl] = useState(false)
  const demo = controller.gateway.mode === 'demo' && !controller.gateway.realPrediction
  const validDate = Boolean(date) && Number.isFinite(Date.parse(date))
  const request: PredictionParameters = { ...parameters, mode: 'planned', launch: position,
    launchAltitudeReference: 'MSL', launchDatetime: validDate ? new Date(date).toISOString() : undefined }
  const coordinatesValid = Number.isFinite(position.latitude) && Math.abs(position.latitude) <= 90 &&
    Number.isFinite(position.longitude) && Math.abs(position.longitude) <= 180 && Number.isFinite(position.altitudeM) &&
    position.altitudeM >= -500 && position.altitudeM <= 65534
  const reason = !coordinatesValid ? 'Revisa las coordenadas y la altitud.' : !validDate || Date.parse(date) <= now ?
    'Elige una fecha y hora futura.' : !msl ? 'Confirma la referencia de altitud.' :
    demo ? null : predictionUnavailableReason(state.snapshot!, request, now)
  return <Dialog title="Planificación independiente" onClose={onClose} className="planning-dialog">
    <form onSubmit={async (event) => {
      event.preventDefault()
      if (reason || state.predicting || state.connection !== 'connected') return
      const result = await controller.predict(request)
      if (result) { onGenerated(request); onClose() }
    }}>
      <p className="helper-text">Elige un lugar y una fecha para este cálculo. El lugar oficial de la misión se conserva.</p>
      <div className="planning-grid">
        <div>
          <Suspense fallback={<div className="map-loading">Cargando cartografía…</div>}>
            <PlanningMap position={{ ...position,
              latitude: Number.isFinite(position.latitude) && Math.abs(position.latitude) <= 90 ? position.latitude : state.snapshot!.mission.launch.latitude,
              longitude: Number.isFinite(position.longitude) && Math.abs(position.longitude) <= 180 ? position.longitude : state.snapshot!.mission.launch.longitude,
            }} onChange={point => setPosition(old => ({ ...point, altitudeM: old.altitudeM }))} settings={settings} />
          </Suspense>
          <p className="helper-text">Haz clic en el mapa o arrastra el marcador. También puedes escribir las coordenadas.</p>
        </div>
        <div className="planning-fields">
          <label className="prediction-field"><span>Fecha y hora de lanzamiento</span><input type="datetime-local" required value={date} onChange={e => setDate(e.target.value)} />
            <small>Zona: {Intl.DateTimeFormat().resolvedOptions().timeZone} · UTC: {request.launchDatetime ?? '—'}</small></label>
          {([{ key: 'latitude', label: 'Latitud · grados', min: -90, max: 90 }, { key: 'longitude', label: 'Longitud · grados', min: -180, max: 180 },
            { key: 'altitudeM', label: 'Altitud de lanzamiento · m s. n. m.', min: -500, max: 65534 }] as const).map(field =>
            <label key={field.key} className="prediction-field"><span>{field.label}</span><input type="number" required step="any" min={field.min} max={field.max}
              value={Number.isFinite(position[field.key]) ? position[field.key] : ''} onChange={e => setPosition(old => ({ ...old, [field.key]: e.target.value === '' ? NaN : Number(e.target.value) }))} /></label>)}
          <label className="helper-text"><input type="checkbox" checked={msl} onChange={e => setMsl(e.target.checked)} /> Confirmo que la altitud está referida al nivel del mar (MSL).</label>
          <p className="helper-text">El mapa no calcula la altitud. Se usarán los parámetros de Recuperación: liberación {parameters.targetRelativeAltitudeM} m, ascenso {parameters.ascentRateMs} m/s y descenso {parameters.descentRateMs} m/s.
            {demo ? ' Modo demostración: resultado simulado.' : controller.gateway.realPrediction ? ' Tawhiri real con entradas simuladas.' : ''}</p>
          <button className="button full-width" disabled={Boolean(reason) || state.predicting || state.connection !== 'connected'}>{state.predicting ? 'Calculando…' : 'Generar predicción'}</button>
          {reason && <p role="status" className="helper-text tone-amber">{reason}</p>}
          {state.actionError && <p role="alert" className="inline-error">{state.actionError}</p>}
        </div>
      </div>
    </form>
  </Dialog>
}
