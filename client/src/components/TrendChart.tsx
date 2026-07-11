import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { RichTrendPoint } from '../api'

const C = ['#c8a253', '#6fae86', '#cf6f5d', '#9a8ec4', '#7ba7b0', '#e6c878', '#d19a66', '#84b6c4']

export interface AuxDef { key: string; label: string; dollar: boolean }
export interface MetricDef { key: string; label: string; pct: boolean; fixed: boolean; aux?: AuxDef[] }

// 单维度走势图:主指标(每股一条)。
// 单选1只股 → 深度模式:叠加该维度相关的辅助指标(如档位图叠 收盘价+20日线;动量图叠另一动量)。
// 多选 → 对比模式:只显示主指标,避免堆成一团。
// names: ticker→中文名;cur: 价格轴货币符(美股$ / A股¥)。
export default function TrendChart({ m, series, names = {}, cur = '$' }: {
  m: MetricDef
  series: Record<string, RichTrendPoint[]>
  names?: Record<string, string>
  cur?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    const keys = Object.keys(series)
    const single = keys.length === 1
    const aux = single ? (m.aux || []) : []
    const hasDollarAux = aux.some((a) => a.dollar)
    const fmtMain = (v: any) => (v == null ? '—' : m.pct ? (v * 100).toFixed(1) + '%' : String(v))

    const yAxes: any[] = [{
      type: 'value', name: m.label, nameTextStyle: { color: '#b0a488', fontSize: 12 },
      ...(m.fixed ? { min: -3, max: 3, interval: 1 } : {}),
      axisLabel: { color: '#b0a488', formatter: (v: number) => (m.pct ? (v * 100).toFixed(0) + '%' : String(v)) },
      splitLine: { lineStyle: { color: '#241d15' } },
    }]
    if (hasDollarAux) {
      yAxes.push({ type: 'value', name: cur, position: 'right', scale: true,
        axisLabel: { color: '#7ba7b0' }, splitLine: { show: false } })
    }

    const mainSeries = keys.map((k, i) => ({
      name: k + (names[k] ? ' ' + names[k] : ''), type: 'line', step: m.key === 'grade' ? 'end' : false,
      showSymbol: false, connectNulls: false, z: 3,
      lineStyle: { color: C[i % C.length], width: 2 }, itemStyle: { color: C[i % C.length] },
      data: (series[k] || []).map((p) => [p.date, (p as any)[m.key]]),
    }))
    // 辅助线(仅单股):次轴$的走虚线,同轴%的走细实线
    const auxColors = ['#7ba7b0', '#9a8ec4', '#d19a66']
    const auxSeries = aux.map((a, i) => ({
      name: a.label, type: 'line', showSymbol: false, connectNulls: true, z: 1,
      yAxisIndex: a.dollar && hasDollarAux ? 1 : 0,
      lineStyle: { color: auxColors[i % auxColors.length], width: 1.4, type: a.dollar ? 'dashed' : 'solid', opacity: 0.85 },
      itemStyle: { color: auxColors[i % auxColors.length] },
      data: (series[keys[0]] || []).map((p) => [p.date, (p as any)[a.key]]),
    }))

    chart.setOption({
      backgroundColor: 'transparent', grid: { left: 52, right: hasDollarAux ? 52 : 20, top: 34, bottom: 30 },
      legend: { textStyle: { color: '#bcae97' }, top: 0 },
      tooltip: {
        trigger: 'axis', backgroundColor: '#1f1913', borderColor: '#2c2418', textStyle: { color: '#f1e9da' },
        valueFormatter: (v: any) => (v == null ? '—' : fmtMain(v)),
      },
      xAxis: { type: 'time', axisLabel: { color: '#b0a488' }, axisLine: { lineStyle: { color: '#2c2418' } } },
      yAxis: yAxes,
      series: [...mainSeries, ...auxSeries],
    })
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [series, m, names, cur])
  return <div ref={ref} style={{ height: 340 }} />
}
