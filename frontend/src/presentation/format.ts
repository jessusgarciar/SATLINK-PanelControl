import type { CommandStatus, FlightPhase } from '../domain/mission.ts'

export const phaseLabels: Record<FlightPhase, string> = {
  preflight: 'PREVUELO',
  ascending: 'ASCENDIENDO',
  descending: 'DESCENDIENDO',
  landed: 'ATERRIZADA',
  unknown: 'SIN CONFIRMAR',
}
export const statusLabels: Record<CommandStatus, string> = {
  pending: 'PENDIENTE',
  sent: 'ENVIADO',
  received: 'RECIBIDO',
  executed: 'EJECUTADO',
  rejected: 'RECHAZADO',
  expired: 'VENCIDO',
}
export const number = (value: number | null | undefined, decimals = 1): string =>
  value === null || value === undefined || !Number.isFinite(value) ? '—' : value.toFixed(decimals)
export const km = (value: number | null | undefined, decimals = 3): string =>
  number(value == null ? null : value / 1000, decimals)
export const clock = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleTimeString('es-MX', { hour12: false }) : '—'
export const dateTime = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleString('es-MX', { hour12: false }) : '—'
export const duration = (seconds: number | null): string => {
  if (seconds === null || !Number.isFinite(seconds)) return '—'
  const s = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(s / 3600)
  return (
    (hours ? String(hours).padStart(2, '0') + ':' : '') +
    String(Math.floor(s / 60) % 60).padStart(2, '0') +
    ':' +
    String(s % 60).padStart(2, '0')
  )
}
export const ageLabel = (seconds: number | null): string =>
  seconds === null
    ? 'Sin datos'
    : seconds < 60
      ? 'Hace ' + seconds + ' s'
      : 'Hace ' + Math.floor(seconds / 60) + ' min'
