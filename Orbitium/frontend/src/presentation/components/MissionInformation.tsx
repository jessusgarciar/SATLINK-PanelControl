import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import type { Mission, MissionParameters } from '../../domain/mission.ts'
import { number } from '../format.ts'
import { AGS_TIME_LABEL, agsDateInput, agsDateTime, agsDateToUtc } from '../missionTime.ts'
import type { MapSettings } from './MissionMap.tsx'
import MissionIcon from './MissionIcon.tsx'
import { Definition, Dialog } from './ui.tsx'

const PlanningMap = lazy(() => import('./PlanningMap.tsx'))

const numericFields = [
  { key: 'latitude', label: 'Latitud · °', min: -90, max: 90 },
  { key: 'longitude', label: 'Longitud · °', min: -180, max: 180 },
  { key: 'altitudeM', label: 'Altitud de lanzamiento · m s. n. m.', min: -500, max: 65534 },
  { key: 'targetRelativeAltitudeM', label: 'Altitud objetivo relativa · m', min: 1000, max: 15000 },
] as const

export default function MissionInformation({ mission, demo, online, mapSettings, onSave, onClose }: {
  mission: Mission | undefined
  demo: boolean
  online: boolean
  mapSettings: MapSettings
  onSave: (parameters: MissionParameters) => Promise<void>
  onClose: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [mapMessage, setMapMessage] = useState('')
  const [draft, setDraft] = useState({ plannedLaunchAt: '', launchLabel: '', latitude: '', longitude: '', altitudeM: '', targetRelativeAltitudeM: '' })
  const form = useRef<HTMLFormElement>(null)
  useEffect(() => {
    if (editing) form.current?.querySelector('input')?.focus()
  }, [editing])
  const edit = () => {
    if (!mission) return
    setDraft({ plannedLaunchAt: agsDateInput(mission.plannedLaunchAt), launchLabel: mission.launchLabel,
      latitude: String(mission.launch.latitude), longitude: String(mission.launch.longitude),
      altitudeM: String(mission.launch.altitudeM), targetRelativeAltitudeM: String(mission.targetRelativeAltitudeM) })
    setErrors({}); setError(''); setMessage(''); setMapMessage(''); setEditing(true)
  }
  const change = (key: keyof typeof draft, value: string) => {
    setDraft(old => ({ ...old, [key]: value }))
    setErrors(old => ({ ...old, [key]: '' }))
    setError('')
  }
  return <Dialog title="Información de misión" className="mission-dialog mission-information" onClose={onClose} closeDisabled={saving}>
    <div className="mission-information-body">
    <section className="operation-hero">
      <p className="mission-eyebrow"><MissionIcon name="settings" /> REFERENCIAS DE MISIÓN</p>
      <h3>Todo listo para el despegue.</h3>
      <p>Identidad, planificación y punto de lanzamiento en un solo lugar.</p>
      <span className="tiny-badge badge-amber">{demo ? 'DEMOSTRACIÓN · CAMBIOS DE ESTA SESIÓN' : 'ESTACIÓN LOCAL · CONFIGURACIÓN PERSISTENTE'}</span>
    </section>
    <section className="mission-information-identity" aria-label="Identidad de la misión">
      <div className="mission-information-section-title"><h3>Identidad y enlace</h3><span>SOLO LECTURA</span></div>
      <dl className="mission-information-grid">
        <Definition label="Misión">{mission?.name ?? 'No disponible'}</Definition>
        <Definition label="Aplicación">{mission?.applicationName ?? 'Nombre no configurado'}</Definition>
        <Definition label="Application ID">{mission?.applicationId ?? 'No disponible'}</Definition>
        <Definition label="DevEUI"><span className={'mission-device-eui ' + (demo ? 'is-simulated' : online ? 'is-online' : 'is-offline')}>{mission?.deviceEui ?? 'No disponible'}</span><small className="mission-device-status">{demo ? 'Dispositivo simulado' : online ? 'Conectado · telemetría reciente' : 'Desconectado · sin telemetría reciente'}</small></Definition>
      </dl>
    </section>
    {mission ? <section className="mission-information-parameters" aria-label="Parámetros locales de misión">
      <div className="mission-information-section-title"><h3>Plan de lanzamiento</h3><span>{editing ? 'EDICIÓN' : 'PARÁMETROS LOCALES'}</span></div>
      {editing ? <form ref={form} noValidate onSubmit={async event => {
        event.preventDefault()
        if (saving) return
        const invalid: Record<string, string> = {}
        if (!draft.launchLabel.trim() || draft.launchLabel.trim().length > 256) invalid.launchLabel = 'Escribe una ubicación de 1 a 256 caracteres.'
        if (draft.plannedLaunchAt && !Number.isFinite(Date.parse(draft.plannedLaunchAt + '-06:00'))) invalid.plannedLaunchAt = 'Introduce una fecha y hora válidas.'
        for (const field of numericFields) {
          const value = Number(draft[field.key])
          if (!draft[field.key].trim() || !Number.isFinite(value) || value < field.min || value > field.max)
            invalid[field.key] = `Introduce un valor entre ${field.min} y ${field.max}.`
        }
        setErrors(invalid)
        if (Object.keys(invalid).length) {
          requestAnimationFrame(() => form.current?.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus())
          return
        }
        setSaving(true); setError('')
        try {
          await onSave({ plannedLaunchAt: draft.plannedLaunchAt ? agsDateToUtc(draft.plannedLaunchAt) : null,
            launchLabel: draft.launchLabel.trim(), launch: { latitude: Number(draft.latitude), longitude: Number(draft.longitude), altitudeM: Number(draft.altitudeM) },
            targetRelativeAltitudeM: Number(draft.targetRelativeAltitudeM) })
          setEditing(false)
          setMessage(demo ? 'Parámetros simulados guardados para esta sesión.' : 'Parámetros guardados en mission.local.json y en la misión activa.')
        } catch (cause) { setError(cause instanceof Error ? cause.message : 'No se pudieron guardar los parámetros. Inténtalo de nuevo.') }
        finally { setSaving(false) }
      }}>
        <fieldset disabled={saving} className="mission-information-fields">
          <label className="prediction-field mission-information-wide"><span>Fecha y hora previstas de lanzamiento</span><input aria-label="Fecha y hora previstas de lanzamiento" type="datetime-local" value={draft.plannedLaunchAt} onChange={e => change('plannedLaunchAt', e.target.value)} aria-invalid={Boolean(errors.plannedLaunchAt)} aria-describedby="mission-planned-help mission-plannedLaunchAt-error" />
            <small id="mission-planned-help">{AGS_TIME_LABEL}. Opcional; deja vacío si aún no está definido.</small><small id="mission-plannedLaunchAt-error" className="mission-field-error">{errors.plannedLaunchAt}</small></label>
          <label className="prediction-field mission-information-wide"><span>Ubicación de lanzamiento</span><input aria-label="Ubicación de lanzamiento" required maxLength={256} value={draft.launchLabel} onChange={e => change('launchLabel', e.target.value)} aria-invalid={Boolean(errors.launchLabel)} aria-describedby="mission-launchLabel-error" /><small id="mission-launchLabel-error" className="mission-field-error">{errors.launchLabel}</small></label>
          <section className="mission-information-location mission-information-wide" aria-label="Mapa del punto de lanzamiento">
            <h4><MissionIcon name="map" /> Selecciona el punto en el mapa</h4>
            <p className="helper-text">Toca el mapa para colocar el marcador o arrástralo. También puedes escribir las coordenadas debajo.</p>
            <div inert={saving} aria-disabled={saving}>
              <Suspense fallback={<div className="map-loading">Cargando mapa…</div>}>
                <PlanningMap settings={mapSettings} position={{
                  latitude: draft.latitude.trim() && Number.isFinite(Number(draft.latitude)) && Math.abs(Number(draft.latitude)) <= 90 ? Number(draft.latitude) : mission.launch.latitude,
                  longitude: draft.longitude.trim() && Number.isFinite(Number(draft.longitude)) && Math.abs(Number(draft.longitude)) <= 180 ? Number(draft.longitude) : mission.launch.longitude,
                  altitudeM: mission.launch.altitudeM,
                }} onChange={point => {
                  if (saving) return
                  const latitude = point.latitude.toFixed(6), longitude = point.longitude.toFixed(6)
                  setDraft(old => ({ ...old, latitude, longitude }))
                  setErrors(old => ({ ...old, latitude: '', longitude: '' })); setError('')
                  setMapMessage(`Punto seleccionado: ${latitude}°, ${longitude}°.`)
                }} />
              </Suspense>
            </div>
            <p className="helper-text">El mapa selecciona coordenadas; introduce la altitud de lanzamiento manualmente.</p>
            <p className="mission-map-feedback" role="status">{mapMessage}</p>
          </section>
          {numericFields.map(field => <label key={field.key} className="prediction-field"><span>{field.label}</span><input aria-label={field.label} type="number" required step="any" min={field.min} max={field.max} value={draft[field.key]} onChange={e => change(field.key, e.target.value)} aria-invalid={Boolean(errors[field.key])} aria-describedby={'mission-' + field.key + '-error'} /><small id={'mission-' + field.key + '-error'} className="mission-field-error">{errors[field.key]}</small></label>)}
        </fieldset>
        <p className="helper-text">El objetivo se mide sobre el punto de lanzamiento · máximo 15 000 m.</p>
        {error && <p className="inline-error" role="alert">{error} Tus cambios se conservan en el formulario.</p>}
        <div className="mission-information-actions"><button type="button" className="button subtle" disabled={saving} onClick={() => { setEditing(false); setError(''); setErrors({}) }}>Cancelar</button><button type="submit" className="button" disabled={saving}>{saving ? 'Guardando…' : 'Guardar parámetros'}</button></div>
      </form> : <>
        <dl className="mission-information-grid">
          <Definition label="Lanzamiento previsto · AGS">{agsDateTime(mission.plannedLaunchAt)}</Definition>
          <Definition label="Ubicación">{mission.launchLabel}</Definition>
          <Definition label="Latitud / Longitud">{number(mission.launch.latitude, 5)}° / {number(mission.launch.longitude, 5)}°</Definition>
          <Definition label="Altitud de lanzamiento">{number(mission.launch.altitudeM, 0)} m s. n. m.</Definition>
          <Definition label="Altitud objetivo relativa">+{number(mission.targetRelativeAltitudeM, 0)} m</Definition>
          <Definition label="Región LoRaWAN">{mission.region}</Definition>
        </dl>
        <div className="mission-information-actions"><button className="button" onClick={edit}>Editar parámetros</button></div>
      </>}
    </section> : <p role="status" className="helper-text">Esperando la configuración de la misión. Revisa la conexión con la estación.</p>}
    <p role="status" className="mission-information-feedback">{message}</p>
    </div>
  </Dialog>
}
