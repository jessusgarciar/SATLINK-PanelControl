import { useState } from 'react'
import type { MissionController, MissionState } from '../../application/MissionController.ts'
import { dataAgeSeconds, latestSample } from '../../domain/mission.ts'
import { clock, statusLabels } from '../format.ts'
import { Dialog, SectionTitle } from './ui.tsx'

export default function CommandPanel({
  state,
  controller,
  now,
}: {
  state: MissionState
  controller: MissionController
  now: number
}) {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [phrase, setPhrase] = useState('')
  const snapshot = state.snapshot!
  const age = dataAgeSeconds(latestSample(snapshot.telemetry), now)
  const demo = controller.gateway.mode === 'demo'
  const available =
    snapshot.permissions.canCommand &&
    state.connection === 'connected' &&
    age !== null &&
    age <= snapshot.mission.staleAfterSeconds &&
    (demo || Boolean(snapshot.csrfToken))
  const hasRelease = snapshot.commands.some(
    (c) => c.type === 'RELEASE_NOW' && !['rejected', 'expired'].includes(c.status),
  )
  const disabled = state.commanding || !available
  return (
    <section className="panel command-panel">
      <div className="section-heading">
        <SectionTitle>Enlace de comando · Respuesta del dispositivo</SectionTitle>
        <span className={'tiny-badge' + (!available ? ' badge-amber' : '')}>
          {demo ? 'SIMULADO' : available ? 'OPERADOR' : 'SOLO LECTURA'}
        </span>
      </div>
      <div className="command-buttons">
        <button
          className="button"
          disabled={disabled || snapshot.mission.beaconOn === null}
          onClick={() =>
            void controller.sendCommand(snapshot.mission.beaconOn ? 'BEACON_OFF' : 'BEACON_ON')
          }
        >
          {snapshot.mission.beaconOn ? '● Baliza OFF' : '○ Baliza ON'}
        </button>
        <button
          className="button"
          disabled={disabled}
          onClick={() => void controller.sendCommand('PING')}
        >
          PING
        </button>
        <button
          className="button"
          disabled={disabled}
          onClick={() => void controller.sendCommand('STATUS')}
        >
          STATUS?
        </button>
        <button
          className="button"
          disabled={disabled}
          onClick={() => void controller.sendCommand('TELEMETRY')}
        >
          TELEM?
        </button>
        <button
          className="button danger"
          disabled={disabled || snapshot.mission.phase !== 'ascending' || hasRelease}
          onClick={() => {
            setPhrase('')
            setConfirmOpen(true)
          }}
        >
          RELEASE ⚡
        </button>
      </div>
      <p className="helper-text">
        {demo
          ? 'Demostración: estos controles no envían comandos a la cápsula.'
          : 'Clase A: espera al siguiente uplink. Recibido no significa ejecutado.'}
      </p>
      {state.actionError && (
        <div className="inline-error" role="alert">
          {state.actionError}
          <button className="text-button" onClick={controller.clearActionError}>
            Entendido
          </button>
        </div>
      )}
      <div
        className="command-log"
        role="log"
        aria-label="Bitácora de comandos"
        aria-live="polite"
        aria-relevant="additions text"
      >
        {!snapshot.commands.length && (
          <p className="log-empty">Sin actividad. Los comandos y sus evidencias aparecerán aquí.</p>
        )}
        {snapshot.commands.map((command) => (
          <div className={'command-entry command-' + command.status} key={command.id}>
            <div>
              <time>[{clock(command.updatedAt)}]</time>
              <strong>{command.type}</strong>
              <span>{statusLabels[command.status]}</span>
            </div>
            <p>{command.evidence}</p>
            <small>
              ID: {command.id.slice(0, 8)}
              {command.simulated ? ' · SIMULADO' : ''}
            </small>
          </div>
        ))}
      </div>
      {confirmOpen && (
        <Dialog title="Confirmar solicitud de liberación" onClose={() => setConfirmOpen(false)}>
          <div className="dialog-body">
            <p className="tone-red">
              {demo
                ? 'Vas a simular la liberación de la cápsula.'
                : 'Esta solicitud puede activar la liberación física de la cápsula.'}
            </p>
            <p>
              Se enviará una sola solicitud. La confirmación del firmware y el evento de liberación
              se mostrarán por separado.
            </p>
            <label className="text-field">
              Escribe LIBERAR para confirmar
              <input
                autoComplete="off"
                autoFocus
                value={phrase}
                onChange={(e) => setPhrase(e.target.value)}
                placeholder="LIBERAR"
              />
            </label>
            <div className="dialog-actions">
              <button className="button subtle" onClick={() => setConfirmOpen(false)}>
                Cancelar
              </button>
              <button
                className="button danger"
                disabled={phrase !== 'LIBERAR' || disabled}
                onClick={async () => {
                  const ok = await controller.sendCommand('RELEASE_NOW', true)
                  if (ok) setConfirmOpen(false)
                }}
              >
                {state.commanding
                  ? 'Solicitando…'
                  : demo
                    ? 'Simular liberación'
                    : 'Solicitar liberación'}
              </button>
            </div>
          </div>
        </Dialog>
      )}
    </section>
  )
}
