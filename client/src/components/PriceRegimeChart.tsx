import { useEffect, useMemo, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchHistory, fetchSnapshot, type RiskHistItem, type Market } from '../api'
import { InfoDot } from '../ui'
import { lvC, LV } from './RiskRibbon'

// 灯 vs 走势对照图:制度彩带背景(A) + 归一化价格线(C,多标的) + 暴露阶梯(B,可开关) + 制度收益归因(D)。
const IDX: { code: string; label: string }[] = [
  { code: 'hs300', label: '沪深300' }, { code: 'zz500', label: '中证500' }, { code: 'zz800', label: '中证800' },
]
const LINE = ['#e6c878', '#7ba7b0', '#9a8ec4', '#6fae86', '#cf6f5d', '#d08a5a']
const lbl = (t: string) => IDX.find((i) => i.code === t)?.label || t

export default function PriceRegimeChart({ market, regime }: { market: Market; regime: RiskHistItem[] }) {
  // regime = 已按当前范围过滤的风险灯历史(升序)
  const [sel, setSel] = useState<string[]>(['hs300'])
  const [cache, setCache] = useState<Record<string, { date: string; close: number | null }[]>>({})
  const [rec, setRec] = useState<string[]>([])
  const [showExpo, setShowExpo] = useState(false)
  const [input, setInput] = useState('')
  const [err, setErr] = useState('')

  const isCN = market === 'cn'
  // 切市场:重置选择(A股默认大盘,美股无A股指数→留空待选)
  useEffect(() => { setSel(isCN ? ['hs300'] : []); setCache({}) }, [market])

  // 推荐股 chips(取当前市场快照持仓前若干)
  useEffect(() => {
    fetchSnapshot(undefined, market).then((s) => setRec((s.holdings || []).filter((h: any) => h.sleeve !== 'custom').slice(0, 6).map((h: any) => h.ticker))).catch(() => {})
  }, [market])

  // 拉缺失标的的历史(n 覆盖范围;显式传市场)
  useEffect(() => {
    const need = sel.filter((t) => !cache[t])
    if (!need.length) return
    need.forEach((t) => {
      fetchHistory(t, 500, market).then((h) => setCache((c) => ({ ...c, [t]: h.map((p) => ({ date: p.date, close: p.close })) })))
        .catch(() => setErr(`${t} 无数据`))
    })
  }, [sel, market])

  const dates = useMemo(() => regime.map((d) => d.asof), [regime])
  const d0 = dates[0], d1 = dates[dates.length - 1]

  // 各标的归一化到范围内首个有效收盘=100
  const lines = useMemo(() => sel.map((t) => {
    const h = cache[t]; if (!h) return { t, pts: [] as (number | null)[] }
    const m = new Map(h.map((p) => [p.date, p.close]))
    const inRange = dates.map((dt) => m.get(dt) ?? null)
    const base = inRange.find((v) => v != null) || null
    return { t, pts: base ? inRange.map((v) => (v == null ? null : (v / base) * 100)) : inRange }
  }), [sel, cache, dates])

  // 制度收益归因:主标的(第一个)在各制度下的日均收益
  const attrib = useMemo(() => {
    const prim = lines[0]; if (!prim || !prim.pts.length) return null
    const acc: Record<string, { sum: number; n: number }> = { green: { sum: 0, n: 0 }, amber: { sum: 0, n: 0 }, red: { sum: 0, n: 0 } }
    for (let i = 1; i < prim.pts.length; i++) {
      const a = prim.pts[i - 1], b = prim.pts[i]; if (a == null || b == null) continue
      const lv = regime[i]?.level; if (!lv || !acc[lv]) continue
      acc[lv].sum += (b - a) / a; acc[lv].n++
    }
    return acc
  }, [lines, regime])

  // ── echarts ──
  const chartRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!chartRef.current || !dates.length) return
    const chart = echarts.init(chartRef.current)
    // 制度带:连续同级 → markArea
    const areas: any[] = []
    let s = 0
    for (let i = 1; i <= regime.length; i++) {
      if (i === regime.length || regime[i].level !== regime[s].level) {
        areas.push([{ xAxis: dates[s], itemStyle: { color: lvC(regime[s].level), opacity: 0.12 } }, { xAxis: dates[i - 1] }])
        s = i
      }
    }
    const series: any[] = lines.map((ln, i) => ({
      name: lbl(ln.t), type: 'line', data: ln.pts, showSymbol: false, smooth: true, connectNulls: true,
      color: LINE[i % LINE.length], lineStyle: { width: 1.8 },
      ...(i === 0 ? { markArea: { silent: true, data: areas } } : {}),
    }))
    if (showExpo) series.push({
      name: '建议仓位', type: 'line', yAxisIndex: 1, step: 'end', showSymbol: false,
      data: regime.map((d) => d.exposure * 100), color: '#8a7238', lineStyle: { width: 1, type: 'dashed' },
    })
    chart.setOption({
      backgroundColor: 'transparent',
      grid: { left: 44, right: showExpo ? 44 : 16, top: 30, bottom: 26 },
      legend: { top: 2, textStyle: { color: '#b0a488', fontSize: 11 }, itemWidth: 16 },
      tooltip: {
        trigger: 'axis', backgroundColor: '#1f1913', borderColor: '#2c2418', textStyle: { color: '#f1e9da' },
        formatter: (ps: any) => {
          const i = ps[0].dataIndex; const d = regime[i]
          return `<b>${dates[i]}</b> <span style="color:${lvC(d.level)}">●</span>${LV[d.level]?.t}<br/>` +
            ps.filter((p: any) => p.seriesName !== '建议仓位').map((p: any) => `${p.marker}${p.seriesName}: ${p.value == null ? '—' : p.value.toFixed(1)}`).join('<br/>')
        },
      },
      xAxis: {
        type: 'category', data: dates, boundaryGap: false, axisLine: { lineStyle: { color: '#2c2418' } },
        axisLabel: { color: '#b0a488', fontSize: 10, interval: Math.max(0, Math.floor(dates.length / 10)) },
      },
      yAxis: [
        { type: 'value', scale: true, name: '归一=100', nameTextStyle: { color: '#b0a488', fontSize: 10 }, axisLabel: { color: '#b0a488', fontSize: 10 }, splitLine: { lineStyle: { color: '#241d15' } } },
        ...(showExpo ? [{ type: 'value', min: 0, max: 100, name: '仓位%', position: 'right', axisLabel: { formatter: '{value}%', color: '#8a7238', fontSize: 10 }, splitLine: { show: false } }] : []),
      ],
      series,
    })
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [lines, dates, regime, showExpo])

  const toggle = (t: string) => setSel((s) => (s.includes(t) ? s.filter((x) => x !== t) : [...s, t]))
  const addInput = () => {
    const t = input.trim(); if (!t) return
    if (!sel.includes(t)) setSel((s) => [...s, t]); setInput(''); setErr('')
  }

  if (!dates.length) return null
  return (
    <div className="card">
      <h3 style={{ marginBottom: 8 }}>灯 vs 走势对照 <InfoDot text="价格线背后铺风险灯制度色带,直接看'红灯那段是不是真跌了'。多标的归一化到100可比。底部给红/绿灯期的日均收益,数字硬证灯准不准。" /></h3>
      <div className="prc-pick">
        {isCN && <><span className="muted">大盘</span>
        {IDX.map((i) => <button key={i.code} className={`chip ${sel.includes(i.code) ? 'on' : ''}`} onClick={() => toggle(i.code)}>{i.label}</button>)}</>}
        {rec.length > 0 && <><span className="muted" style={{ marginLeft: 6 }}>推荐股</span>
          {rec.map((t) => <button key={t} className={`chip ${sel.includes(t) ? 'on' : ''}`} onClick={() => toggle(t)}>{t.replace(/^(sh|sz)\./, '')}</button>)}</>}
        <input className="prc-input" value={input} placeholder="输代码 如600519" onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addInput()} />
        <button className="chip" onClick={addInput}>+加</button>
        <label className="prc-expo"><input type="checkbox" checked={showExpo} onChange={(e) => setShowExpo(e.target.checked)} /> 叠加建议仓位</label>
      </div>
      {err && <div className="down" style={{ fontSize: 12, marginBottom: 4 }}>{err}</div>}
      <div ref={chartRef} style={{ height: 260 }} />
      {attrib && (
        <div className="prc-attrib muted">
          <b style={{ color: 'var(--ink-soft)' }}>{lbl(sel[0])}</b> 各制度日均:
          <span style={{ color: 'var(--up)' }}> 绿灯 {attrib.green.n ? (attrib.green.sum / attrib.green.n * 100).toFixed(2) : '—'}%</span>
          <span style={{ color: 'var(--gold)' }}> · 黄灯 {attrib.amber.n ? (attrib.amber.sum / attrib.amber.n * 100).toFixed(2) : '—'}%</span>
          <span style={{ color: 'var(--down)' }}> · 红灯 {attrib.red.n ? (attrib.red.sum / attrib.red.n * 100).toFixed(2) : '—'}%</span>
          <span> — 红灯日均&lt;绿灯 说明灯有效择时</span>
        </div>
      )}
    </div>
  )
}
