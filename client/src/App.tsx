import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchSnapshot, runEngine, fetchVersion, fetchPnL, savePositions } from './api'
import type { Snapshot, Holding, Position, PnLResult } from './types'

const pct = (x: number) => `${(x * 100).toFixed(1)}%`
const usd = (x: number) => `$${x.toLocaleString('en-US', { maximumFractionDigits: 2 })}`
const gradeClass = (g: number) => (g >= 2 ? 'g-3' : g >= 0 ? 'g-1' : g === -1 ? 'g-neg1' : 'g-neg2')
const actionColor = (a: string) => (a.includes('清仓') ? 'var(--down)' : a.includes('减') ? 'var(--warn)' : 'var(--up)')

export default function App() {
  const [snap, setSnap] = useState<Snapshot | null>(null)
  const [ver, setVer] = useState('dev')
  const [err, setErr] = useState('')
  const [running, setRunning] = useState(false)
  const [tab, setTab] = useState<'signals' | 'positions'>('signals')

  const load = () => fetchSnapshot().then(setSnap).catch((e) => setErr(String(e.message || e)))
  useEffect(() => { load(); fetchVersion().then((v) => setVer(v.version)) }, [])

  const doRun = async () => {
    setRunning(true); setErr('')
    try { await runEngine(true); await load() } catch (e: any) { setErr(String(e.message || e)) }
    setRunning(false)
  }

  return (
    <div className="wrap">
      <div className="header">
        <div>
          <div className="title">Sentinel<span className="ver">{ver}</span></div>
          <div className="sub">{snap ? `数据截至 ${snap.asof} 收盘 · 资金池 ${usd(snap.capital)}` : '美股策略决策支持'}</div>
        </div>
        <button onClick={doRun} disabled={running}>{running ? '引擎运行中…' : '刷新快照'}</button>
      </div>

      <div className="tabs">
        <button className={tab === 'signals' ? 'active' : ''} onClick={() => setTab('signals')}>策略信号</button>
        <button className={tab === 'positions' ? 'active' : ''} onClick={() => setTab('positions')}>我的持仓</button>
      </div>

      {err && <div className="card" style={{ color: 'var(--down)' }}>{err}
        <div style={{ marginTop: 8 }}><button onClick={doRun} disabled={running}>{running ? '运行中…' : '运行引擎生成快照'}</button></div></div>}

      {tab === 'signals' && snap && <Signals snap={snap} />}
      {tab === 'positions' && <Positions />}

      <div className="disc">
        研究工具,非投资建议。档位=趋势状态(松·只减防御跟法,只减不追涨);概率带=波动缩放经验分布(校准,非方向预言);
        风险灯=波动目标体制闸。方向不可预测,本系统为决策支持,手动执行,盈亏自负。
      </div>
    </div>
  )
}

function Signals({ snap }: { snap: Snapshot }) {
  const chartRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!chartRef.current) return
    const chart = echarts.init(chartRef.current, undefined, { renderer: 'canvas' })
    const hs = snap.holdings
    const bands = hs.map((h, i) => ({ value: [i, h.prob['h20'].band70[0] * 100, h.prob['h20'].band70[1] * 100, h.prob['h20'].median * 100], grade: h.grade }))
    chart.setOption({
      backgroundColor: 'transparent',
      grid: { left: 55, right: 20, top: 34, bottom: 44 },
      title: { text: '未来 20 日收益概率带(70% 区间 + 中位)', left: 'center', textStyle: { fontSize: 13, color: '#aeb9c9' } },
      tooltip: {
        backgroundColor: '#1b2433', borderColor: '#26303f', textStyle: { color: '#e6edf6' },
        formatter: (p: any) => {
          const h = hs[p.data.value[0]]; const b = h.prob['h20']
          return `<b>${h.ticker}</b><br/>中位 ${pct(b.median)}<br/>70%区间 ${pct(b.band70[0])} ~ ${pct(b.band70[1])}<br/>止损 $${b.stop} / 目标 $${b.target}<br/>到目标 ${pct(b.p_hit_target)} · 触止损 ${pct(b.p_hit_stop)}`
        },
      },
      xAxis: { type: 'category', data: hs.map((h) => h.ticker), axisLabel: { color: '#6b7787' }, axisLine: { lineStyle: { color: '#26303f' } } },
      yAxis: { type: 'value', axisLabel: { formatter: '{value}%', color: '#6b7787' }, splitLine: { lineStyle: { color: '#26303f' } } },
      series: [{
        type: 'custom',
        renderItem: (params: any, api: any) => {
          const idx = api.value(0)
          const lo = api.coord([idx, api.value(1)]); const hi = api.coord([idx, api.value(2)]); const med = api.coord([idx, api.value(3)])
          const g = bands[params.dataIndex].grade
          const color = g >= 2 ? '#2ecc9b' : g >= 0 ? '#4d9dff' : g === -1 ? '#f5a623' : '#ff5c6c'
          const w = 14
          return { type: 'group', children: [
            { type: 'rect', shape: { x: lo[0] - w / 2, y: hi[1], width: w, height: lo[1] - hi[1] }, style: { fill: color, opacity: 0.35 } },
            { type: 'line', shape: { x1: med[0] - w / 2, y1: med[1], x2: med[0] + w / 2, y2: med[1] }, style: { stroke: color, lineWidth: 2 } },
          ] }
        },
        data: bands,
      }],
    })
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [snap])

  const rl = snap.risk_light
  return (
    <>
      <div className="row">
        <div className="card">
          <div className="muted">风险灯(波动目标闸)</div>
          <div className="big"><span className={`light ${rl.level}`} />{rl.note}</div>
          <div className="muted">SPY 年化波动 {pct(rl.spy_vol)} · 建议总仓位 {pct(rl.exposure)}</div>
        </div>
        <div className="card">
          <div className="muted">组合(策略建议)</div>
          <div className="big">{snap.portfolio.n_holdings} 只</div>
          <div className="muted">总仓位 {pct(snap.portfolio.gross_exposure)} · 现金 {pct(snap.portfolio.cash_pct)}</div>
        </div>
      </div>
      <div className="card">
        <h3>策略建议持仓 · 档位 · 到价概率</h3>
        <div className="tbl-scroll">
          <table>
            <thead><tr>
              <th>标的</th><th>腿</th><th>现价</th><th>目标股数</th><th>目标市值</th>
              <th>档位</th><th>动作</th><th>20日中位</th><th>70%区间</th><th>止损/目标</th><th>到目标/触止损</th>
            </tr></thead>
            <tbody>
              {snap.holdings.map((h: Holding) => {
                const b = h.prob['h20']
                return (<tr key={h.ticker}>
                  <td><b>{h.ticker}</b></td><td>{h.sleeve}</td><td>${h.price}</td>
                  <td>{h.target_shares}</td><td>${h.target_value}</td>
                  <td><span className={`pill ${gradeClass(h.grade)}`}>{h.grade >= 0 ? `+${h.grade}` : h.grade} {h.grade_label}</span></td>
                  <td style={{ color: actionColor(h.action), fontWeight: 600 }}>{h.action}</td>
                  <td className={b.median >= 0 ? 'up' : 'down'}>{pct(b.median)}</td>
                  <td className="muted">{pct(b.band70[0])} ~ {pct(b.band70[1])}</td>
                  <td>${b.stop} / ${b.target}</td>
                  <td>{pct(b.p_hit_target)} / {pct(b.p_hit_stop)}</td>
                </tr>)
              })}
            </tbody>
          </table>
        </div>
      </div>
      <div className="card"><div ref={chartRef} style={{ height: 320 }} /></div>
    </>
  )
}

