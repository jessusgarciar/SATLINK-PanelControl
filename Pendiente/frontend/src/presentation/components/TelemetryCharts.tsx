import { memo, useMemo } from 'react'
import ReactEChartsCore from 'echarts-for-react/esm/core'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, AriaComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption, LineSeriesOption } from 'echarts'
import type { Telemetry } from '../../domain/mission.ts'
import { telemetryPoints } from '../readings.ts'
import { aggregateSamples, chartInterval } from '../chartReadings.ts'
import { SectionTitle } from './ui.tsx'

echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  AriaComponent,
  CanvasRenderer,
])
const colors = {
  cyan: '#2563eb',
  amber: '#d97706',
  purple: '#7c3aed',
  blue: '#0284c7',
  green: '#16a34a',
}
const chartOptions = { renderer: 'canvas' as const }
type SeriesConfig = {
  key: keyof Telemetry
  label: string
  color: string
  scale?: number
  area?: boolean
  axis?: number
}
const configs: { title: string; unit: string; series: SeriesConfig[]; secondUnit?: string }[] = [
  {
    title: 'Altitud GPS vs barométrica',
    unit: 'km',
    series: [
      { key: 'altitudeGpsM', label: 'GPS', color: colors.cyan, scale: 0.001, area: true },
      { key: 'altitudeBarometricM', label: 'Barométrica', color: colors.blue, scale: 0.001 },
    ],
  },
  {
    title: 'Temperatura interna (°C)',
    unit: '°C',
    series: [{ key: 'temperatureC', label: 'Temperatura', color: colors.amber, area: true }],
  },
  {
    title: 'Humedad (%) · Presión (hPa)',
    unit: '%',
    secondUnit: 'hPa',
    series: [
      { key: 'humidityPct', label: 'Humedad', color: colors.purple },
      { key: 'pressureHpa', label: 'Presión', color: colors.blue, axis: 1 },
    ],
  },
  {
    title: 'Voltaje batería (V)',
    unit: 'V',
    series: [{ key: 'batteryV', label: 'Batería', color: colors.green, area: true }],
  },
]
const chartMetricKeys = [...new Set(configs.flatMap((config) => config.series.map((series) => series.key)))]

function intervalLabel(interval: number): string {
  return interval < 60_000 ? '20 s' : `${interval / 60_000} min`
}

const Chart = memo(function Chart({
  samples,
  config,
}: {
  samples: Telemetry[]
  config: (typeof configs)[number]
}) {
  const interval = useMemo(() => chartInterval(samples), [samples])
  const points = useMemo(() => aggregateSamples(samples, interval, chartMetricKeys), [samples, interval])
  const option = useMemo<EChartsOption>(() => {
    const series: LineSeriesOption[] = config.series.map((s) => ({
      name: s.label,
      type: 'line',
      showSymbol: false,
      symbolSize: 4,
      emphasis: { focus: 'series', scale: 1.3 },
      connectNulls: true,
      sampling: 'lttb',
      yAxisIndex: s.axis ?? 0,
      lineStyle: { width: 1.6, color: s.color },
      itemStyle: { color: s.color },
      areaStyle: s.area
        ? {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: s.color + '28' },
              { offset: 1, color: s.color + '00' },
            ]),
          }
        : undefined,
      data: telemetryPoints(points, s.key, s.scale),
    }))
    const axis = (unit: string) => ({
      type: 'value' as const,
      scale: true,
      splitNumber: 3,
      axisLabel: {
        color: '#64748b',
        fontSize: 9,
        formatter: (v: number) => (unit === 'V' ? v.toFixed(3) : +v.toFixed(2)) + ' ' + unit,
      },
      splitLine: { lineStyle: { color: '#dbe3ee', type: 'dashed' as const } },
    })
    return {
      animation: false,
      aria: {
        enabled: true,
        label: {
          description:
            config.title +
            '. Resumen por intervalos de ' + intervalLabel(interval) +
            ', con la mediana de las muestras recibidas. ' +
            points.length +
            ' muestras, ordenadas por hora de recepción. Las lecturas actuales están disponibles en las tarjetas de sensores.',
        },
      },
      textStyle: { fontFamily: 'JetBrains Mono, monospace' },
      grid: { left: 9, right: 9, top: 28, bottom: 4, containLabel: true },
      tooltip: {
        trigger: 'axis',
        triggerOn: 'mousemove|click|mousewheel',
        axisPointer: { type: 'line', lineStyle: { color: '#2563eb', width: 1 } },
        renderMode: 'richText',
        backgroundColor: '#ffffff',
        borderColor: '#dbe3ee',
        textStyle: { color: '#1e293b', fontSize: 11 },
        valueFormatter: (value) =>
          value === null
            ? 'No disponible'
            : typeof value === 'number'
              ? value.toFixed(3)
              : String(value),
      },
      legend: {
        show: config.series.length > 1,
        top: 0,
        right: 4,
        icon: 'roundRect',
        itemHeight: 3,
        itemWidth: 12,
        textStyle: { color: '#64748b', fontSize: 9 },
      },
      xAxis: {
        type: 'time',
        axisLine: { lineStyle: { color: '#dbe3ee' } },
        axisTick: { show: false },
        axisLabel: {
          color: '#64748b',
          fontSize: 9,
          hideOverlap: true,
          formatter: (v: number) =>
            new Date(v).toLocaleTimeString('es-MX', { minute: '2-digit', second: '2-digit' }),
        },
        splitNumber: 4,
      },
      yAxis: config.secondUnit
        ? [axis(config.unit), { ...axis(config.secondUnit), splitLine: { show: false } }]
        : axis(config.unit),
      series,
    }
  }, [points, config, interval])
  return (
    <section className="panel chart-panel">
      <SectionTitle>{config.title}</SectionTitle>
      <p className="chart-hint">Mediana cada {intervalLabel(interval)} · Toca la gráfica para consultar el valor</p>
      {config.series.some(s => telemetryPoints(samples, s.key).length > 0) ? (
        <ReactEChartsCore
          echarts={echarts}
          option={option}
          opts={chartOptions}
          style={{ height: 163, width: '100%' }}
          notMerge
          lazyUpdate
        />
      ) : (
        <div className="chart-empty">Esperando muestras válidas</div>
      )}
    </section>
  )
})
export default function TelemetryCharts({ samples, sectionId }: { samples: Telemetry[]; sectionId?: string }) {
  return (
    <div id={sectionId} tabIndex={sectionId ? -1 : undefined} className="charts-grid">
      {configs.map((config) => (
        <Chart key={config.title} samples={samples} config={config} />
      ))}
    </div>
  )
}
