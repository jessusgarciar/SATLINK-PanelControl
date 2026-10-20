import type { SVGProps } from 'react'

export type MissionIconName = 'summary' | 'map' | 'charts' | 'archive' | 'ascent' | 'radio' | 'device' | 'settings'
const paths: Record<MissionIconName, string> = {
  summary: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  map: 'm3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6 M9 3v15 M15 6v15',
  charts: 'M4 3v17h17 M7 14l4-5 4 3 6-8',
  archive: 'M4 4h16v5H4z M6 9v12h12V9 M10 13h4',
  ascent: 'M12 21V3 m-6 6 6-6 6 6 M5 21h14',
  radio: 'M12 18v3 M9 21h6 M12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4 M6.3 6.3a8 8 0 0 0 0 11.4 M17.7 6.3a8 8 0 0 1 0 11.4 M3.5 3.5a12 12 0 0 0 0 17 M20.5 3.5a12 12 0 0 1 0 17',
  device: 'M6 6h12v12H6z M10 10h4v4h-4z M9 2v4 M15 2v4 M9 18v4 M15 18v4 M2 9h4 M2 15h4 M18 9h4 M18 15h4',
  settings: 'M4 6h16 M4 12h16 M4 18h16 M8 3v6 M16 9v6 M10 15v6',
}
export default function MissionIcon({ name, ...props }: SVGProps<SVGSVGElement> & { name: MissionIconName }) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" {...props}><path d={paths[name]} /></svg>
}
