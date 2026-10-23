/** Aguascalientes uses UTC−06:00 year-round, independently of the operator's device. */
export const AGS_TIME_LABEL = 'Hora de Aguascalientes · UTC−06:00'
const offsetMs = 6 * 60 * 60 * 1000

export function agsDateInput(value: string | null | undefined): string {
  return value ? new Date(Date.parse(value) - offsetMs).toISOString().slice(0, 16) : ''
}

export function agsDateToUtc(value: string): string {
  return new Date(value + '-06:00').toISOString()
}

export function agsDateTime(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString('es-MX', { timeZone: 'Etc/GMT+6', hour12: false }) : '—'
}
