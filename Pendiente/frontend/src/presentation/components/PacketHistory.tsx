import { useEffect, useRef, useState } from 'react'
import type { MissionGateway, PacketRecord } from '../../application/ports.ts'
import type { Telemetry } from '../../domain/mission.ts'
import { dateTime } from '../format.ts'
import './PacketHistory.css'

const labels: Record<string, string> = {
  boardTemperatureC: 'BME de placa · °C', boardPressureHpa: 'BME de placa · hPa', boardHumidityPct: 'BME de placa · %',
  tvocPpb: 'ENS160 · TVOC · ppb', eco2Ppm: 'ENS160 · eCO₂ · ppm', aqi: 'ENS160 · AQI',
  ahtTemperatureC: 'AHT · °C', ahtHumidityPct: 'AHT · %', lightLux: 'BH1750 · lx', lightSaturated: 'Luz saturada',
  dhtTemperatureC: 'DHT · °C', dhtHumidityPct: 'DHT · %', inaBusV: 'INA219 · V', inaCurrentMa: 'INA219 · mA',
  temperatureC: 'Temperatura · °C', pressureHpa: 'Presión · hPa', humidityPct: 'Humedad · %',
  batteryV: 'Batería · V', batteryPct: 'Batería · %', latitude: 'Latitud · °', longitude: 'Longitud · °',
  altitudeGpsM: 'Altitud GPS · m', satellites: 'Satélites', gpsFix: 'Fix GPS', gpsActive: 'GPS activo',
  usbPowered: 'Sin batería medida / USB', charging: 'Cargando', uptimeS: 'Tiempo encendida · s',
  lectura: 'Número de lectura', enVuelo: 'En vuelo', corteEnCurso: 'Corte en curso', cortado: 'Secuencia terminada',
  evento: 'Evento', motivo: 'Motivo', seq: 'Secuencia', intento: 'Intento', altitudeM: 'Altitud · m',
  tVueloS: 'Tiempo de vuelo · s', verticalSpeedMs: 'Velocidad vertical · m/s', altitudeSource: 'Fuente de altitud',
  downlinkRssiDbm: 'RSSI del Marco · dBm', downlinkSnrDb: 'SNR del Marco · dB',
  rssiDbm: 'RSSI · dBm', snrDb: 'SNR · dB', packetType: 'Tipo de paquete', fPort: 'Puerto',
}
function display(value: unknown): string {
  if (value == null) return '—'
  if (typeof value === 'boolean') return value ? 'Sí' : 'No'
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}
function simulation(samples: Telemetry[]): PacketRecord[] {
  return [...samples].reverse().map(s => ({ id: s.id, receivedAt: s.receivedAt, ingestedAt: s.receivedAt,
    status: 'accepted', reason: null, decoded: { ...s }, raw: { simulated: true }, rawBase64: '' }))
}

export default function PacketHistory({ gateway, samples }: { gateway: MissionGateway; samples: Telemetry[] }) {
  const [items, setItems] = useState<PacketRecord[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const active = useRef<AbortController | null>(null)
  const mounted = useRef(true)
  async function load(more = false) {
    active.current?.abort()
    const request = new AbortController()
    active.current = request
    setLoading(true); setError('')
    try {
      const page = await gateway.packets!(more ? cursor : null, request.signal)
      if (!mounted.current || request.signal.aborted) return
      setItems(old => more ? [...old, ...page.items.filter(p => !old.some(o => o.id === p.id))] : page.items)
      setCursor(page.nextCursor)
    } catch (cause) {
      if (mounted.current && !request.signal.aborted) setError(cause instanceof Error ? cause.message : 'No se pudieron cargar los paquetes.')
    } finally { if (mounted.current && !request.signal.aborted) setLoading(false) }
  }
  useEffect(() => {
    mounted.current = true
    if (gateway.packets) void load()
    return () => { mounted.current = false; active.current?.abort() }
    // La sección se vuelve a montar al cambiar de misión o de fuente.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gateway])
  const packets = gateway.packets ? items : simulation(samples)
  const selected = packets.find(p => p.id === selectedId) ?? packets[0]
  const rows = selected ? Object.entries(selected.decoded).filter(([k]) => !['presentFields', 'presentDeviceFields'].includes(k)) : []
  return <section className="packet-history" aria-labelledby="packet-history-title">
    <div className="mission-information-section-title"><h3 id="packet-history-title">Historial de paquetes</h3><span>{gateway.mode === 'demo' ? 'SIMULADO' : 'RECIBIDOS'}</span></div>
    <p className="helper-text">Selecciona un paquete para revisar lo que llegó en ese envío. Hora de recepción en la estación; valores no disponibles: —.</p>
    {gateway.packets && <button className="button subtle" disabled={loading} onClick={() => void load()}>Actualizar paquetes</button>}
    <p role="status" className="helper-text">{loading ? 'Cargando paquetes…' : `${packets.length} paquetes cargados`}</p>
    {error && <p role="alert" className="inline-error">{error}</p>}
    {!loading && !packets.length && !error && <p className="helper-text">Aún no hay paquetes guardados para esta misión.</p>}
    {packets.length > 0 && <div className="packet-browser">
      <div className="packet-list" role="group" aria-label="Paquetes recibidos">
        {packets.map(p => <button key={p.id} type="button" className="packet-select" aria-pressed={selected?.id === p.id} onClick={() => setSelectedId(p.id)}>
          <span>{display(p.decoded.packetType ?? (p.status === 'rejected' ? 'Rechazado' : 'Telemetría'))} <small>fPort {display(p.raw.fPort ?? p.decoded.fPort)}</small></span>
          <time dateTime={p.receivedAt ?? p.ingestedAt}>{dateTime(p.receivedAt ?? p.ingestedAt)}</time>
          <small>fCnt {display(p.raw.fCnt ?? p.decoded.frameCounter)} · {p.status === 'accepted' ? 'Aceptado' : 'Rechazado'}</small>
        </button>)}
      </div>
      {selected && <article className="packet-detail" aria-label="Detalle del paquete seleccionado">
        <h4>Contenido del paquete</h4>
        <p className="helper-text">{dateTime(selected.receivedAt ?? selected.ingestedAt)} · ID {selected.id}</p>
        {selected.reason && <p className="inline-error">{selected.reason}</p>}
        <dl className="packet-fields">{rows.map(([key, value]) => <div key={key}><dt>{labels[key] ?? key}</dt><dd>{display(value)}</dd></div>)}</dl>
        <details><summary>Evento original y payload</summary><pre>{JSON.stringify(selected.raw, null, 2)}</pre>{selected.rawBase64 && <details><summary>Evento original en Base64</summary><pre>{selected.rawBase64}</pre></details>}</details>
      </article>}
    </div>}
    {cursor && <button className="button subtle" disabled={loading} onClick={() => void load(true)}>Cargar paquetes anteriores</button>}
  </section>
}
