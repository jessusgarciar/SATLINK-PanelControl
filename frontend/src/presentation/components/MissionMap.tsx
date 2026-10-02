import { useEffect, useMemo, useState } from 'react'
import {
  CircleMarker,
  MapContainer,
  Polyline,
  Popup,
  ScaleControl,
  TileLayer,
  useMap,
  useMapEvents,
} from 'react-leaflet'
import type { LatLngTuple } from 'leaflet'
import type { DashboardSnapshot, Telemetry } from '../../domain/mission.ts'
import { clock, number } from '../format.ts'

export interface MapSettings {
  tileUrl: string
  attribution: string
}
function ViewController({
  fix,
  overview,
  bounds,
  fitKey,
  following,
  setFollowing,
}: {
  fix: Telemetry | undefined
  overview: boolean
  bounds: LatLngTuple[]
  fitKey: string
  following: boolean
  setFollowing: (following: boolean) => void
}) {
  const map = useMap()
  useMapEvents({ dragstart: () => setFollowing(false) })
  useEffect(() => {
    const updateSize = () => {
      const container = map.getContainer()
      if (!container.clientWidth || !container.clientHeight) return
      map.invalidateSize()
      if (overview && bounds.length > 1)
        map.fitBounds(bounds, { padding: [30, 30], maxZoom: 15, animate: false })
    }
    // A native dialog starts hidden. Fit only after it has a measurable size.
    const observer = new ResizeObserver(updateSize)
    observer.observe(map.getContainer())
    updateSize()
    return () => observer.disconnect()
    // Capture bounds on opening/recalculating/resizing, not on every packet.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, overview, fitKey])
  useEffect(() => {
    if (following && fix?.latitude != null && fix.longitude != null)
      map.panTo([fix.latitude, fix.longitude], { animate: false })
  }, [map, fix?.latitude, fix?.longitude, following])
  return null
}
export default function MissionMap({
  snapshot,
  settings,
  overview = false,
}: {
  snapshot: DashboardSnapshot
  settings: MapSettings
  overview?: boolean
}) {
  const [following, setFollowing] = useState(!overview)
  const [tiles, setTiles] = useState(Boolean(settings.tileUrl))
  const [tileError, setTileError] = useState(false)
  const { mission, telemetry, prediction, events } = snapshot
  const valid = useMemo(
    () => telemetry.filter((t) => t.latitude !== null && t.longitude !== null),
    [telemetry],
  )
  const fix = valid.at(-1)
  const measured: LatLngTuple[] = valid.map((t) => [t.latitude!, t.longitude!])
  const predicted: LatLngTuple[] = overview
    ? (prediction?.trajectory.map((p) => [p.latitude, p.longitude]) ?? [])
    : []
  const launch: LatLngTuple = [mission.launch.latitude, mission.launch.longitude]
  const tileEvents = useMemo(() => ({ tileerror: () => setTileError(true) }), [])
  return (
    <div className={'mission-map' + (overview ? ' overview-map' : '')}>
      <div className="map-toolbar">
        <button
          className={'map-control' + (following ? ' selected' : '')}
          aria-pressed={following}
          onClick={() => setFollowing(!following)}
        >
          ◎ {following ? 'Siguiendo' : 'Seguir cápsula'}
        </button>
        <label className="map-control">
          <input
            type="checkbox"
            checked={tiles}
            onChange={(e) => {
              setTiles(e.target.checked)
              setTileError(false)
            }}
            disabled={!settings.tileUrl}
          />
          Mapa base
        </label>
      </div>
      <MapContainer
        className="leaflet-host"
        center={
          fix?.latitude != null && fix.longitude != null ? [fix.latitude, fix.longitude] : launch
        }
        zoom={13}
        scrollWheelZoom={false}
        attributionControl
        zoomControl
      >
        <ViewController
          fix={fix}
          overview={overview}
          bounds={[launch, ...measured, ...predicted]}
          fitKey={prediction?.id ?? 'none'}
          following={following}
          setFollowing={setFollowing}
        />
        {tiles && (
          <TileLayer
            className="base-tiles"
            url={settings.tileUrl}
            attribution={settings.attribution}
            maxZoom={19}
            eventHandlers={tileEvents}
          />
        )}
        <ScaleControl imperial={false} position="bottomleft" />
        <Polyline
          positions={measured}
          pathOptions={{ color: '#00e5ff', weight: 2.5, opacity: 0.9 }}
        />
        {predicted.length > 0 && (
          <Polyline
            positions={predicted}
            pathOptions={{ color: '#fbbf24', weight: 2, dashArray: '7 7' }}
          />
        )}
        <CircleMarker
          center={launch}
          radius={5}
          pathOptions={{ color: '#94a3b8', fillColor: '#64748b', fillOpacity: 1, weight: 1 }}
        >
          <Popup>
            Lanzamiento
            <br />
            {number(launch[0], 5)}°, {number(launch[1], 5)}°
          </Popup>
        </CircleMarker>
        {fix && (
          <CircleMarker
            center={[fix.latitude!, fix.longitude!]}
            radius={7}
            pathOptions={{
              className: 'capsule-marker',
              color: '#b9f8ff',
              fillColor: '#00e5ff',
              fillOpacity: 1,
              weight: 1,
            }}
          >
            <Popup>
              Última posición válida
              <br />
              {number(fix.latitude, 5)}°, {number(fix.longitude, 5)}°<br />
              Recepción: {clock(fix.receivedAt)}
            </Popup>
          </CircleMarker>
        )}
        {overview && prediction && (
          <>
            <CircleMarker
              center={[prediction.release.latitude, prediction.release.longitude]}
              radius={5}
              pathOptions={{ color: '#f87171', fillOpacity: 0.3 }}
            >
              <Popup>
                Liberación estimada
                <br />
                {clock(prediction.release.time)}
              </Popup>
            </CircleMarker>
            <CircleMarker
              center={[prediction.landing.latitude, prediction.landing.longitude]}
              radius={8}
              pathOptions={{ color: '#fbbf24', fillColor: '#fbbf24', fillOpacity: 0.3, weight: 2 }}
            >
              <Popup>
                <strong>Aterrizaje estimado</strong>
                <br />
                {number(prediction.landing.latitude, 5)}°, {number(prediction.landing.longitude, 5)}
                °<br />
                ETA: {clock(prediction.landing.time)}
                <br />
                {prediction.source === 'demo' ? 'Escenario simulado' : 'Predicción Tawhiri'}
              </Popup>
            </CircleMarker>
          </>
        )}
        {events
          .filter((event) => event.type === 'release' && event.position)
          .map((event) => (
            <CircleMarker
              key={event.id}
              center={[event.position!.latitude, event.position!.longitude]}
              radius={6}
              pathOptions={{ color: '#f87171', fillColor: '#f87171', fillOpacity: 1 }}
            >
              <Popup>{event.message}</Popup>
            </CircleMarker>
          ))}
      </MapContainer>
      {(tileError || !tiles) && (
        <p className="map-notice">
          {tileError
            ? 'Cartografía no disponible. Se conservan coordenadas y trayectorias.'
            : 'Mapa base oculto · coordenadas y trayectorias visibles.'}
        </p>
      )}
      {!fix && <p className="map-notice tone-amber">Esperando una posición GPS válida.</p>}
    </div>
  )
}
