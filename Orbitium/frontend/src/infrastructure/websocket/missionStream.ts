import type { ConnectionStatus, MissionMessage } from '../../domain/mission.ts'
import { parseMessage } from '../http/validation.ts'

/** Native WebSocket, same-origin session cookie, bounded retries and complete cleanup. */
export function subscribeMission(
  url: string,
  onMessage: (message: MissionMessage) => void,
  onStatus: (status: ConnectionStatus) => void,
  onError: (message: string) => void,
): () => void {
  let stopped = false
  let socket: WebSocket | null = null
  let retry: ReturnType<typeof setTimeout> | undefined
  let watchdog: ReturnType<typeof setTimeout> | undefined
  let attempt = 0
  const armWatchdog = () => {
    clearTimeout(watchdog)
    watchdog = setTimeout(() => {
      socket?.close(4000, 'Heartbeat timeout')
    }, 45000)
  }
  const connect = () => {
    if (stopped) return
    onStatus(attempt === 0 ? 'connecting' : 'reconnecting')
    try {
      socket = new WebSocket(url)
    } catch {
      onStatus('offline')
      onError('La URL WebSocket no es válida.')
      return
    }
    socket.onopen = () => {
      if (stopped) return
      onStatus('connected')
      armWatchdog()
    }
    socket.onmessage = (event: MessageEvent<unknown>) => {
      if (stopped) return
      armWatchdog()
      try {
        if (typeof event.data !== 'string' || event.data.length > 2_000_000)
          throw new Error('Mensaje WebSocket inválido o demasiado grande.')
        const message = parseMessage(JSON.parse(event.data))
        attempt = 0
        if (message) onMessage(message)
      } catch (error) {
        onError(error instanceof Error ? error.message : 'Mensaje descartado por formato inválido.')
      }
    }
    socket.onerror = () => {
      if (!stopped) onStatus('offline')
    }
    socket.onclose = (event) => {
      clearTimeout(watchdog)
      if (stopped) return
      if ([1008, 4401, 4403].includes(event.code)) {
        onStatus('offline')
        onError(
          'Sesión expirada o sin acceso a la misión. Inicia sesión en la estación y reintenta.',
        )
        return
      }
      onStatus('reconnecting')
      const delay =
        Math.min(30000, 1000 * 2 ** Math.min(attempt++, 5)) + Math.floor(Math.random() * 300)
      retry = setTimeout(connect, delay)
    }
  }
  connect()
  return () => {
    stopped = true
    clearTimeout(retry)
    clearTimeout(watchdog)
    if (socket) {
      socket.onopen = null
      socket.onmessage = null
      socket.onerror = null
      socket.onclose = null
      socket.close()
    }
  }
}
