import { useState } from 'react'
import type { MissionController, MissionState } from '../../application/MissionController.ts'
import { commandUnavailableReason } from '../../domain/mission.ts'
import type { CommandType } from '../../domain/mission.ts'
import { clock, duration, statusLabels } from '../format.ts'
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
  const [startOpen, setStartOpen] = useState(false)
  const [phrase, setPhrase] = useState('')
  const snapshot = state.snapshot!
  const demo = controller.gateway.mode === 'demo'
  const available =
    snapshot.permissions.canCommand &&
    state.connection === 'connected' &&
    (demo || Boolean(snapshot.csrfToken))
  const hasRelease = snapshot.commands.some(
    (c) => c.type === 'RELEASE_NOW' && !['rejected', 'expired'].includes(c.status),
  )
  const disabled = state.commanding || !available
  const reason = (type: CommandType) => commandUnavailableReason(snapshot, type, now)
  const blocked = (type: CommandType) => disabled || Boolean(reason(type))
  const startPending = snapshot.commands.some((c) => c.type === 'START_MISSION' && ['pending', 'sent', 'received'].includes(c.status))
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
          disabled={blocked('START_MISSION')}
          title={reason('START_MISSION') ?? 'Iniciar misión y watchdog en la Heltec'}
          onClick={() => setStartOpen(true)}
        >
          {snapshot.mission.startedAt ? 'Misión iniciada' : startPending ? 'Inicio solicitado' : 'Iniciar misión'}
        </button>
        <button
          className="button"
          disabled={blocked('PING')}
          title={reason('PING') ?? undefined}
          onClick={() => void controller.sendCommand('PING')}
        >
          PING
        </button>
        <button
          className="button"
          disabled={blocked('STATUS')}
          title={reason('STATUS') ?? undefined}
          onClick={() => void controller.sendCommand('STATUS')}
        >
          STATUS?
        </button>
        <button
          className="button"
          disabled={blocked('TELEMETRY')}
          title={reason('TELEMETRY') ?? undefined}
          onClick={() => void controller.sendCommand('TELEMETRY')}
        >
          TELEM?
        </button>
        <button
          className="button danger"
          disabled={blocked('RELEASE_NOW') || snapshot.mission.phase !== 'ascending' || hasRelease}
          title={reason('RELEASE_NOW') ?? undefined}
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
          : snapshot.commandSettings?.reason ?? 'Clase A · intervalo de 6 horas: el comando espera al siguiente uplink. Recibido no significa ejecutado.'}
      </p>
      {!demo && !snapshot.mission.startedAt && <p className="helper-text">El tiempo de misión y el watchdog comienzan únicamente con la ejecución confirmada de START_MISSION por la Heltec.</p>}
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
      {startOpen && (
        <Dialog title="Confirmar inicio de misión" onClose={() => setStartOpen(false)}>
          <div className="dialog-body">
            <p>{demo ? 'Inicio simulado de misión.' : 'Se solicitará a la Heltec iniciar la misión y su watchdog autónomo.'}</p>
            <p>
              Watchdog configurado: {duration(snapshot.mission.watchdogSeconds)}. Solicitarlo o recibir
              un ACK no inicia los contadores; hace falta confirmar la ejecución. Esta acción no
              confirma ascenso ni modifica la cadencia de radio.
            </p>
            <div className="dialog-actions">
              <button className="button subtle" onClick={() => setStartOpen(false)}>Cancelar</button>
              <button className="button" disabled={blocked('START_MISSION')} onClick={async () => {
                if (await controller.sendCommand('START_MISSION', true)) setStartOpen(false)
              }}>{state.commanding ? 'Solicitando…' : 'Confirmar inicio'}</button>
            </div>
          </div>
        </Dialog>
      )}
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
