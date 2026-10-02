import { Component, useEffect, useRef } from 'react'
import type { CSSProperties, ErrorInfo, ReactNode } from 'react'
import type { FlightPhase } from '../../domain/mission.ts'
import { phaseLabels } from '../format.ts'

export function SectionTitle({
  children,
  amber = false,
}: {
  children: ReactNode
  amber?: boolean
}) {
  return <h2 className={'section-title' + (amber ? ' amber-title' : '')}>{children}</h2>
}
export function PhaseChip({ phase }: { phase: FlightPhase }) {
  return (
    <span className={'phase-chip phase-' + phase}>
      <span className="status-dot" />
      {phaseLabels[phase]}
    </span>
  )
}
export function DataCard({
  label,
  value,
  unit,
  detail,
  tone = 'neutral',
  stale = false,
}: {
  label: string
  value: string
  unit?: string
  detail?: string
  tone?: 'neutral' | 'cyan' | 'green' | 'amber' | 'red'
  stale?: boolean
}) {
  return (
    <article className={'panel data-card' + (stale ? ' stale-card' : '')}>
      <h2>{label}</h2>
      <div className={'data-value tone-' + tone}>
        {value}
        <span className="data-unit">{value !== '—' && unit}</span>
      </div>
      {detail && <p>{detail}</p>}
    </article>
  )
}
export function Definition({
  label,
  children,
  tone = '',
}: {
  label: string
  children: ReactNode
  tone?: string
}) {
  return (
    <div className="definition">
      <dt>{label}</dt>
      <dd className={tone ? 'tone-' + tone : undefined}>{children}</dd>
    </div>
  )
}
export function Dialog({
  title,
  children,
  onClose,
  className = '',
}: {
  title: string
  children: ReactNode
  onClose: () => void
  className?: string
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const dialog = ref.current
    dialog?.showModal()
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      dialog?.close()
      document.body.style.overflow = overflow
      previous?.focus()
    }
  }, [])
  return (
    <dialog
      ref={ref}
      className={'dialog ' + className}
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault()
        onClose()
      }}
    >
      <div className="dialog-heading">
        <h2>{title}</h2>
        <button className="button subtle" onClick={onClose} aria-label="Cerrar diálogo">
          ✕ Cerrar
        </button>
      </div>
      {children}
    </dialog>
  )
}
export function RangeInput({
  label,
  value,
  min,
  max,
  step = 1,
  unit,
  onChange,
  disabled = false,
}: {
  label: string
  value: number
  min: number
  max: number
  step?: number
  unit: string
  onChange: (v: number) => void
  disabled?: boolean
}) {
  return (
    <label className="range-field">
      <span>
        {label}
        <output>
          {value} {unit}
        </output>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        disabled={disabled}
        style={{ '--progress': ((value - min) / (max - min)) * 100 + '%' } as CSSProperties}
      />
    </label>
  )
}
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('SATLINK render error', error, info.componentStack)
  }
  render() {
    return this.state.failed ? (
      <main className="fatal-error">
        <h1>No se pudo mostrar el panel</h1>
        <p>Recarga la interfaz para restablecer la visualización.</p>
        <button className="button" onClick={() => window.location.reload()}>
          Recargar
        </button>
      </main>
    ) : (
      this.props.children
    )
  }
}