function Positions() {
  const [data, setData] = useState<PnLResult | null>(null)
  const [rows, setRows] = useState<Position[]>([])
  const [err, setErr] = useState('')
  const [nt, setNt] = useState(''); const [ns, setNs] = useState(''); const [nc, setNc] = useState('')

  const load = () => fetchPnL().then((d) => { setData(d); setRows(d.positions.map((p) => ({ ticker: p.ticker, shares: p.shares, cost: p.cost }))) }).catch((e) => setErr(String(e.message || e)))
  useEffect(() => { load() }, [])

  const add = () => {
    if (!nt || !ns || !nc) return
    setRows([...rows, { ticker: nt.toUpperCase(), shares: +ns, cost: +nc }]); setNt(''); setNs(''); setNc('')
  }
  const del = (i: number) => setRows(rows.filter((_, j) => j !== i))
  const save = async () => { setErr(''); try { await savePositions(rows); await load() } catch (e: any) { setErr(String(e.message || e)) } }

  const s = data?.summary
  return (
    <>
      {s && <div className="row">
        <div className="card"><div className="muted">总市值</div><div className="big">{usd(s.market_value)}</div><div className="muted">as-of {data!.asof} 收盘</div></div>
        <div className="card"><div className="muted">总成本</div><div className="big">{usd(s.cost_value)}</div></div>
        <div className="card"><div className="muted">浮动盈亏</div><div className={`big ${s.pnl >= 0 ? 'up' : 'down'}`}>{s.pnl >= 0 ? '+' : ''}{usd(s.pnl)}</div><div className={s.pnl >= 0 ? 'up' : 'down'}>{s.pnl >= 0 ? '+' : ''}{pct(s.pnl_pct)}</div></div>
      </div>}

      <div className="card">
        <h3>录入持仓(手动,按 as-of 收盘价算盈亏)</h3>
        <div className="pos-add">
          <input placeholder="代码 AAPL" value={nt} onChange={(e) => setNt(e.target.value)} />
          <input placeholder="股数" value={ns} onChange={(e) => setNs(e.target.value)} />
          <input placeholder="每股成本" value={nc} onChange={(e) => setNc(e.target.value)} />
          <button onClick={add}>+ 添加</button>
          <button className="ghost" onClick={save}>保存并计算</button>
        </div>
        {err && <div className="down" style={{ fontSize: 13, marginBottom: 8 }}>{err}</div>}
        <div className="tbl-scroll">
          <table>
            <thead><tr><th>标的</th><th>股数</th><th>成本</th><th>现价</th><th>市值</th><th>盈亏</th><th>盈亏%</th><th></th></tr></thead>
            <tbody>
              {rows.map((r, i) => {
                const p = data?.positions.find((x) => x.ticker === r.ticker && x.shares === r.shares)
                return (<tr key={i}>
                  <td><b>{r.ticker}</b></td><td>{r.shares}</td><td>${r.cost}</td>
                  <td>{p?.priced ? `$${p.price}` : <span className="muted">无价</span>}</td>
                  <td>{p ? usd(p.market_value) : '—'}</td>
                  <td className={p && p.pnl >= 0 ? 'up' : 'down'}>{p ? `${p.pnl >= 0 ? '+' : ''}${usd(p.pnl)}` : '—'}</td>
                  <td className={p && p.pnl >= 0 ? 'up' : 'down'}>{p ? `${p.pnl >= 0 ? '+' : ''}${pct(p.pnl_pct)}` : '—'}</td>
                  <td><button className="ghost" onClick={() => del(i)} style={{ padding: '2px 8px' }}>删</button></td>
                </tr>)
              })}
              {rows.length === 0 && <tr><td colSpan={8} className="muted" style={{ textAlign: 'center', padding: 20 }}>暂无持仓,上方添加后点"保存并计算"</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
