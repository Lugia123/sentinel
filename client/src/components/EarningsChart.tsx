import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { EarnQuarter } from '../api'

// 财报可视化(确定性作图,数据=官方季度数,非AI生成):
// 柱=营收/净利(美股:亿美元;A股:亿元),线=净利率%。近8季按时间正序。
export default function EarningsChart({ quarters, unit = '亿美元' }: { quarters: EarnQuarter[]; unit?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const qs = [...quarters].reverse().slice(-8) // 正序,取近8季
    const yi = (v: number | null) => (v == null ? null : +(v / 1e8).toFixed(1)) // →亿(美元/元)
    const dates = qs.map((q) => q.period.slice(0, 7))
    const rev = qs.map((q) => yi(q.revenue))
    const ni = qs.map((q) => yi(q.net_income))
    const margin = qs.map((q) => (q.revenue && q.net_income != null ? +((q.net_income / q.revenue) * 100).toFixed(1) : null))
    const chart = echarts.init(ref.current)
    chart.setOption({
      backgroundColor: 'transparent', grid: { left: 52, right: 52, top: 34, bottom: 28 },
      legend: { textStyle: { color: '#bcae97' }, top: 0 },
      tooltip: { trigger: 'axis', backgroundColor: '#1f1913', borderColor: '#2c2418', textStyle: { color: '#f1e9da' } },
      xAxis: { type: 'category', data: dates, axisLabel: { color: '#b0a488' }, axisLine: { lineStyle: { color: '#2c2418' } } },
      yAxis: [
        { type: 'value', name: unit, nameTextStyle: { color: '#b0a488', fontSize: 12 }, axisLabel: { color: '#b0a488' }, splitLine: { lineStyle: { color: '#241d15' } } },
        { type: 'value', name: '净利率', position: 'right', axisLabel: { color: '#6fae86', formatter: '{value}%' }, splitLine: { show: false } },
      ],
      series: [
        { name: '营收', type: 'bar', data: rev, itemStyle: { color: '#c8a253' }, barMaxWidth: 26 },
        { name: '净利润', type: 'bar', data: ni, itemStyle: { color: '#8a7238' }, barMaxWidth: 26 },
        { name: '净利率', type: 'line', yAxisIndex: 1, data: margin, showSymbol: true, symbolSize: 6, lineStyle: { color: '#6fae86', width: 2 }, itemStyle: { color: '#6fae86' } },
      ],
    })
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [quarters, unit])
  return <div ref={ref} style={{ height: 260 }} />
}
