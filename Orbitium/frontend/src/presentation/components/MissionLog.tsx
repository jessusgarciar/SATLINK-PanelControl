import { useMemo } from 'react'
import { clock } from '../format.ts'
import AnimatedList from './react-bits/AnimatedList.tsx'
import { SectionTitle } from './ui.tsx'

export default function MissionLog({ entries }: { entries: readonly { id: number; at: string; message: string }[] }) {
  const items = useMemo(() => entries.map(entry => ({ id: entry.id, title: entry.message, meta: <time dateTime={entry.at}>{clock(entry.at)}</time> })), [entries])
  return <section id="mission-log" tabIndex={-1} className="panel mission-log" aria-label="Bitácora técnica de sesión">
    <SectionTitle>Bitácora técnica · Sesión</SectionTitle>
    <p className="archive-caption">Conexiones y errores del panel. Separada de los eventos físicos de misión.</p>
    {items.length ? <AnimatedList className="orbitium-log-list" items={items} readOnly ariaLabel="Entradas de bitácora técnica" selectOnHover={false} enableArrowNavigation={false} frame={false} showGradients={false} displayScrollbar animation="fade" animateOnce stagger={0.02} radius={4} gap={0} width="100%" maxHeight={288} theme="dark" /> : <p className="mission-log-empty">Sin cambios de conexión registrados.</p>}
  </section>
}
