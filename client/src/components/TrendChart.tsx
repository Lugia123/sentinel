import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { RichTrendPoint, TickerMeta } from '../api'

const C = ['#c8a253', '#6fae86', '#cf6f5d', '#9a8ec4', '#7ba7b0', '#e6c878', '#d19a66', '#84b6c4']

export interface MetricDef { key: string; label: string; pct: boolean; fixed: boolean }

// 单个分析维度的走势图(一图内对比多只股)。多维度时每维一个 TrendChart 堆叠显示。
export default function TrendChart({ m, series, meta }: {
  m: MetricDef
  series: Record<string, RichTrendPoint[]>
  meta: TickerMeta
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    const keys = Object.keys(series)
    chart.setOption({
      backgroundColor: 'transparent', grid: { left: 52, right: 20, top: 34, bottom: 30 },
      legend: { textStyle: { color: '#bcae97' }, top: 0 },
      tooltip: {
        trigger: 'axis', backgroundColor: '#1f1913', borderColor: '#2c2418', textStyle: { color: '#f1e9da' },
        valueFormatter: (v: any) => (v == null ? '—' : m.pct ? (v * 100).toFixed(1) + '%' : String(v)),
      },
      xAxis: { type: 'time', axisLabel: { color: '#b0a488' }, axisLine: { lineStyle: { color: '#2c2418' } } },
      yAxis: {
        type: 'value', name: m.label, nameTextStyle: { color: '#b0a488', fontSize: 12 },
        ...(m.fixed ? { min: -3, max: 3, interval: 1 } : {}),
        axisLabel: { color: '#b0a488', formatter: (v: number) => (m.pct ? (v * 100).toFixed(0) + '%' : String(v)) },
        splitLine: { lineStyle: { color: '#241d15' } },
      },
      series: keys.map((k, i) => ({
        name: k + (meta[k] ? ' ' + meta[k].cn : ''), type: 'line', step: m.key === 'grade' ? 'end' : false,
        showSymbol: false, connectNulls: false,
        lineStyle: { color: C[i % C.length], width: 2 }, itemStyle: { color: C[i % C.length] },
        data: (series[k] || []).map((p) => [p.date, (p as any)[m.key]]),
      })),
    })
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [series, m, meta])
  return <div ref={ref} style={{ height: 340 }} />
}
