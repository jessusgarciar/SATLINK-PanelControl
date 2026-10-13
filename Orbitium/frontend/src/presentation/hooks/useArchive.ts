import { useEffect, useMemo, useSyncExternalStore } from 'react'
import type { HistoryGateway } from '../../application/ports.ts'
import { WindowController } from '../../application/WindowController.ts'
import { timeRange } from '../../domain/history.ts'
import type { WindowKey } from '../../domain/history.ts'

export function useArchive(gateway: HistoryGateway, key: WindowKey, enabled: boolean) {
  const controller = useMemo(() => new WindowController(gateway), [gateway])
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot)
  useEffect(() => {
    if (!enabled) return
    const refresh = () => void controller.load(timeRange(key, Date.now()))
    refresh()
    const timer = setInterval(refresh, 5000)
    return () => { clearInterval(timer); controller.dispose() }
  }, [controller, key, enabled])
  return state
}
