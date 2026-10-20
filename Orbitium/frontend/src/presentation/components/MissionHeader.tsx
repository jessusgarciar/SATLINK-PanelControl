import { lazy, memo, Suspense, useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import type { Mission } from '../../domain/mission.ts'
import { duration } from '../format.ts'
import { useMediaQuery } from '../hooks/useMediaQuery.ts'
import logo from '../../../../logo.png'
import CardNav from './react-bits/CardNav.tsx'
import type { CardNavItem } from './react-bits/CardNav.tsx'
import { PhaseChip } from './ui.tsx'

const Aurora = lazy(() => import('./react-bits/Aurora.tsx'))
const auroraColors = ['#07304f', '#00c5df', '#124684']
const navStyle = { '--cn-bar': '82px', '--cn-logo': '52px', '--cn-radius': '4px', '--cn-panel': '#0a1422', '--cn-edge': '#00e5ff24', '--cn-ring': '#00e5ff', '--cn-muted': '#a8b7c9' } as CSSProperties
const menuItems: CardNavItem[] = [
  { label: 'MISIÓN', description: 'Lo esencial, a un toque.', bgColor: '#0d2031', textColor: '#e2e8f0', links: [{ label: 'Resumen de vuelo', href: '#mission-summary' }, { label: 'Mapa y recuperación', href: '#mission-map' }] },
  { label: 'TELEMETRÍA', description: 'Lecturas y evolución.', bgColor: '#101e30', textColor: '#e2e8f0', links: [{ label: 'Sensores', href: '#mission-sensors' }, { label: 'Gráficas del intervalo', href: '#mission-charts' }] },
  { label: 'ESTACIÓN', description: 'Archivo y diagnóstico.', bgColor: '#102331', textColor: '#e2e8f0', links: [{ label: 'Archivo y CSV', href: '#mission-archive' }, { label: 'Bitácora técnica', href: '#mission-log' }] },
]

const HeaderAurora = memo(function HeaderAurora() {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(true)
  const reduce = useMediaQuery('(prefers-reduced-motion: reduce)')
  useEffect(() => {
    const element = ref.current
    if (!element) return
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  return <div ref={ref} className="mission-aurora" aria-hidden="true">
    {!reduce && <Suspense fallback={null}><Aurora colorStops={auroraColors} speed={0.22} amplitude={0.7} height={0.65} blend={0.65} glow={0.3} brightness={0.8} layers={1} mouseInteraction={false} intro={false} opacity={0.8} dpr={1} paused={!visible} /></Suspense>}
  </div>
})

export default function MissionHeader({ mission, elapsed, mode, onModeChange }: {
  mission: Mission | undefined; elapsed: number | null; mode: 'demo' | 'live'; onModeChange: (mode: 'demo' | 'live') => void
}) {
  return <header className="mission-header">
    <HeaderAurora />
    <div className="mission-header-inner">
      <CardNav className="orbitium-card-nav" style={navStyle} theme="dark" surface="solid" accentColor="#00e5ff" intro={false} openOn="click" cardEffect="fade" stagger={0.04} bounce={0.06} speed={1.3} maxWidth={1280} cardHeight={148} ariaLabel="Navegación de misión" items={menuItems}
        menuHeader={<section className="mission-status-rail" aria-label="Estado y fuente de misión">
          <label className="mission-source"><span>Fuente de datos</span><select value={mode} onChange={e => onModeChange(e.target.value as 'demo' | 'live')}><option value="demo">DEMOSTRACIÓN</option><option value="live">ESTACIÓN REAL</option></select></label>
          {mission ? <PhaseChip phase={mission.phase} /> : <span className="mission-phase-unavailable">Fase no disponible</span>}
          <span className="mission-clock"><span className="sr-only">Tiempo de vuelo: </span>T+ <strong>{duration(elapsed)}</strong></span>
        </section>}
        logo={<span className="mission-brand"><img src={logo} alt="" /><span><span role="heading" aria-level={1} className="mission-brand-name">ORBITIUM</span><small>SATLINK · CONTROL DE MISIÓN</small></span></span>}
        logoAlt="Orbitium, ir al resumen" logoHref="#mission-summary" />
    </div>
  </header>
}
