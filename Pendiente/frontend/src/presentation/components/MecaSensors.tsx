import type { Telemetry } from '../../domain/mission.ts'
import { number, dateTime } from '../format.ts'
import { DataCard } from './ui.tsx'
import { temperatureTone } from '../metricTones.ts'
import type { MetricTone } from '../metricTones.ts'

const fields = [
  ['batteryPct', 'Carga de batería', '%'],
  ['satellites', 'Satélites GPS', ''],
  ['uptimeS', 'Tiempo encendido', 's'],
  ['lectura', 'Contador de lectura', ''],
  ['boardTemperatureC', 'BME de placa · temperatura', '°C'],
  ['boardPressureHpa', 'BME de placa · presión', 'hPa'],
  ['boardHumidityPct', 'BME de placa · humedad', '%'],
] as const

export default function MecaSensors({ samples, now, staleAfterSeconds }: {
  samples: Telemetry[]; now: number; staleAfterSeconds: number
}) {
  const ordered = [...samples].sort((a, b) => Date.parse(b.receivedAt) - Date.parse(a.receivedAt))
  return <>
      {fields.map(([key, label, unit]) => {
        const sample = ordered.find(s => s.packet && Object.hasOwn(s.packet, key))
        const value = sample?.packet?.[key]
        const numeric = typeof value === 'number' && Number.isFinite(value) ? value : null
        const tone: MetricTone = key.toLowerCase().includes('temperature') ? temperatureTone(numeric)
          : key === 'batteryPct' ? (numeric === null ? 'neutral' : numeric < 15 ? 'red' : numeric < 30 ? 'amber' : 'green')
          : key.toLowerCase().includes('humidity') ? 'blue'
          : key.toLowerCase().includes('pressure') ? 'cyan'
          : 'cyan'
        return <DataCard key={key} label={label} unit={unit} tone={tone}
          value={numeric !== null ? number(numeric, ['batteryPct', 'satellites', 'uptimeS', 'lectura'].includes(key) ? 0 : 1) : '—'}
          detail={sample ? dateTime(sample.receivedAt) : 'Sin paquete recibido'}
          stale={!sample || now - Date.parse(sample.receivedAt) > staleAfterSeconds * 1000} />
      })}
  </>
}
