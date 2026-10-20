import { memo } from 'react'
import type { Mission, Telemetry } from '../../domain/mission.ts'
import { km, number, phaseLabels } from '../format.ts'
import Counter from './react-bits/Counter.tsx'
import SloshGauge from './react-bits/SloshGauge.tsx'
import MissionIcon from './MissionIcon.tsx'

const BasicCounter = memo(function BasicCounter({ value }: { value: number }) {
  return <Counter value={value} locale="es-MX" decimals={3} duration={0.28} bounce={0} stagger={0} motionBlur={false} intro={false} fontSize="clamp(30px, 7vw, 56px)" fontWeight={600} textColor="var(--cyan)" gap={0} tabular />
})

export default function MissionSummary({ mission, readings, progress, stale, observedAt }: {
  mission: Mission; readings: Telemetry | null; progress: number | null; stale: boolean; observedAt?: string
}) {
  const altitude = readings?.relativeAltitudeM
  const available = altitude != null && Number.isFinite(altitude)
  return <section id="mission-summary" tabIndex={-1} className={`mission-summary panel${stale ? ' stale-card' : ''}`} aria-label="Resumen de vuelo">
    <div className="mission-summary-readout">
      <p className="mission-eyebrow"><span className="status-dot" /> {phaseLabels[mission.phase]} <span className="mission-live-label">{!available ? 'SIN LECTURA' : stale ? 'DATO ANTIGUO' : 'ÚLTIMA LECTURA'}</span></p>
      <h2>Altitud sobre lanzamiento</h2>
      <div className="mission-hero-value">{available ? <BasicCounter value={Math.round(altitude) / 1000} /> : <strong>—</strong>}<span>km</span></div>
      <p className="mission-altitude-datum">GPS absoluto <strong>{km(readings?.altitudeGpsM)} km</strong> · s. n. m.</p>
      <div className="mission-hero-facts">
        <div><span>Velocidad vertical</span><strong>{readings?.verticalSpeedMs != null && readings.verticalSpeedMs > 0 ? '+' : ''}{number(readings?.verticalSpeedMs)} <small>m/s</small></strong></div>
        <div><span>Objetivo relativo</span><strong>{km(mission.targetRelativeAltitudeM, 1)} <small>km</small></strong></div>
      </div>
      <p className="mission-reading-stamp">{observedAt ? <>Recibido <time dateTime={observedAt}>{new Date(observedAt).toLocaleTimeString('es-MX')}</time></> : 'Esperando lectura de altitud'}</p>
    </div>
    <div className="mission-ascent-instrument">
      <span className="mission-instrument-title">PERFIL DE VUELO</span>
      <div className="mission-instrument-body">
        <div className="mission-flight-column">
          {progress !== null ? <SloshGauge value={progress} interactive={false} showValue={false} liquidColor="#00c8dd" glassColor="#07131f" width={38} height={152} radius={4} ticks={5} viscosity={0.08} tilt={0.04} splash={0} ariaLabel="Progreso hacia altitud objetivo" /> : <div className="mission-gauge-unavailable" aria-label="Progreso no disponible" />}
          {progress !== null && <span className="mission-flight-marker" style={{ bottom: `${Math.max(0, Math.min(100, progress))}%` }}><MissionIcon name="ascent" width={14} height={14} /></span>}
        </div>
        <div className="mission-flight-scale"><span>{km(mission.targetRelativeAltitudeM, 0)} km<small>OBJETIVO</small></span><span>{km(mission.targetRelativeAltitudeM / 2, 1)}</span><span>0 km<small>LANZAMIENTO</small></span></div>
      </div>
      <strong className="mission-progress-value">{number(progress, 1)}<span>%</span></strong>
      <span className="mission-progress-caption">del objetivo{stale ? ' · antiguo' : ''}</span>
    </div>
  </section>
}
