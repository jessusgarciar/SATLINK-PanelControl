import { useEffect, useRef, useState } from 'react'
import type { MissionGateway } from '../../application/ports.ts'
import { WINDOW_OPTIONS } from '../../domain/history.ts'
import type { TimeRange, WindowKey } from '../../domain/history.ts'

export default function ArchiveToolbar({ gateway, selected, setSelected, range, total, seriesCount, trackCount, loading, error, openHistory, onActivity }: {
  gateway: MissionGateway; selected: WindowKey; setSelected: (key: WindowKey) => void; range: TimeRange | null; total: number | null; seriesCount: number; trackCount: number; loading: boolean; error: string | null; openHistory: () => void; onActivity: (message: string) => void
}) {
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  const abort = useRef<AbortController | null>(null)
  useEffect(() => () => { abort.current?.abort() }, [gateway, selected])
  const exportCsv = async () => {
    if (!range) return
    abort.current?.abort()
    const request = new AbortController()
    abort.current = request
    setExporting(true); setExportError(null)
    try {
      const blob = await gateway.exportCsv(range, request.signal)
      if (request.signal.aborted) return
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url; link.download = 'satlink-' + (gateway.mode === 'demo' ? 'simulado-' : '') + range.to.replaceAll(':', '-') + '.csv'
      document.body.append(link); link.click(); link.remove()
      onActivity('CSV ' + (gateway.mode === 'demo' ? 'simulado' : 'histórico') + ': descarga preparada · ' + range.to)
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (error) { if (!request.signal.aborted) { const message = error instanceof Error ? error.message : 'Falló la exportación.'; setExportError(message); onActivity('CSV: ' + message) } }
    finally { if (abort.current === request) setExporting(false) }
  }
  return <section className="panel archive-controls" aria-label="Archivo de telemetría">
    <div className="archive-toolbar">
      <label>Ventana <select value={selected} onChange={(e) => { setExportError(null); setSelected(e.target.value as WindowKey) }}>{WINDOW_OPTIONS.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}</select></label>
      <span role="status">{loading ? 'Actualizando archivo…' : total === null ? 'Archivo no disponible' : total + ' registros'}</span>
      <button className="button subtle" disabled={!range || exporting || loading} onClick={() => void exportCsv()}>{exporting ? 'Exportando…' : '↓ CSV completo'}</button>
      {exporting && <button className="text-button" onClick={() => { abort.current?.abort(); setExporting(false) }}>Cancelar descarga</button>}
      <button className="button subtle" disabled={!range || loading} onClick={openHistory}>▶ Histórico</button>
    </div>
    <p className="archive-caption">Filtro para mapa, gráficas y CSV. Las tarjetas muestran la última recepción. {gateway.mode === 'demo' && 'Archivo limitado a la ventana del simulador.'}</p>
    {range && <p className="archive-caption">Gráficas: {seriesCount} muestras · Trayectoria: {trackCount} posiciones GPS · CSV: todos los registros del intervalo.</p>}
    {range && <p className="archive-caption">Intervalo visual: {range.from ? new Date(range.from).toLocaleString() : 'Inicio'} → {new Date(range.to).toLocaleString()}.</p>}
    {(error || exportError) && <p role="alert" className="tone-amber">{exportError ?? error} {error && 'Se conserva el último intervalo consultado.'}</p>}
  </section>
}
