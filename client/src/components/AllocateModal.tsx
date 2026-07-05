import { useState } from 'react'
import Modal from './Modal'
import { fetchAIAllocate, type AllocItem, type TickerMeta } from '../api'
import type { Holding } from '../types'
import { usd } from '../ui'

type Mode = 'even' | 'risk_parity' | 'ai'
const r2 = (x: number) => Math.round(x * 100) / 100
const r3 = (x: number) => Math.round(x * 1000) / 1000
const r4 = (x: number) => Math.round(x * 10000) / 10000

// 建议股数分配弹窗:选股票 × 分配方式(均分/风险平价/AI),算出各股目标股数;
// 未选的当 0。确认后回写主列表。
export default function AllocateModal({ holdings, meta, capital, exposure, onApply, onClose }: {
  holdings: Holding[]
  meta: TickerMeta
  capital: number
  exposure: number // 风险灯建议总仓位(0-1)
  onApply: (shares: Record<string, number>, note: string) => void
  onClose: () => void
}) {
  const [sel, setSel] = useState<Set<string>>(new Set(holdings.map((h) => h.ticker)))
  const [mode, setMode] = useState<Mode>('risk_parity')
  const [result, setResult] = useState<AllocItem[] | null>(null)
  const [cash, setCash] = useState(0)
  const [note, setNote] = useState('')
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  const toggle = (tk: string) => setSel((s) => { const n = new Set(s); n.has(tk) ? n.delete(tk) : n.add(tk); return n })
  const allOn = sel.size === holdings.length
  const toggleAll = () => setSel(allOn ? new Set() : new Set(holdings.map((h) => h.ticker)))

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
    // 确定性:均分 / 风险平价(逆波动),总仓位=风险灯exposure
    let w: number[]
    if (mode === 'even') w = chosen.map(() => 1 / chosen.length)
    else {
      const inv = chosen.map((h) => 1 / Math.max(0.05, h.indicators?.vol_annual ?? 0.3))
      const s = inv.reduce((a, b) => a + b, 0); w = inv.map((x) => x / s)
    }
    const items: AllocItem[] = chosen.map((h, i) => ({
      ticker: h.ticker, weight: r4(w[i] * exposure), shares: r3((capital * w[i] * exposure) / h.price),
      value: r2(capital * w[i] * exposure), reason: '',
    }))
    setResult(items); setNote(''); setCash(r4(1 - items.reduce((a, b) => a + b.weight, 0)))
  }

  const apply = () => {
    if (!result) return
    const m: Record<string, number> = {}
    holdings.forEach((h) => { m[h.ticker] = 0 }) // 未选/未分配 = 0
    result.forEach((a) => { m[a.ticker] = a.shares })
    onApply(m, note || `${mode === 'even' ? '均分' : mode === 'risk_parity' ? '风险平价' : 'AI'}分配 · 选中${sel.size}只`)
    onClose()
  }

  return (
    <Modal wide title={<>⚖ 为建议股数分配 <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>· 资金池 {usd(capital)} · 选中的才买,没选的当 0</span></>} onClose={onClose}>
      <div className="alloc-modes">
        <button className={mode === 'even' ? 'active' : ''} onClick={() => setMode('even')}>均分</button>
        <button className={mode === 'risk_parity' ? 'active' : ''} onClick={() => setMode('risk_parity')}>风险平价(波动低多给)</button>
        <button className={mode === 'ai' ? 'active' : ''} onClick={() => setMode('ai')}>🤖 AI 分配(做取舍)</button>
        <button className="primary" onClick={compute} disabled={loading} style={{ marginLeft: 'auto' }}>{loading ? 'AI 分配中…（约15秒）' : '计算分配'}</button>
      </div>
      {err && <div className="down" style={{ fontSize: 13, margin: '8px 0' }}>{err}</div>}

      <div className="alloc-grid">
        <div className="alloc-pick">
          <div className="alloc-sub">
            选择股票 <button className="linkbtn" onClick={toggleAll}>{allOn ? '全不选' : '全选'}</button>
          </div>
          <div className="alloc-list">
            {holdings.map((h) => (
              <label key={h.ticker} className={`alloc-item ${sel.has(h.ticker) ? 'on' : ''}`}>
                <input type="checkbox" checked={sel.has(h.ticker)} onChange={() => toggle(h.ticker)} />
                <b>{h.ticker}</b><span className="ss-sub">{meta[h.ticker]?.cn || ''}</span>
                <span className="alloc-g" data-g={h.grade >= 2 ? 'up' : h.grade >= -1 ? 'mid' : 'down'}>{h.grade >= 0 ? '+' : ''}{h.grade}</span>
              </label>
            ))}
          </div>
        </div>
        <div className="alloc-res">
          <div className="alloc-sub">分配结果</div>
          {!result && <div className="muted">选好股票和方式,点「计算分配」。<br />AI 分配会根据资金池+价+趋势+波动做取舍(不必全买)。</div>}
          {result && (
            <>
              {note && <div className="alloc-note">🤖 {note}</div>}
              <div className="tbl-scroll" style={{ maxHeight: 300 }}>
                <table>
                  <thead><tr><th>标的</th><th>权重</th><th>股数</th><th>金额</th>{mode === 'ai' && <th>理由</th>}</tr></thead>
                  <tbody>
                    {result.map((a) => (
                      <tr key={a.ticker}>
                        <td><b>{a.ticker}</b> <span className="ss-sub">{meta[a.ticker]?.cn || ''}</span></td>
                        <td>{(a.weight * 100).toFixed(1)}%</td>
                        <td>{a.shares}</td>
                        <td>{usd(a.value)}</td>
                        {mode === 'ai' && <td className="muted" style={{ fontSize: 12 }}>{a.reason}</td>}
                      </tr>
                    ))}
                    <tr><td className="muted">留现金</td><td className="muted">{(cash * 100).toFixed(1)}%</td><td /><td className="muted">{usd(capital * cash)}</td>{mode === 'ai' && <td />}</tr>
                  </tbody>
                </table>
              </div>
              <div style={{ marginTop: 12, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button className="ghost" onClick={onClose}>取消</button>
                <button className="primary" onClick={apply}>应用到列表</button>
              </div>
            </>
          )}
        </div>
      </div>
      <div className="src-cite">研究工具,非投资建议。分配为规则化/AI 推演,股数按现价确定性计算;是否买入、买多少由你自行决定。</div>
    </Modal>
  )
}
