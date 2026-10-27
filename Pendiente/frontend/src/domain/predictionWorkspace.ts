import type { DashboardSnapshot, Mission, Prediction, PredictionParameters } from './mission.ts'

export type PredictionMode = 'planned' | 'ascending'
export const predictionMode = (p: Prediction): PredictionMode => p.context?.mode ?? p.parameters.mode ?? 'planned'

/** Two successful calculations per mode; a failed attempt never replaces a route. */
export function mergePredictionHistory(...groups: (Prediction | null | undefined)[][]): Prediction[] {
  const unique = new Map<string, Prediction>()
  for (const p of groups.flat()) if (p) unique.set(p.id, p)
  const counts = { planned: 0, ascending: 0 }
  return [...unique.values()].sort((a, b) => Date.parse(b.generatedAt) - Date.parse(a.generatedAt))
    .filter(p => ++counts[predictionMode(p)] <= 2)
}

export function modePredictions(snapshot: DashboardSnapshot, mode: PredictionMode): Prediction[] {
  return mergePredictionHistory(snapshot.predictionHistory ?? [], [snapshot.prediction])
    .filter(p => predictionMode(p) === mode)
}

/** Mission settings seed drafts; saved results are immutable evidence, not form defaults. */
export function missionPredictionDraft(mission: Mission, mode: PredictionMode, now: number): PredictionParameters {
  const planned = mission.plannedLaunchAt && Date.parse(mission.plannedLaunchAt) > now
    ? mission.plannedLaunchAt : new Date(now + 3600000).toISOString()
  return {
    mode, ...(mode === 'planned' ? { launch: { ...mission.launch }, launchDatetime: planned } : {}),
    targetRelativeAltitudeM: mission.targetRelativeAltitudeM,
    ascentRateMs: mission.nominalAscentMs, descentRateMs: mission.nominalDescentMs,
    ascentWindDirection: 45, ascentWindMs: 8, descentWindDirection: 120, descentWindMs: 5,
  }
}
