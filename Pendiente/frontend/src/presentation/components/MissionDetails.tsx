import type { Mission, Telemetry } from '../../domain/mission.ts'
import { km, number } from '../format.ts'
import Carousel from './react-bits/Carousel.tsx'
import MissionIcon from './MissionIcon.tsx'
import { Definition } from './ui.tsx'

const flag = (value: boolean | null | undefined) => value == null ? 'Desconocido' : value ? 'Sí' : 'No'

export default function MissionDetails({ mission, readings, demo }: { mission: Mission; readings: Telemetry | null; demo: boolean }) {
  const cards = [
    <article key="gnss" className="mission-detail-card"><div className="mission-detail-heading"><MissionIcon name="map" /><span>01 / GNSS</span></div><h3>Posicionamiento</h3><dl className="mission-detail-grid">
      <Definition label="GPS activo">{flag(readings?.device?.gpsActive)}</Definition><Definition label="Fix GPS">{flag(readings?.device?.gpsFix)}</Definition><Definition label="Satélites">{number(readings?.device?.satellites, 0)}</Definition><Definition label="Referencia">GPS · s. n. m.</Definition>
    </dl><p className="mission-detail-note">Metadatos reportados por el dispositivo.</p></article>,
    <article key="power" className="mission-detail-card"><div className="mission-detail-heading"><MissionIcon name="device" /><span>02 / ENERGÍA</span></div><h3>Alimentación</h3><dl className="mission-detail-grid">
      <Definition label="Batería reportada">{number(readings?.device?.batteryPct, 0)} %</Definition><Definition label="Cargando">{flag(readings?.device?.charging)}</Definition><Definition label="Sin batería / USB">{flag(readings?.device?.usbPowered)}</Definition><Definition label="Voltaje">{number(readings?.batteryV, 3)} V</Definition>
    </dl><p className="mission-detail-note">Porcentaje recibido; no estimado desde el voltaje.</p></article>,
    <article key="radio" className="mission-detail-card"><div className="mission-detail-heading"><MissionIcon name="radio" /><span>03 / LORAWAN</span></div><h3>Enlace de radio</h3><dl className="mission-detail-grid">
      <Definition label="Gateway">{readings?.radio?.gatewayId ?? '—'}</Definition><Definition label="Frecuencia">{readings?.radio?.frequencyHz == null ? '—' : number(readings.radio.frequencyHz / 1e6, 3) + ' MHz'}</Definition><Definition label="Data Rate">{readings?.radio?.dataRate == null ? '—' : 'DR' + readings.radio.dataRate}</Definition><Definition label="Puerto">{number(readings?.radio?.fPort, 0)}</Definition><Definition label="Región">{mission.region}</Definition><Definition label="SNR">{number(readings?.snrDb)} dB</Definition>
    </dl></article>,
    <article key="plan" className="mission-detail-card"><div className="mission-detail-heading"><MissionIcon name="ascent" /><span>04 / PLAN DE VUELO</span></div><h3>Referencias de misión</h3><dl className="mission-detail-grid">
      <Definition label={mission.altitudeTargetMode === 'absolute' ? 'Altitud objetivo' : 'Objetivo relativo'}>{km(mission.targetRelativeAltitudeM, 0)} km</Definition><Definition label="Ascenso nominal">{number(mission.nominalAscentMs, 1)} m/s</Definition><Definition label="Descenso nominal">{number(mission.nominalDescentMs, 1)} m/s</Definition><Definition label="ETA nominal">~{Math.round(Math.max(0, mission.targetRelativeAltitudeM - (mission.altitudeTargetMode === 'absolute' ? mission.launch.altitudeM : 0)) / mission.nominalAscentMs / 60)} min</Definition>
    </dl><p className="mission-detail-note">Origen: {mission.launchLabel}. Referencias nominales, no predicción.</p></article>,
    <article key="firmware" className="mission-detail-card"><div className="mission-detail-heading"><MissionIcon name="settings" /><span>05 / DISPOSITIVO</span></div><h3>Configuración</h3><dl className="mission-detail-grid">
      <Definition label="Watchdog">{mission.watchdogSeconds / 60} min</Definition><Definition label="Primario">GPS · firmware</Definition><Definition label="Respaldo">Timer · firmware</Definition><Definition label="Dispositivo">{demo ? 'SIMULADO' : mission.deviceEui}</Definition>
    </dl><p className="mission-detail-note">Los disparadores pertenecen al firmware.</p></article>,
  ]
  return <section className="mission-details panel" aria-label="Detalles secundarios de misión">
    <div className="mission-details-intro"><p className="mission-eyebrow">SISTEMAS {demo ? '· SIMULADOS' : '· ESTACIÓN REAL'}</p><h2>La misión,<br />en detalle.</h2><p>GNSS, alimentación, radio y referencias de vuelo.</p><span>Desliza o usa las flechas para explorar.</span></div>
    <Carousel className="orbitium-carousel" items={cards} baseWidth="100%" autoHeight peek={0} gap={16} radius={4} frame={false} effect="slide" indicator="counter" arrows autoplay={false} loop={false} theme="light" />
  </section>
}
