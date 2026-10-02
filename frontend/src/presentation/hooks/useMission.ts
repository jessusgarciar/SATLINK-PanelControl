import { useEffect, useState, useSyncExternalStore } from 'react'
import type { MissionController } from '../../application/MissionController.ts'

export function useMission(controller: MissionController) {
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot)
  useEffect(() => controller.start(), [controller])
  return state
}
export function useNow() {
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  return now
}
