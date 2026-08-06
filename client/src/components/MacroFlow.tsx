import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchMacroFlow, type MacroFlow as MacroData } from '../api'
import { InfoDot, riseColor, fallColor } from '../ui'

// 大盘 + 北向资金流(纯展示,不进策略)。compact=首屏精简 ribbon;否则=资金流页顶部富面板。
const yi = (x: number | null | undefined) => (x == null ? '—' : `${x >= 0 ? '+' : ''}${x.toFixed(1)}亿`)
const sign = (x: number | null | undefined) => (x == null ? 'muted' : x > 0 ? 'up' : x < 0 ? 'down' : 'muted')

// 迷你/常规柱状趋势:柱按正负=涨色/跌色
function bars(el: HTMLDivElement, dates: string[], vals: (number | null)[], compact: boolean) {
  const chart = echarts.init(el)
  const rise = riseColor(), fall = fallColor()
  chart.setOption({
    backgroundColor: 'transparent',
    grid: compact ? { left: 2, right: 2, top: 4, bottom: 2 } : { left: 40, right: 8, top: 10, bottom: 20 },
    tooltip: compact ? { show: false } : {
      trigger: 'axis', backgroundColor: '#1f1913', borderColor: '#2c2418', textStyle: { color: '#f1e9da' },
      formatter: (ps: any) => `${dates[ps[0].dataIndex]}<br/>${yi(ps[0].value)}`,
    },
    xAxis: { type: 'category', data: dates, show: !compact, axisLabel: { color: '#b0a488', fontSize: 10 }, axisLine: { lineStyle: { color: '#2c2418' } } },
    yAxis: { type: 'value', show: !compact, axisLabel: { color: '#b0a488', fontSize: 10, formatter: '{value}' }, splitLine: { lineStyle: { color: '#241d15' } } },
    series: [{
      type: 'bar', data: vals.map((v) => ({ value: v, itemStyle: { color: v == null ? '#555' : v >= 0 ? rise : fall } })),
      barMaxWidth: compact ? 4 : 14,
    }],
  })
  return chart
}

export default function MacroFlow({ compact = false, onOpen }: { compact?: boolean; onOpen?: () => void }) {
  const [d, setD] = useState<MacroData | null>(null)
  const [loading, setLoading] = useState(true)
  const northRef = useRef<HTMLDivElement>(null)
  const mktRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let alive = true
    fetchMacroFlow().then((x) => { if (alive) { setD(x); setLoading(false) } })
    return () => { alive = false }
  }, [])

  useEffect(() => {
    if (!d) return
    const cs: echarts.ECharts[] = []
    if (northRef.current && d.north.length) cs.push(bars(northRef.current, d.north.map((p) => p.date.slice(5)), d.north.map((p) => p.north), compact))
    if (mktRef.current && d.market.length) cs.push(bars(mktRef.current, d.market.map((p) => p.date.slice(5)), d.market.map((p) => p.net), compact))
    const onR = () => cs.forEach((c) => c.resize()); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); cs.forEach((c) => c.dispose()) }
  }, [d, compact])

  if (loading && compact) return null
  if (!d) return compact ? null : <div className="card muted">大盘/北向资金流暂不可用。</div>
  const s = d.summary

  // 首屏精简 ribbon
  if (compact) {
    return (
      <div className="mac-ribbon card" onClick={onOpen} title="点看资金流全景">
        <div className="mac-rb-item">
          <span className="mac-rb-lbl">北向今日</span>
          <b className={sign(s.north_today)}>{yi(s.north_today)}</b>
          <div ref={northRef} className="mac-spark" />
        </div>
        <div className="mac-rb-sep" />
        <div className="mac-rb-item">
          <span className="mac-rb-lbl">大盘主力今日</span>
          <b className={sign(s.market_today)}>{yi(s.market_today)}</b>
          <div ref={mktRef} className="mac-spark" />
        </div>
        <div className="mac-rb-sep" />
        <div className="mac-rb-item">
          <span className="mac-rb-lbl">沪指</span>
          <b className={sign(s.pct_sh)}>{s.pct_sh == null ? '—' : (s.pct_sh >= 0 ? '+' : '') + s.pct_sh + '%'}</b>
          <span className="mac-rb-more">资金流全景 ›</span>
        </div>
      </div>
    )
  }

  // 资金流页顶部富面板
  return (
    <div className="mac-panels">
      <div className="card">
        <div className="mac-head"><h3>北向资金 <span className="mac-tag">聪明钱</span></h3>
          <InfoDot text="沪股通+深股通净流入(外资)。北向被视为聪明钱,常作市场情绪参考。纯展示,非投资建议。" /></div>
        <div className="mac-hero"><span className="mac-lbl">今日净流入</span><span className={`mac-big ${sign(s.north_today)}`}>{yi(s.north_today)}</span>
          <span className="mac-sub2">近5日 <b className={sign(s.north_5d)}>{yi(s.north_5d)}</b></span></div>
        <div className="mac-cap">近{d.north.length}日北向净流入</div>
        <div ref={northRef} style={{ height: 140 }} />
      </div>
      <div className="card">
        <div className="mac-head"><h3>大盘主力资金</h3>
          <InfoDot text="两市主力(超大单+大单)净流入 + 沪深涨跌。纯展示,非投资建议。" /></div>
        <div className="mac-hero"><span className="mac-lbl">今日净流入</span><span className={`mac-big ${sign(s.market_today)}`}>{yi(s.market_today)}</span>
          <span className="mac-sub2">沪 <b className={sign(s.pct_sh)}>{s.pct_sh == null ? '—' : (s.pct_sh >= 0 ? '+' : '') + s.pct_sh + '%'}</b></span></div>
        <div className="mac-cap">近{d.market.length}日大盘主力净流入</div>
        <div ref={mktRef} style={{ height: 140 }} />
      </div>
    </div>
  )
}
