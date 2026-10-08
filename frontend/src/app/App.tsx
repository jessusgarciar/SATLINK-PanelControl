import { useMemo, useState } from 'react'
import { MissionController } from '../application/MissionController.ts'
import { DemoMissionGateway } from '../infrastructure/demo/DemoMissionGateway.ts'
import { HttpMissionGateway } from '../infrastructure/http/HttpMissionGateway.ts'
import Dashboard from '../presentation/pages/Dashboard.tsx'
import '../presentation/styles/App.css'

const mapSettings = {
  tileUrl: import.meta.env.VITE_TILE_URL ?? 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  attribution:
    import.meta.env.VITE_TILE_ATTRIBUTION ??
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}
export default function App() {
  const [mode, setMode] = useState<'demo' | 'live'>(
    import.meta.env.VITE_DATA_SOURCE === 'live' ? 'live' : 'demo',
  )
  const controller = useMemo(
    () =>
      new MissionController(
        mode === 'demo'
          ? new DemoMissionGateway(import.meta.env.VITE_DEMO_PREDICTION === 'tawhiri')
          : new HttpMissionGateway(
              import.meta.env.VITE_API_BASE_URL ?? '/api/v1',
              import.meta.env.VITE_MISSION_ID ?? 'satlink-001',
            ),
      ),
    [mode],
  )
  return (
    <Dashboard
      key={mode}
      controller={controller}
      mapSettings={mapSettings}
      onModeChange={setMode}
    />
  )
}
