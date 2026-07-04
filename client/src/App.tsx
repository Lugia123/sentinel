import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchSnapshot, runEngine } from './api'
import type { Snapshot, Holding } from './types'

const pct = (x: number) => `${(x * 100).toFixed(1)}%`
const gradeClass = (g: number) =>
  g >= 2 ? 'g-3' : g === 1 || g === 0 ? 'g-1' : g === -1 ? 'g-neg1' : 'g-neg2'
const actionColor = (a: string) =>
  a.includes('清仓') ? 'var(--down)' : a.includes('减') ? 'var(--warn)' : 'var(--up)'

export default function App() {
  const [snap, setSnap] = useState<Snapshot | null>(null)
  const [err, setErr] = useState<string>('')
  const [running, setRunning] = useState(false)
  const chartRef = useRef<HTMLDivElement>(null)

  const load = () => fetchSnapshot().then(setSnap).catch((e) => setErr(String(e.message || e)))
  useEffect(() => { load() }, [])

  useEffect(() => {
    if (!snap || !chartRef.current) return
    const chart = echarts.init(chartRef.current)
    const hs = snap.holdings
    const cats = hs.map((h) => h.ticker)
    // 20 日 70% 收益带 [低, 高] + 中位 —— custom 画区间条
    const bands = hs.map((h, i) => {
      const p = h.prob['h20']
      return { value: [i, p.band70[0] * 100, p.band70[1] * 100, p.median * 100], grade: h.grade }
    })
    chart.setOption({
      grid: { left: 60, right: 20, top: 30, bottom: 40 },
      title: { text: '未来 20 日收益概率带(70% 区间 + 中位)', left: 'center', textStyle: { fontSize: 13, color: '#3f4d68' } },
      tooltip: {
        formatter: (p: any) => {
          const h = hs[p.data.value[0]]
          const b = h.prob['h20']
          return `<b>${h.ticker}</b><br/>中位 ${pct(b.median)}<br/>70%区间 ${pct(b.band70[0])} ~ ${pct(b.band70[1])}<br/>止损 $${b.stop} / 目标 $${b.target}<br/>到目标 ${pct(b.p_hit_target)} · 触止损 ${pct(b.p_hit_stop)}`
        },
      },
      xAxis: { type: 'category', data: cats, axisLabel: { color: '#5c6a83' } },
      yAxis: { type: 'value', axisLabel: { formatter: '{value}%', color: '#5c6a83' }, splitLine: { lineStyle: { color: '#e9eef6' } } },
      series: [{
        type: 'custom',
        renderItem: (params: any, api: any) => {
          const idx = api.value(0)
          const lo = api.coord([idx, api.value(1)])
          const hi = api.coord([idx, api.value(2)])
          const med = api.coord([idx, api.value(3)])
          const g = bands[params.dataIndex].grade
          const color = g >= 2 ? '#0ca678' : g >= 0 ? '#2f80ed' : g === -1 ? '#e08a1e' : '#e23d34'
          const w = 14
          return {
            type: 'group',
            children: [
              { type: 'rect', shape: { x: lo[0] - w / 2, y: hi[1], width: w, height: lo[1] - hi[1] }, style: { fill: color, opacity: 0.35 } },
              { type: 'line', shape: { x1: med[0] - w / 2, y1: med[1], x2: med[0] + w / 2, y2: med[1] }, style: { stroke: color, lineWidth: 2 } },
            ],
          }
        },
        data: bands,
      }],
    })
    const onResize = () => chart.resize()
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('resize', onResize); chart.dispose() }
  }, [snap])

  const doRun = async () => {
    setRunning(true); setErr('')
    try { await runEngine(true); await load() } catch (e: any) { setErr(String(e.message || e)) }
    setRunning(false)
  }

  if (err) return <div className="wrap"><div className="card" style={{ color: 'var(--down)' }}>{err}<br /><button onClick={doRun} disabled={running} style={{ marginTop: 10 }}>{running ? '引擎运行中…' : '运行引擎生成快照'}</button></div></div>
  if (!snap) return <div className="wrap"><div className="card">加载中…</div></div>

  const rl = snap.risk_light
  return (
    <div className="wrap">
      <div className="header">
        <div>
          <div className="title">Sentinel · 美股策略决策支持</div>
          <div className="sub">数据截至 {snap.asof} 收盘 · 运行于 {snap.generated_at} · 资金池 ${snap.capital}</div>
        </div>
        <button onClick={doRun} disabled={running}>{running ? '引擎运行中…' : '刷新快照'}</button>
      </div>

      <div className="row">
        <div className="card">
          <div className="muted">风险灯(波动目标闸)</div>
          <div className="big"><span className={`light ${rl.level}`} />{rl.note}</div>
          <div className="muted">SPY 年化波动 {pct(rl.spy_vol)} · 建议总仓位 {pct(rl.exposure)}</div>
        </div>
        <div className="card">
          <div className="muted">组合</div>
          <div className="big">{snap.portfolio.n_holdings} 只</div>
          <div className="muted">总仓位 {pct(snap.portfolio.gross_exposure)} · 现金 {pct(snap.portfolio.cash_pct)}</div>
        </div>
      </div>

      <div className="card">
        <div className="tbl-scroll">
          <table>
            <thead>
              <tr>
                <th>标的</th><th>腿</th><th>现价</th><th>目标股数</th><th>目标市值</th>
                <th>档位</th><th>动作</th><th>20日中位</th><th>70%区间</th><th>止损/目标</th><th>到目标/触止损</th>
              </tr>
            </thead>
            <tbody>
              {snap.holdings.map((h: Holding) => {
                const b = h.prob['h20']
                return (
                  <tr key={h.ticker}>
                    <td><b>{h.ticker}</b></td>
                    <td>{h.sleeve}</td>
                    <td>${h.price}</td>
                    <td>{h.target_shares}</td>
                    <td>${h.target_value}</td>
                    <td><span className={`pill ${gradeClass(h.grade)}`}>{h.grade >= 0 ? `+${h.grade}` : h.grade} {h.grade_label}</span></td>
                    <td style={{ color: actionColor(h.action), fontWeight: 600 }}>{h.action}</td>
                    <td style={{ color: b.median >= 0 ? 'var(--up)' : 'var(--down)' }}>{pct(b.median)}</td>
                    <td className="muted">{pct(b.band70[0])} ~ {pct(b.band70[1])}</td>
                    <td>${b.stop} / ${b.target}</td>
                    <td>{pct(b.p_hit_target)} / {pct(b.p_hit_stop)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card"><div ref={chartRef} style={{ height: 320 }} /></div>

      <div className="disc">
        {snap.disclaimer}。档位=趋势状态(松·只减防御跟法,只减不追涨);概率带=波动缩放经验分布(校准,非方向预言);
        风险灯=波动目标体制闸。方向不可预测,本系统为决策支持,手动执行,盈亏自负。
      </div>
    </div>
  )
}
