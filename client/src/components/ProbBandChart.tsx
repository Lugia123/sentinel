import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { Holding } from '../types'

// 概率带可视化:5/20/60日 70%收益区间(横条)+ 中位(竖线),把概率表变成一眼看懂的图。
export default function ProbBandChart({ prob }: { prob: Holding['prob'] }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const rows = [
      { k: 'h60', label: '60日' }, { k: 'h20', label: '20日' }, { k: 'h5', label: '5日' },
    ].filter((r) => prob[r.k])
    const chart = echarts.init(ref.current)
    const bands = rows.map((r, i) => {
      const b = prob[r.k]
      return { value: [i, b.band70[0] * 100, b.band70[1] * 100, b.median * 100] }
    })
    chart.setOption({
      backgroundColor: 'transparent', grid: { left: 48, right: 20, top: 12, bottom: 26 },
      tooltip: {
        backgroundColor: '#1f1913', borderColor: '#2c2418', textStyle: { color: '#f1e9da' },
        formatter: (p: any) => {
          const b = prob[rows[p.data.value[0]].k]
          return `${rows[p.data.value[0]].label}<br/>中位 ${(b.median * 100).toFixed(1)}%<br/>70%区间 ${(b.band70[0] * 100).toFixed(1)}% ~ ${(b.band70[1] * 100).toFixed(1)}%`
        },
      },
      xAxis: { type: 'value', axisLabel: { formatter: '{value}%', color: '#b0a488' }, splitLine: { lineStyle: { color: '#241d15' } } },
      yAxis: { type: 'category', data: rows.map((r) => r.label), axisLabel: { color: '#b0a488' }, axisLine: { lineStyle: { color: '#2c2418' } }, axisTick: { show: false } },
      series: [{
        type: 'custom', encode: { x: [1, 2, 3], y: 0 },
        renderItem: (_: any, api: any) => {
          const cat = api.value(0)
          const lo = api.coord([api.value(1), cat]); const hi = api.coord([api.value(2), cat]); const med = api.coord([api.value(3), cat])
          const bh = 16, y = lo[1] - bh / 2
          const up = api.value(3) >= 0
          const color = up ? '#6fae86' : '#cf6f5d'
          return { type: 'group', children: [
            { type: 'rect', shape: { x: lo[0], y, width: hi[0] - lo[0], height: bh }, style: { fill: '#c8a253', opacity: 0.28 } },
            { type: 'line', shape: { x1: med[0], y1: y - 2, x2: med[0], y2: y + bh + 2 }, style: { stroke: color, lineWidth: 2 } },
          ] }
        },
        data: bands,
      }],
      markLine: {},
    })
    // 0% 参考线
    chart.setOption({ series: [{ markLine: { silent: true, symbol: 'none', lineStyle: { color: '#3a2f1e', type: 'dashed' }, data: [{ xAxis: 0 }] } }] } as any)
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [prob])
  return <div ref={ref} style={{ height: 150 }} />
}
