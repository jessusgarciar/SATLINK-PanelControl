import { useEffect, useState } from 'react'
import GooeyNav from './react-bits/GooeyNav.tsx'
import MissionIcon from './MissionIcon.tsx'

const destinations = [
  { label: 'Resumen', href: '#mission-summary', icon: <MissionIcon name="summary" /> },
  { label: 'Mapa', href: '#mission-map', icon: <MissionIcon name="map" /> },
  { label: 'Gráficas', href: '#mission-charts', icon: <MissionIcon name="charts" /> },
  { label: 'Archivo', href: '#mission-archive', icon: <MissionIcon name="archive" /> },
]

export default function MissionNavigation() {
  const [active, setActive] = useState(0)
  useEffect(() => {
    let frame = 0
    const update = () => {
      frame = 0
      let current = 0
      destinations.forEach((destination, index) => {
        const element = document.querySelector(destination.href)
        if (element && element.getBoundingClientRect().top <= window.innerHeight * 0.4) current = index
      })
      setActive(current)
    }
    const schedule = () => { if (!frame) frame = requestAnimationFrame(update) }
    window.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', schedule)
    update()
    return () => { cancelAnimationFrame(frame); window.removeEventListener('scroll', schedule); window.removeEventListener('resize', schedule) }
  }, [])
  return <div className="mission-bottom-nav">
    <GooeyNav ariaLabel="Secciones de misión" items={destinations} activeIndex={active} onChange={setActive} theme="dark" color="#00e5ff" activeTextColor="#04121d" frame={true} size="md" particleCount={8} spread={28} wobble={0.2} animationTime={520} timeVariance={300} gooeyness={0.5} hoverEffect={false} className="orbitium-gooey" />
  </div>
}
