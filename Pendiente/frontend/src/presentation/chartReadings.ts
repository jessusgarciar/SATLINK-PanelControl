import type { Telemetry } from '../domain/mission.ts'

function median(values: number[]): number | null {
  if (values.length === 0) return null
  const sorted = [...values].sort((a, b) => a - b)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0
    ? (sorted[middle - 1] + sorted[middle]) / 2
    : sorted[middle]
}

export function chartInterval(samples: Telemetry[]): number {
  const times = samples.map((sample) => Date.parse(sample.receivedAt)).filter(Number.isFinite)
  const span = times.length > 1 ? Math.max(...times) - Math.min(...times) : 0
  if (span <= 20 * 60_000) return 20_000
  if (span <= 2 * 60 * 60_000) return 3 * 60_000
  return 4 * 60_000
}

/** Chart-only medians. Never persist these summaries or substitute them for raw CSV rows. */
export function aggregateSamples(samples: Telemetry[], interval: number, keys: (keyof Telemetry)[]): Telemetry[] {
  const buckets = new Map<number, Telemetry[]>()
  for (const sample of samples) {
    const time = Date.parse(sample.receivedAt)
    if (!Number.isFinite(time)) continue
    const start = Math.floor(time / interval) * interval
    const bucket = buckets.get(start) ?? []
    bucket.push(sample)
    buckets.set(start, bucket)
  }
  return [...buckets.entries()].sort(([a], [b]) => a - b).map(([start, bucket]) => {
    const aggregated: Telemetry = { ...bucket[0], receivedAt: new Date(start).toISOString() }
    for (const key of keys) {
      const values = bucket.flatMap((sample) => {
        const value = sample[key]
        return typeof value === 'number' && Number.isFinite(value) ? [value] : []
      })
      Object.assign(aggregated, { [key]: median(values) })
    }
    return aggregated
  })
}
