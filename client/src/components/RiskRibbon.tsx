import { useEffect, useMemo, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchRiskHistory, type RiskHistItem, type Market } from '../api'
import { InfoDot } from '../ui'

// 风险灯 Section A:制度带 + 驱动图(宽度vs阈值 / SPY波动)+ 统计。RiskLight 详情页与 策略信号首屏 共用。
export type RLRange = 'ytd' | '90d' | 'all'
export const LV: Record<string, { c: string; t: string }> = {
  green: { c: 'var(--up)', t: '绿·可满仓' },
  amber: { c: 'var(--gold)', t: '黄·半仓' },
  red: { c: 'var(--down)', t: '红·空仓观望' },
}
export const lvC = (l: string) => LV[l]?.c || 'var(--ink-mute)'
export const pctS = (x: number | null | undefined) => (x == null ? '—' : `${(x * 100).toFixed(1)}%`)
export const filterRange = (asc: RiskHistItem[], range: RLRange) => {
  if (!asc.length || range === 'all') return asc
  if (range === '90d') return asc.slice(-90)
  const y = asc[asc.length - 1].asof.slice(0, 4)
  return asc.filter((d) => d.asof.slice(0, 4) === y)
}

export default function RiskRibbon({ market, range = 'ytd', rawData, onOpenDetail, title }: {
  market: Market; range?: RLRange; rawData?: RiskHistItem[]; onOpenDetail?: () => void; title?: string
}) {
  const [fetched, setFetched] = useState<RiskHistItem[]>([])
  const [loading, setLoading] = useState(!rawData)
  useEffect(() => {
    if (rawData) return
    setLoading(true)
    fetchRiskHistory(market).then((d) => { setFetched(d); setLoading(false) }).catch(() => setLoading(false))
  }, [market, rawData])

  const isCN = market === 'cn'
  const asc = useMemo(() => [...(rawData ?? fetched)].sort((a, b) => a.asof.localeCompare(b.asof)), [rawData, fetched])
  const data = useMemo(() => filterRange(asc, range), [asc, range])

  const stats = useMemo(() => {
    const cnt: Record<string, number> = { green: 0, amber: 0, red: 0 }
    data.forEach((d) => { cnt[d.level] = (cnt[d.level] || 0) + 1 })
    const cur = data.length ? data[data.length - 1].level : ''
    let streak = 0
    for (let i = data.length - 1; i >= 0 && data[i].level === cur; i--) streak++
    let flip: null | { date: string; from: string; to: string } = null
    for (let i = data.length - 1; i > 0; i--) {
      if (data[i].level !== data[i - 1].level) { flip = { date: data[i].asof, from: data[i - 1].level, to: data[i].level }; break }
    }
    return { n: data.length, cnt, cur, streak, flip }
  }, [data])

  const chartRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!chartRef.current || !data.length) return
    const chart = echarts.init(chartRef.current)
    const xs = data.map((d) => d.asof.slice(5))
    const main = data.map((d) => ((isCN ? d.breadth : d.spy_vol) ?? 0) * 100)
    const thr = isCN ? data.map((d) => (d.breadth_ma ?? 0) * 100) : []
    const series: any[] = [{
      name: isCN ? '市场宽度' : 'SPY年化波动', type: 'line', data: main, showSymbol: false, smooth: true,
      color: '#e6c878',   // 线 + 图例标记统一金色(只设 lineStyle 会让图例用默认调色板色 → 对不上)
      lineStyle: { width: 2 }, areaStyle: { color: 'rgba(200,162,83,.10)' },
    }]
    if (isCN) series.push({
      name: '翻灯阈值(宽度MA)', type: 'line', data: thr, showSymbol: false, smooth: true,
      color: '#7ba7b0',   // 线 + 图例标记统一蓝
      lineStyle: { width: 1.5, type: 'dashed' },
    })
    chart.setOption({
      backgroundColor: 'transparent',
      grid: { left: 44, right: 16, top: 30, bottom: 26 },
      legend: { top: 2, textStyle: { color: '#b0a488', fontSize: 11 }, itemWidth: 18 },
      tooltip: {
        trigger: 'axis', backgroundColor: '#1f1913', borderColor: '#2c2418', textStyle: { color: '#f1e9da' },
        formatter: (ps: any) => {
          const d = data[ps[0].dataIndex]
          return `<b>${d.asof}</b> <span style="color:${lvC(d.level)}">●</span>${LV[d.level]?.t}<br/>` +
            ps.map((p: any) => `${p.marker}${p.seriesName}: ${p.value.toFixed(1)}%`).join('<br/>') +
            `<br/>建议仓位 ${pctS(d.exposure)}`
        },
      },
      xAxis: {
        type: 'category', data: xs, axisLine: { lineStyle: { color: '#2c2418' } },
        axisLabel: { color: '#b0a488', fontSize: 10, interval: Math.max(0, Math.floor(xs.length / 10)) },
      },
      yAxis: {
        type: 'value', splitLine: { lineStyle: { color: '#241d15' } },
        axisLabel: { formatter: '{value}%', color: '#b0a488', fontSize: 10 },
      },
      series,
    })
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [data, isCN])

  if (loading) return <div className="card muted">风险灯加载中…</div>
  if (!data.length) return null
  const rangeLbl = range === 'ytd' ? '今年' : range === '90d' ? '近90天' : '全部'
  return (
    <div className="card">
      {title && (
        <div className="muted" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span>{title} <InfoDot text="市场级风险闸:决定总仓位(绿满/黄半/红空)。彩带=每日制度,曲线=宽度vs翻灯阈值,看现在处在什么体制、离翻灯多远。" /></span>
          {onOpenDetail && <button className="ghost mini" onClick={onOpenDetail} title="日历视图 + 信号分解 + 切市场/范围">详情 ›</button>}
        </div>
      )}
      <div className="rl-ribbon" title="每格一个交易日,颜色=当日风险灯">
        {data.map((d) => <span key={d.asof} className="rl-seg" style={{ background: lvC(d.level) }} title={`${d.asof} ${LV[d.level]?.t}`} />)}
      </div>
      <div className="rl-ribbon-x muted"><span>{data[0].asof}</span><span>{data[data.length - 1].asof}</span></div>
      <div ref={chartRef} style={{ height: 200, marginTop: 8 }} />
      <div className="rl-stats">
        <div className="rl-stat"><div className="muted">当前制度</div><div className="rl-big" style={{ color: lvC(stats.cur) }}>● {LV[stats.cur]?.t || '—'}</div></div>
        <div className="rl-stat"><div className="muted">已持续</div><div className="rl-big">{stats.streak} 个交易日</div></div>
        <div className="rl-stat"><div className="muted">{rangeLbl}占比</div>
          <div className="rl-mix">
            <span style={{ color: 'var(--up)' }}>绿{Math.round((stats.cnt.green / stats.n) * 100)}%</span>
            <span style={{ color: 'var(--gold)' }}>黄{Math.round((stats.cnt.amber / stats.n) * 100)}%</span>
            <span style={{ color: 'var(--down)' }}>红{Math.round((stats.cnt.red / stats.n) * 100)}%</span>
          </div>
        </div>
        <div className="rl-stat"><div className="muted">上次翻灯</div>
          <div className="rl-big">{stats.flip ? <>{stats.flip.date.slice(5)} <span style={{ color: lvC(stats.flip.from) }}>●</span>→<span style={{ color: lvC(stats.flip.to) }}>●</span></> : '本段无'}</div>
        </div>
      </div>
    </div>
  )
}
