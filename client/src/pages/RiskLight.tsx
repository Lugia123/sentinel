import { useEffect, useMemo, useState } from 'react'
import { fetchRiskHistory, type RiskHistItem, type Market } from '../api'
import { InfoDot } from '../ui'
import RiskRibbon, { LV, lvC, pctS, filterRange, type RLRange } from '../components/RiskRibbon'
import PriceRegimeChart from '../components/PriceRegimeChart'

// 风险灯详情页:A 制度带+驱动图(复用 RiskRibbon)/ B 日历热力图 / C 四信号分解。市场切换 + 时间范围。
export default function RiskLight({ initialMarket = 'cn', onBack }: { initialMarket?: Market; onBack?: () => void }) {
  const [mkt, setMkt] = useState<Market>(initialMarket)
  const [range, setRange] = useState<RLRange>('ytd')
  const [raw, setRaw] = useState<RiskHistItem[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    setLoading(true)
    fetchRiskHistory(mkt).then((d) => { setRaw(d); setLoading(false) }).catch(() => setLoading(false))
  }, [mkt])

  const isCN = mkt === 'cn'
  const asc = useMemo(() => [...raw].sort((a, b) => a.asof.localeCompare(b.asof)), [raw])
  const data = useMemo(() => filterRange(asc, range), [asc, range])

  // B 日历热力图:按月分组
  const byMonth = useMemo(() => {
    const m = new Map<string, RiskHistItem[]>()
    data.forEach((d) => { const k = d.asof.slice(0, 7); if (!m.has(k)) m.set(k, []); m.get(k)!.push(d) })
    return [...m.entries()]
  }, [data])

  // C 四信号分解:最新一天 + 近60天迷你走势
  const last = data.length ? data[data.length - 1] : null
  const spark = (key: keyof RiskHistItem) => {
    const vs = data.slice(-60).map((d) => (d[key] as number) ?? 0)
    if (!vs.length) return ''
    const mx = Math.max(...vs), mn = Math.min(...vs), rg = mx - mn || 1
    return vs.map((v, i) => `${(i / (vs.length - 1)) * 100},${28 - ((v - mn) / rg) * 24 - 2}`).join(' ')
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
        {/* A 制度带 + 驱动图 + 统计(复用组件) */}
        <RiskRibbon market={mkt} range={range} rawData={asc} />

        {/* 灯 vs 走势对照(制度带 + 归一价格线 + 暴露 + 归因) */}
        <PriceRegimeChart market={mkt} regime={data} />

        <div className="row rl-bc">
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
        </div>
      </>}
    </>
  )
}
