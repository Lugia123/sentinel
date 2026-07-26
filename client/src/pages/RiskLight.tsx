import { useEffect, useMemo, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchRiskHistory, type RiskHistItem, type Market } from '../api'
import { InfoDot } from '../ui'

// 风险灯历史页:A 制度带+驱动图 / B 日历热力图 / C 四信号分解。市场切换 + 时间范围。
const LV: Record<string, { c: string; t: string }> = {
  green: { c: 'var(--up)', t: '绿·可满仓' },
  amber: { c: 'var(--gold)', t: '黄·半仓' },
  red: { c: 'var(--down)', t: '红·空仓观望' },
}
const lvC = (l: string) => LV[l]?.c || 'var(--ink-mute)'
const pctS = (x: number | null | undefined) => (x == null ? '—' : `${(x * 100).toFixed(1)}%`)

export default function RiskLight({ initialMarket = 'cn', onBack }: { initialMarket?: Market; onBack?: () => void }) {
  const [mkt, setMkt] = useState<Market>(initialMarket)
  const [range, setRange] = useState<'ytd' | '90d' | 'all'>('ytd')
  const [raw, setRaw] = useState<RiskHistItem[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    setLoading(true)
    fetchRiskHistory(mkt).then((d) => { setRaw(d); setLoading(false) }).catch(() => setLoading(false))
  }, [mkt])

  const isCN = mkt === 'cn'
  const asc = useMemo(() => [...raw].sort((a, b) => a.asof.localeCompare(b.asof)), [raw])
  const data = useMemo(() => {
    if (!asc.length) return asc
    if (range === 'all') return asc
    if (range === '90d') return asc.slice(-90)
    const y = asc[asc.length - 1].asof.slice(0, 4)
    return asc.filter((d) => d.asof.slice(0, 4) === y)
  }, [asc, range])

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

  // ── A 驱动图:A股=宽度 vs 阈值(宽度MA);美股=SPY波动 ──
  const chartRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!chartRef.current || !data.length) return
    const chart = echarts.init(chartRef.current)
    const xs = data.map((d) => d.asof.slice(5))
    const main = data.map((d) => ((isCN ? d.breadth : d.spy_vol) ?? 0) * 100)
    const thr = isCN ? data.map((d) => (d.breadth_ma ?? 0) * 100) : []
    const series: any[] = [{
      name: isCN ? '市场宽度' : 'SPY年化波动', type: 'line', data: main, showSymbol: false, smooth: true,
      lineStyle: { color: '#e6c878', width: 2 }, areaStyle: { color: 'rgba(200,162,83,.10)' },
    }]
    if (isCN) series.push({
      name: '翻灯阈值(宽度MA)', type: 'line', data: thr, showSymbol: false, smooth: true,
      lineStyle: { color: '#7ba7b0', width: 1.5, type: 'dashed' },
    })
    chart.setOption({
      backgroundColor: 'transparent',
      grid: { left: 44, right: 16, top: 30, bottom: 26 },
      legend: { top: 2, textStyle: { color: '#b0a488', fontSize: 11 }, itemWidth: 18 },
      tooltip: {
        trigger: 'axis', backgroundColor: '#1f1913', borderColor: '#2c2418', textStyle: { color: '#f1e9da' },
        formatter: (ps: any) => {
          const i = ps[0].dataIndex; const d = data[i]
          return `<b>${d.asof}</b> <span style="color:${lvC(d.level)}">●</span>${LV[d.level]?.t}<br/>` +
            ps.map((p: any) => `${p.marker}${p.seriesName}: ${p.value.toFixed(1)}%`).join('<br/>') +
            `<br/>建议仓位 ${pctS(d.exposure)}`
        },
      },
      xAxis: {
        type: 'category', data: xs, axisLabel: { color: '#b0a488', fontSize: 10, interval: Math.max(0, Math.floor(xs.length / 10)) },
        axisLine: { lineStyle: { color: '#2c2418' } },
      },
      yAxis: {
        type: 'value', axisLabel: { formatter: '{value}%', color: '#b0a488', fontSize: 10 },
        splitLine: { lineStyle: { color: '#241d15' } },
      },
      series,
    })
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [data, isCN])

  // ── B 日历热力图:按月分组,每天一格 ──
  const byMonth = useMemo(() => {
    const m = new Map<string, RiskHistItem[]>()
    data.forEach((d) => { const k = d.asof.slice(0, 7); if (!m.has(k)) m.set(k, []); m.get(k)!.push(d) })
    return [...m.entries()]
  }, [data])

  // ── C 四信号分解:最新一天 + 各自近60天迷你走势 ──
  const last = data.length ? data[data.length - 1] : null
  const spark = (key: keyof RiskHistItem) => {
    const vs = data.slice(-60).map((d) => (d[key] as number) ?? 0)
    if (!vs.length) return ''
    const mx = Math.max(...vs), mn = Math.min(...vs), rg = mx - mn || 1
    const pts = vs.map((v, i) => `${(i / (vs.length - 1)) * 100},${28 - ((v - mn) / rg) * 24 - 2}`).join(' ')
    return pts
  }
  const signals = isCN && last ? [
    { name: '市场宽度', val: pctS(last.breadth), ok: (last.breadth ?? 0) > (last.breadth_ma ?? 1), hint: `>翻灯阈值 ${pctS(last.breadth_ma)} 才转强`, key: 'breadth' as const },
    { name: '微盘拥挤度', val: pctS(last.crowd), ok: (last.crowd ?? 0) <= 0.85, hint: '≤85% 不拥挤', key: 'crowd' as const },
    { name: '成交额体制', val: (last.amount_ratio ?? 0).toFixed(2), ok: (last.amount_ratio ?? 0) > 0.85, hint: '>0.85 流动性未枯竭', key: 'amount_ratio' as const },
    { name: '小盘背离', val: last.diverge ? '有⚠' : '无', ok: !last.diverge, hint: '无背离为佳', key: 'exposure' as const },
  ] : last ? [
    { name: 'SPY年化波动', val: pctS(last.spy_vol), ok: true, hint: '波动越低越可满仓', key: 'spy_vol' as const },
  ] : []

  return (
    <>
      <div className="rl-head">
        <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
          {onBack && <button className="ghost mini" onClick={onBack} title="返回策略信号">‹ 返回</button>}
          风险灯详情 <InfoDot text="市场级风险闸(Gate)的历史演变。A股看4维:宽度∧非拥挤∧成交额未枯竭∧非背离→绿/黄/红三档总仓位。这页看它这段时间怎么变、为什么。" />
        </h2>
        <div className="rl-ctrls">
          <div className="seg">
            <button className={isCN ? 'on' : ''} onClick={() => setMkt('cn')}>A股</button>
            <button className={!isCN ? 'on' : ''} onClick={() => setMkt('us')}>美股</button>
          </div>
          <div className="seg">
            {(['ytd', '90d', 'all'] as const).map((r) => (
              <button key={r} className={range === r ? 'on' : ''} onClick={() => setRange(r)}>{r === 'ytd' ? '今年' : r === '90d' ? '近90天' : '全部'}</button>
            ))}
          </div>
        </div>
      </div>

      {loading ? <div className="card">加载中…</div> : !data.length ? <div className="card muted">暂无历史数据</div> : <>
        {/* A 制度带 + 驱动图 + 统计 */}
        <div className="card">
          <div className="rl-ribbon" title="每格一个交易日,颜色=当日风险灯">
            {data.map((d) => <span key={d.asof} className="rl-seg" style={{ background: lvC(d.level) }} title={`${d.asof} ${LV[d.level]?.t}`} />)}
          </div>
          <div className="rl-ribbon-x muted">
            <span>{data[0].asof}</span><span>{data[data.length - 1].asof}</span>
          </div>
          <div ref={chartRef} style={{ height: 220, marginTop: 8 }} />
          <div className="rl-stats">
            <div className="rl-stat"><div className="muted">当前制度</div><div className="rl-big" style={{ color: lvC(stats.cur) }}>● {LV[stats.cur]?.t || '—'}</div></div>
            <div className="rl-stat"><div className="muted">已持续</div><div className="rl-big">{stats.streak} 个交易日</div></div>
            <div className="rl-stat"><div className="muted">{range === 'ytd' ? '今年' : range === '90d' ? '近90天' : '全部'}占比</div>
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

        {/* B 日历热力图 */}
        <div className="card">
          <h3>日历视图 <InfoDot text="每格一个交易日,颜色=当日风险灯。一眼看这段时间绿/黄/红怎么分布、有没有连续转向。" /></h3>
          <div className="rl-cal">
            {byMonth.map(([mon, days]) => (
              <div key={mon} className="rl-cal-row">
                <span className="rl-cal-mon muted">{mon}</span>
                <div className="rl-cal-days">
                  {days.map((d) => <span key={d.asof} className="rl-cal-cell" style={{ background: lvC(d.level) }} title={`${d.asof} ${LV[d.level]?.t} · ${isCN ? '宽度' + pctS(d.breadth) : '波动' + pctS(d.spy_vol)}`} />)}
                </div>
              </div>
            ))}
          </div>
          <div className="rl-legend muted">
            <span><i style={{ background: 'var(--up)' }} />绿·满仓</span>
            <span><i style={{ background: 'var(--gold)' }} />黄·半仓</span>
            <span><i style={{ background: 'var(--down)' }} />红·空仓</span>
          </div>
        </div>

        {/* C 四信号分解 */}
        <div className="card">
          <h3>信号分解 <InfoDot text={isCN ? '风险灯由4个子信号合成:全过=绿满仓,宽度on但成交额枯竭/背离=黄半仓,宽度弱或拥挤=红空仓。看当前每个信号卡在哪。' : '美股风险灯看大盘波动目标。'} /> <span className="muted" style={{ fontWeight: 400 }}>· {last?.asof}</span></h3>
          <div className="rl-sigs">
            {signals.map((s) => (
              <div key={s.name} className="rl-sig">
                <span className="rl-sig-name">{s.name}</span>
                <svg className="rl-sig-spark" viewBox="0 0 100 28" preserveAspectRatio="none"><polyline points={spark(s.key)} fill="none" stroke={s.ok ? 'var(--up)' : 'var(--down)'} strokeWidth="1.5" /></svg>
                <span className="rl-sig-val" style={{ color: s.ok ? 'var(--up)' : 'var(--down)' }}>{s.val} {s.ok ? '✓' : '⚠'}</span>
                <span className="rl-sig-hint muted">{s.hint}</span>
              </div>
            ))}
          </div>
        </div>
      </>}
    </>
  )
}
