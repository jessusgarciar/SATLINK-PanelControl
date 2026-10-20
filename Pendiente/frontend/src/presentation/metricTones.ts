export type MetricTone = 'neutral' | 'cyan' | 'blue' | 'green' | 'amber' | 'red'

export function temperatureTone(value: number | null | undefined): MetricTone {
  if (value == null || !Number.isFinite(value)) return 'neutral'
  if (value <= 15) return 'blue'
  if (value < 25) return 'amber'
  return 'red'
}

export function batteryTone(value: number | null | undefined): MetricTone {
  if (value == null || !Number.isFinite(value)) return 'neutral'
  if (value < 3) return 'red'
  if (value < 3.4) return 'amber'
  return 'green'
}

export function rssiTone(value: number | null | undefined): MetricTone {
  if (value == null || !Number.isFinite(value)) return 'neutral'
  if (value <= -110) return 'red'
  if (value < -90) return 'amber'
  return 'green'
}
