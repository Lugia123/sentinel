import { useState } from 'react'
import Modal from './Modal'
import { fetchAIAllocate, getMarket, type AllocItem, type TickerMeta } from '../api'
import type { Holding } from '../types'

type Mode = 'even' | 'risk_parity' | 'ai'
const r2 = (x: number) => Math.round(x * 100) / 100
const r3 = (x: number) => Math.round(x * 1000) / 1000
const r4 = (x: number) => Math.round(x * 10000) / 10000

// 建议股数分配工具:选股票 × 分配方式(均分/风险平价/AI) → 算出各股目标股数。
// 纯工具:不回写列表;资金池可在此录入。A股:一手=100股取整、¥ 计价。
export default function AllocateModal({ holdings, meta, capital: defaultCap, exposure, onClose }: {
  holdings: Holding[]
  meta: TickerMeta
  capital: number
  exposure: number // 风险灯建议总仓位(0-1)
  onClose: () => void
}) {
  const isCN = getMarket() === 'cn'
  const CUR = isCN ? '¥' : '$'
  const money = (x: number) => `${CUR}${x.toLocaleString('en-US', { maximumFractionDigits: 2 })}`
  const cnName = (tk: string) => meta[tk]?.cn || holdings.find((h) => h.ticker === tk)?.name || ''
  const [capital, setCapital] = useState(defaultCap)
  const [capText, setCapText] = useState(String(defaultCap))
  const [sel, setSel] = useState<Set<string>>(new Set(holdings.map((h) => h.ticker)))
  const [mode, setMode] = useState<Mode>('risk_parity')
  const [q, setQ] = useState('')
  const [result, setResult] = useState<AllocItem[] | null>(null)
  const [cash, setCash] = useState(0)
  const [note, setNote] = useState('')
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  const toggle = (tk: string) => setSel((s) => { const n = new Set(s); n.has(tk) ? n.delete(tk) : n.add(tk); return n })
  const filtered = holdings.filter((h) => {
    const s = q.trim().toLowerCase()
    if (!s) return true
    return h.ticker.toLowerCase().includes(s) || cnName(h.ticker).includes(q.trim())
  })
  const allOn = filtered.length > 0 && filtered.every((h) => sel.has(h.ticker))
  const selectAll = () => setSel((s) => { const n = new Set(s); filtered.forEach((h) => n.add(h.ticker)); return n })
  const clearAll = () => setSel((s) => { const n = new Set(s); filtered.forEach((h) => n.delete(h.ticker)); return n })
  const invert = () => setSel((s) => { const n = new Set(s); filtered.forEach((h) => (n.has(h.ticker) ? n.delete(h.ticker) : n.add(h.ticker))); return n })

  const applyCapText = () => { const v = parseFloat(capText); if (v >= 1) setCapital(v); else setCapText(String(capital)) }

  const compute = async () => {
    setErr(''); setResult(null)
    const chosen = holdings.filter((h) => sel.has(h.ticker))
    if (chosen.length === 0) { setErr('至少选一只股票'); return }
    if (mode === 'ai') {
      setLoading(true)
      try {
        const res = await fetchAIAllocate(chosen.map((h) => h.ticker), capital)
        setResult(res.allocations); setCash(res.cash_pct); setNote(res.note)
      } catch (e: any) { setErr(String(e.message || e)) }
      setLoading(false)
      return
    }
    let w: number[]
    if (mode === 'even') w = chosen.map(() => 1 / chosen.length)
    else {
      const inv = chosen.map((h) => 1 / Math.max(0.05, h.indicators?.vol_annual ?? 0.3))
      const s = inv.reduce((a, b) => a + b, 0); w = inv.map((x) => x / s)
    }
    const items: AllocItem[] = chosen.map((h, i) => {
      let shares = r3((capital * w[i] * exposure) / h.price)
      let value = r2(capital * w[i] * exposure)
      if (isCN) { // A股一手=100股,向下取整手;金额随实际股数重算
        shares = Math.floor((capital * w[i] * exposure) / h.price / 100) * 100
        value = r2(shares * h.price)
      }
      return { ticker: h.ticker, weight: isCN ? r4(value / capital) : r4(w[i] * exposure), shares, value, reason: '' }
    }).filter((it) => !isCN || it.shares > 0)
    setResult(items); setNote(''); setCash(r4(1 - items.reduce((a, b) => a + b.weight, 0)))
  }

  return (
    <Modal xwide title={<>⚖ 建议股数分配 <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>· 选股票 + 方式 → 算各股买多少(工具,不改列表)</span></>} onClose={onClose}>
      <div className="alloc-topbar">
        <div className="alloc-cap">
          <span className="muted">资金池 {CUR}</span>
          <input value={capText} onChange={(e) => setCapText(e.target.value.replace(/[^0-9.]/g, ''))}
            onBlur={applyCapText} onKeyDown={(e) => e.key === 'Enter' && applyCapText()} style={{ width: 110 }} />
        </div>
        <div className="alloc-modes">
          <button className={mode === 'even' ? 'active' : ''} onClick={() => setMode('even')}>均分</button>
          <button className={mode === 'risk_parity' ? 'active' : ''} onClick={() => setMode('risk_parity')}>风险平价</button>
          <button className={mode === 'ai' ? 'active' : ''} onClick={() => setMode('ai')}>🤖 AI 分配</button>
        </div>
        <button className="primary" onClick={compute} disabled={loading}>{loading ? 'AI 分配中…（约15秒）' : '计算分配'}</button>
      </div>
      {err && <div className="down" style={{ fontSize: 13, margin: '8px 0' }}>{err}</div>}

      <div className="alloc-grid">
        <div className="alloc-pick">
          <div className="alloc-sub">
            <span>选择股票 <span className="muted">({sel.size}/{holdings.length})</span></span>
            <span className="alloc-acts">
              <button className="linkbtn" onClick={selectAll}>全选</button>
              <button className="linkbtn" onClick={invert}>反选</button>
              <button className="linkbtn" onClick={clearAll}>清空</button>
            </span>
          </div>
          <input className="alloc-filter" placeholder="筛选:代码或中文名…" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="alloc-list">
            {filtered.map((h) => {
              const on = sel.has(h.ticker)
              return (
                <div key={h.ticker} className={`alloc-item ${on ? 'on' : ''}`} onClick={() => toggle(h.ticker)}>
                  <span className={`ck ${on ? 'ck-on' : ''}`}>{on ? '✓' : ''}</span>
                  <b>{h.ticker}</b><span className="ss-sub">{cnName(h.ticker)}</span>
                  <span className="alloc-g" data-g={h.grade >= 2 ? 'up' : h.grade >= -1 ? 'mid' : 'down'}>{h.grade >= 0 ? '+' : ''}{h.grade}</span>
                </div>
              )
            })}
            {filtered.length === 0 && <div className="muted" style={{ padding: 8 }}>无匹配</div>}
          </div>
        </div>
        <div className="alloc-res">
          <div className="alloc-sub"><span>分配结果</span></div>
          {!result && <div className="muted">选好股票和方式,点「计算分配」。<br />AI 分配会根据资金池+价+趋势+波动做取舍(不必全买)。</div>}
          {result && (
            <>
              {note && <div className="alloc-note">🤖 {note}</div>}
              <div className="tbl-scroll" style={{ maxHeight: 360 }}>
                <table>
                  <thead><tr><th>标的</th><th>权重</th><th>股数</th><th>金额</th>{mode === 'ai' && <th>理由</th>}</tr></thead>
                  <tbody>
                    {result.map((a) => (
                      <tr key={a.ticker}>
                        <td><b>{a.ticker}</b> <span className="ss-sub">{cnName(a.ticker)}</span></td>
                        <td>{(a.weight * 100).toFixed(1)}%</td>
                        <td className="gold">{a.shares}</td>
                        <td>{money(a.value)}</td>
                        {mode === 'ai' && <td className="muted" style={{ fontSize: 12 }}>{a.reason}</td>}
                      </tr>
                    ))}
                    <tr><td className="muted">留现金</td><td className="muted">{(cash * 100).toFixed(1)}%</td><td /><td className="muted">{money(capital * cash)}</td>{mode === 'ai' && <td />}</tr>
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
      <div className="src-cite">研究工具,非投资建议。分配为规则化/AI 推演,股数按现价确定性计算{isCN ? '(A股按一手=100股向下取整,凑不满一手的自动舍弃)' : ''};是否买入、买多少由你自行决定。</div>
    </Modal>
  )
}
