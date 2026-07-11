import { useEffect, useState } from 'react'
import { fetchPnL, savePositions, type Market } from '../api'
import type { Position, PnLResult } from '../types'
import { pct2, InfoDot } from '../ui'

export default function Positions({ market = 'us' }: { market?: Market }) {
  const isCN = market === 'cn'
  const CUR = isCN ? '¥' : '$'
  const money = (x: number) => `${CUR}${x.toLocaleString('en-US', { maximumFractionDigits: 2 })}`
  const [data, setData] = useState<PnLResult | null>(null)
  const [rows, setRows] = useState<Position[]>([])
  const [err, setErr] = useState('')
  const [nt, setNt] = useState(''); const [ns, setNs] = useState(''); const [nc, setNc] = useState('')

  const load = () => fetchPnL().then((d) => { setData(d); setRows((d.positions || []).map((p) => ({ ticker: p.ticker, shares: p.shares, cost: p.cost }))) }).catch((e) => setErr(String(e.message || e)))
  useEffect(() => { setData(null); setRows([]); setErr(''); load() }, [market]) // 切市场重载(两市场持仓各自独立)

  const add = () => {
    if (!nt || !ns || !nc) return
    const tk = isCN ? nt.trim().toLowerCase() : nt.trim().toUpperCase() // A股代码小写(sh.600000),美股大写
    setRows([...rows, { ticker: tk, shares: +ns, cost: +nc }]); setNt(''); setNs(''); setNc('')
  }
  const del = (i: number) => setRows(rows.filter((_, j) => j !== i))
  const save = async () => { setErr(''); try { await savePositions(rows); await load() } catch (e: any) { setErr(String(e.message || e)) } }

  const s = data?.summary
  return (
    <>
      <div className="hint">
        📒 在这里录入<b>你实际买了的股票</b>（代码、股数、每股成本），系统按最新收盘价帮你算<b>浮动盈亏</b>。
        这只是记账，和上面的策略建议是两回事。{isCN ? '当前是 A股 持仓账本(与美股账本各自独立)。' : '当前是 美股 持仓账本(与A股账本各自独立)。'}
      </div>
      {s && <div className="row">
        <div className="card"><div className="muted">总市值 <InfoDot text="你持仓按最新收盘价的市场价值。" /></div><div className="big">{money(s.market_value)}</div><div className="muted">收盘价截至 {data!.asof}</div></div>
        <div className="card"><div className="muted">总成本</div><div className="big">{money(s.cost_value)}</div></div>
        <div className="card"><div className="muted">浮动盈亏 <InfoDot text="市值 − 成本。绿=赚,红=亏。只算“账面”,没卖不算真落袋。" /></div><div className={`big ${s.pnl >= 0 ? 'up' : 'down'}`}>{s.pnl >= 0 ? '+' : ''}{money(s.pnl)}</div><div className={s.pnl >= 0 ? 'up' : 'down'}>{pct2(s.pnl_pct)}</div></div>
      </div>}

      <div className="card">
        <h3>录入持仓</h3>
        <div className="pos-add">
          <input placeholder={isCN ? '代码 如 sh.600000' : '代码 如 AAPL'} value={nt} onChange={(e) => setNt(e.target.value)} />
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
                const p = (data?.positions || []).find((x) => x.ticker === r.ticker && x.shares === r.shares)
                return (<tr key={i}>
                  <td><b>{r.ticker}</b></td><td>{r.shares}</td><td>{CUR}{r.cost}</td>
                  <td>{p?.priced ? `${CUR}${p.price}` : <span className="muted">无价</span>}</td>
                  <td>{p ? money(p.market_value) : '—'}</td>
                  <td className={p && p.pnl >= 0 ? 'up' : 'down'}>{p ? `${p.pnl >= 0 ? '+' : ''}${money(p.pnl)}` : '—'}</td>
                  <td className={p && p.pnl >= 0 ? 'up' : 'down'}>{p ? pct2(p.pnl_pct) : '—'}</td>
                  <td><button className="ghost" onClick={() => del(i)} style={{ padding: '2px 8px' }}>删</button></td>
                </tr>)
              })}
              {rows.length === 0 && <tr><td colSpan={8} className="muted" style={{ textAlign: 'center', padding: 20 }}>还没录入。上方填代码/股数/成本 → “保存并计算”</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="muted" style={{ marginTop: 8 }}>提示：无价=该代码不在系统数据池里(暂无收盘价),盈亏不计入合计。</div>
      </div>
    </>
  )
}
