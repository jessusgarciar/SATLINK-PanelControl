import { useEffect } from 'react'
import { divIcon } from 'leaflet'
import type { Marker as LeafletMarker } from 'leaflet'
import { MapContainer, Marker, TileLayer, useMapEvents } from 'react-leaflet'
import type { Position } from '../../domain/mission.ts'
import type { MapSettings } from './MissionMap.tsx'

const icon = divIcon({ className: 'planning-marker', html: '<span></span>', iconSize: [24, 24], iconAnchor: [12, 12] })
function Selection({ position, onChange }: { position: Position; onChange: (position: Position) => void }) {
  const map = useMapEvents({ click(event) {
    onChange({ ...position, latitude: event.latlng.lat, longitude: ((event.latlng.lng + 180) % 360 + 360) % 360 - 180 })
  } })
  useEffect(() => { map.invalidateSize(); map.panTo([position.latitude, position.longitude]) }, [map, position.latitude, position.longitude])
  return <Marker icon={icon} draggable position={[position.latitude, position.longitude]} eventHandlers={{ dragend(event) {
    const point = (event.target as LeafletMarker).getLatLng()
    onChange({ ...position, latitude: point.lat, longitude: ((point.lng + 180) % 360 + 360) % 360 - 180 })
  } }} />
}
export default function PlanningMap({ position, onChange, settings }: { position: Position; onChange: (position: Position) => void; settings: MapSettings }) {
  return <MapContainer className="planning-map" center={[position.latitude, position.longitude]} zoom={12}>
    <TileLayer url={settings.tileUrl} attribution={settings.attribution} />
    <Selection position={position} onChange={onChange} />
  </MapContainer>
}
