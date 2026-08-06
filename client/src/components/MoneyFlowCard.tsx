import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchMoneyflow, type MoneyFlow } from '../api'
import { InfoDot, riseColor, fallColor } from '../ui'

// A股个股【资金流·量能】展示卡(纯展示,不进策略)。颜色走 --rise/--fall,自动跟随用户涨跌配色。
// 结构:头条(主力5日净流入+量价资状态) → 主力vs散户分歧条 → 资金×价格时间线 → 四单结构 → 量能。
const yi = (x: number | null | undefined, dp = 2) => (x == null ? '—' : `${x >= 0 ? '+' : ''}${x.toFixed(dp)}亿`)
const cls = (x: number | null | undefined) => (x == null ? 'muted' : x > 0 ? 'up' : x < 0 ? 'down' : 'muted')

export default function MoneyFlowCard({ ticker }: { ticker: string }) {
  const [mf, setMf] = useState<MoneyFlow | null>(null)
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(40)
  const chartRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let alive = true
    setLoading(true)
    fetchMoneyflow(ticker, days).then((d) => { if (alive) { setMf(d); setLoading(false) } })
    return () => { alive = false }
  }, [ticker, days])

  // 资金 × 价格 时间线:柱=每日主力净额(涨色入/跌色出),线=收盘价(次轴),背离区高亮
  useEffect(() => {
    if (!chartRef.current || !mf || !mf.summary.has_moneyflow) return
    const chart = echarts.init(chartRef.current)
    const p = mf.points
    const dates = p.map((x) => x.date.slice(5))
    const rise = riseColor(), fall = fallColor()
    const mainBars = p.map((x) => ({ value: x.main, itemStyle: { color: x.main == null ? '#555' : x.main >= 0 ? rise : fall } }))
    const price = p.map((x) => x.close)
    // 背离区:标记最后6日
    const mark = mf.summary.divergence
      ? { markArea: { silent: true, itemStyle: { color: 'rgba(207,111,93,0.08)' }, data: [[{ xAxis: dates[Math.max(0, dates.length - 6)] }, { xAxis: dates[dates.length - 1] }]] } }
      : {}
    chart.setOption({
      backgroundColor: 'transparent', grid: { left: 46, right: 46, top: 24, bottom: 24 },
      legend: { data: ['主力净额', '收盘价'], textStyle: { color: '#bcae97' }, top: 0, itemWidth: 12, itemHeight: 8 },
      tooltip: {
        trigger: 'axis', backgroundColor: '#1f1913', borderColor: '#2c2418', textStyle: { color: '#f1e9da' },
        formatter: (ps: any) => {
          const i = ps[0].dataIndex, x = p[i]
          const g = (v: number | null) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}亿`)
          return `${x.date}<br/>主力 ${g(x.main)} · 散户 ${g(x.retail)}<br/>量比 ${x.vol_ratio ?? '—'} · 换手 ${x.turn ?? '—'}% · 涨跌 ${x.pct == null ? '—' : x.pct + '%'}<br/>收盘 ¥${x.close ?? '—'}`
        },
      },
      xAxis: { type: 'category', data: dates, axisLabel: { color: '#b0a488', fontSize: 10 }, axisLine: { lineStyle: { color: '#2c2418' } } },
      yAxis: [
        { type: 'value', name: '亿', nameTextStyle: { color: '#8a7e66', fontSize: 10 }, axisLabel: { color: '#b0a488', fontSize: 10 }, splitLine: { lineStyle: { color: '#241d15' } } },
        { type: 'value', scale: true, axisLabel: { color: '#8a7e66', fontSize: 10 }, splitLine: { show: false } },
      ],
      series: [
        { name: '主力净额', type: 'bar', data: mainBars, barMaxWidth: 12, ...mark },
        { name: '收盘价', type: 'line', yAxisIndex: 1, data: price, showSymbol: false, lineStyle: { color: '#e6c878', width: 1.8 }, z: 3 },
      ],
    })
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [mf])

  if (loading) return <div className="card"><h3>资金流 · 量能</h3><div className="muted">加载中…</div></div>
  if (!mf) return null // 非A股或数据完全不可用:不渲染

  const s = mf.summary
  const last = mf.points[mf.points.length - 1]
  const mainT = last?.main ?? null, retailT = last?.retail ?? null
  // 主力vs散户 今日分歧判定
  let dvg = '资金观望'
  if (mainT != null && retailT != null) {
    if (mainT > 0 && retailT < 0) dvg = '主力吸筹（主进散出）'
    else if (mainT < 0 && retailT > 0) dvg = '派发 / 散户接盘'
    else if (mainT > 0 && retailT > 0) dvg = '一致流入'
    else if (mainT < 0 && retailT < 0) dvg = '一致流出'
  }
  const aMain = Math.abs(mainT ?? 0), aRet = Math.abs(retailT ?? 0), tot = aMain + aRet || 1
  const bk = s.buckets_today
  const bkMax = Math.max(...['elg', 'lg', 'md', 'sm'].map((k) => Math.abs((bk as any)[k] ?? 0)), 0.01)
  const consecTxt = s.consec > 0 ? `连续流入 ${s.consec} 日` : s.consec < 0 ? `连续流出 ${-s.consec} 日` : '—'
  const divWarn = s.divergence === 'top'

  return (
    <div className="card">
      <div className="mf-head">
        <h3>资金流 · 量能 <InfoDot text="主力=超大单+大单(≥30万),散户=中+小单;金额亿元。颜色随你的涨跌配色。连续多日净流入比单日更有参考;价与资金背离时高亮预警。纯展示,不进策略。数据:tushare+本地量能,非投资建议。" /></h3>
        <div className="mf-win">{[20, 40, 60].map((d) => <button key={d} className={days === d ? 'on' : ''} onClick={() => setDays(d)}>{d}日</button>)}</div>
      </div>

      {!s.has_moneyflow && <div className="muted mf-degrade">⚠ 资金流接口暂不可用,仅显示量能(下方)。</div>}

      {s.has_moneyflow && <>
        {/* 头条 */}
        <div className="mf-hero">
          <div className="mf-hero-main">
            <div className="mf-lbl">主力净流入 · 近5日累计</div>
            <div className={`mf-big ${cls(s.main_5d)}`}>{yi(s.main_5d)} {s.main_5d != null && (s.main_5d >= 0 ? '↑' : '↓')}</div>
          </div>
          <div className={`mf-state ${divWarn ? 'warn' : s.tone}`}>{divWarn ? '⚠ ' : ''}{s.state}</div>
        </div>
        <div className="mf-kv">
          <div>今日主力<b className={cls(mainT)}>{yi(mainT)}</b></div>
          <div>20日累计<b className={cls(s.main_20d)}>{yi(s.main_20d)}</b></div>
          <div>{s.consec >= 0 ? '连续流入' : '连续流出'}<b>{Math.abs(s.consec)} 日</b></div>
          <div>散户近5日<b className={cls(s.retail_5d)}>{yi(s.retail_5d)}</b></div>
        </div>

        {/* 主力 vs 散户 分歧条 */}
        <div className="mf-sub"><span>主力 vs 散户 · 今日净额方向</span><span className="mf-tag">{dvg}</span></div>
        <div className="mf-dvg">
          <div className="seg" style={{ width: `${(aMain / tot) * 100}%`, background: (mainT ?? 0) >= 0 ? 'var(--rise)' : 'var(--fall)' }}>主力 {yi(mainT)}</div>
          <div className="seg lite" style={{ width: `${(aRet / tot) * 100}%`, background: (retailT ?? 0) >= 0 ? 'var(--rise-bg)' : 'var(--fall-bg)' }}>散户 {yi(retailT)}</div>
        </div>

        {/* 资金 × 价格 时间线 */}
        <div className="mf-sub"><span>资金 × 价格 · 近{days}日（柱=主力净额，线=收盘）</span>{s.divergence === 'top' && <span className="mf-tag warn">顶背离：价升·钱出</span>}{s.divergence === 'bottom' && <span className="mf-tag">价跌·钱进（或吸筹）</span>}</div>
        <div ref={chartRef} style={{ height: 200 }} />

        {/* 四单结构 */}
        <div className="mf-sub"><span>四单结构 · 今日净额</span></div>
        <div className="mf-buckets">
          {[['超大单', 'elg'], ['大单', 'lg'], ['中单', 'md'], ['小单', 'sm']].map(([name, k]) => {
            const v = (bk as any)[k] as number | null
            const w = v == null ? 0 : (Math.abs(v) / bkMax) * 46
            return <div className="bk" key={k}>
              <span className="bk-name">{name}</span>
              <div className="bk-track"><div className="bk-fill" style={{ [(v ?? 0) >= 0 ? 'left' : 'right']: '50%', width: `${w}%`, background: (v ?? 0) >= 0 ? 'var(--rise)' : 'var(--fall)' } as any} /></div>
              <span className={`bk-amt ${cls(v)}`}>{yi(v)}</span>
            </div>
          })}
        </div>
        <div className="mf-axis">← 流出　·　中线=0　·　流入 →</div>
      </>}

      {/* 量能(不依赖资金流接口,始终显示)*/}
      <div className="mf-sub" style={{ marginTop: 14 }}><span>量能 · 量价配合</span></div>
      <div className="mf-vol">
        <div>量比（今/20日均）<b>{s.vol_ratio ?? '—'}</b></div>
        <div>换手率<b>{s.turn == null ? '—' : s.turn + '%'}</b></div>
        <div>今日涨跌<b className={cls(s.pct)}>{s.pct == null ? '—' : (s.pct >= 0 ? '+' : '') + s.pct + '%'}</b></div>
      </div>
    </div>
  )
}
