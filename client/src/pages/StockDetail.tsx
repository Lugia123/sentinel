import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchHistory, fetchExplain } from '../api'
import type { Holding, HistPoint } from '../types'
import type { TickerMeta } from '../api'
import { pct2, GradeBadge, SleeveBadge, actionColor, verdictCls, InfoDot } from '../ui'

export default function StockDetail({ h, meta, onBack }: { h: Holding; meta: TickerMeta; onBack: () => void }) {
  const m = meta[h.ticker]
  const [hist, setHist] = useState<HistPoint[]>([])
  const [ai, setAi] = useState<string>(''); const [aiLoading, setAiLoading] = useState(true); const [aiErr, setAiErr] = useState('')
  const priceRef = useRef<HTMLDivElement>(null)

  useEffect(() => { fetchHistory(h.ticker).then(setHist) }, [h.ticker])
  const loadAI = (force = false) => {
    setAiLoading(true); setAiErr('')
    fetchExplain(h.ticker, force).then((e) => setAi(e.content)).catch((e) => setAiErr(String(e.message || e))).finally(() => setAiLoading(false))
  }
  useEffect(() => { loadAI(false) }, [h.ticker])

  // 价格 + 均线图
  useEffect(() => {
    if (!priceRef.current || hist.length === 0) return
    const chart = echarts.init(priceRef.current)
    const mk = (k: keyof HistPoint, name: string, color: string, w = 1) => ({
      name, type: 'line', showSymbol: false, lineStyle: { width: w, color }, data: hist.map((p) => p[k]),
    })
    chart.setOption({
      backgroundColor: 'transparent', grid: { left: 55, right: 15, top: 30, bottom: 30 },
      legend: { textStyle: { color: '#aeb9c9' }, top: 0 },
      tooltip: { trigger: 'axis', backgroundColor: '#1b2433', borderColor: '#26303f', textStyle: { color: '#e6edf6' } },
      xAxis: { type: 'category', data: hist.map((p) => p.date?.slice(5)), axisLabel: { color: '#6b7787' }, axisLine: { lineStyle: { color: '#26303f' } } },
      yAxis: { type: 'value', scale: true, axisLabel: { color: '#6b7787' }, splitLine: { lineStyle: { color: '#26303f' } } },
      series: [mk('close', '收盘', '#e6edf6', 2), mk('sma20', '20日线', '#2ecc9b'), mk('sma50', '50日线', '#f5a623'), mk('sma200', '200日线', '#ff5c6c')],
    })
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [hist])

  const ind = h.indicators
  return (
    <>
      <button className="ghost" onClick={onBack}>‹ 返回列表</button>
      <div className="card detail-head">
        <div>
          <span className="dh-tk">{h.ticker}</span>
          {m && <span className="cn" style={{ fontSize: 15 }}>{m.cn} · {m.sector}</span>} <SleeveBadge sleeve={h.sleeve} />
          <span className="dh-px">${h.price}</span>
        </div>
        <div>
          <GradeBadge g={h.grade} label={h.grade_label} /> <span style={{ color: actionColor(h.action), fontWeight: 700, marginLeft: 8 }}>{h.action}</span>
        </div>
      </div>

      {h.reason && <div className="card"><h3>为什么选它</h3><p style={{ margin: 0 }}>{h.reason}</p></div>}

      {/* AI 讲解 */}
      <div className="card ai-card">
        <h3>🤖 AI 讲解 <span className="muted" style={{ fontWeight: 400 }}>· DeepSeek 按策略规则白话解读</span>
          <button className="ghost mini" style={{ float: 'right' }} onClick={() => loadAI(true)} disabled={aiLoading}>{aiLoading ? '生成中…' : '重新讲解'}</button>
        </h3>
        {aiLoading && <div className="muted">正在生成讲解…（首次约几秒）</div>}
        {aiErr && <div className="down" style={{ fontSize: 13 }}>{aiErr}</div>}
        {!aiLoading && ai && <div className="ai-text">{ai.split('\n').map((line, i) => <p key={i} style={{ margin: '6px 0' }}>{line}</p>)}</div>}
      </div>

      {/* 档位分解 */}
      {h.signals && <div className="card">
        <h3>档位怎么算的 <InfoDot text="7个子信号,多=看多(+1),空=看空(-1),中=中性(0),求和后映射到 -3~+3。全好就是+3。" /></h3>
        <div className="sig-grid">
          {h.signals.map((s, i) => (
            <div key={i} className="sig">
              <span className={`sig-dot ${verdictCls(s.verdict)}`}>{s.verdict === '多' ? '✓' : s.verdict === '空' ? '✕' : '–'}</span>
              <div><div className="sig-name">{s.name}</div><div className="muted">{s.detail}</div></div>
            </div>
          ))}
        </div>
        <div className="muted" style={{ marginTop: 8 }}>当前档位 <GradeBadge g={h.grade} label={h.grade_label} /> → 动作「{h.action}」（只减不追涨）</div>
      </div>}

      {/* 关键指标 */}
      {ind && <div className="card">
        <h3>关键指标（原值，不藏）</h3>
        <div className="kv-grid">
          <div className="kv"><span>近半年动量</span><b>{ind.mom126 != null ? pct2(ind.mom126) : '—'}</b></div>
          <div className="kv"><span>近21日动量</span><b>{ind.mom21 != null ? pct2(ind.mom21) : '—'}</b></div>
          <div className="kv"><span>年化波动</span><b>{ind.vol_annual != null ? (ind.vol_annual * 100).toFixed(0) + '%' : '—'}</b></div>
          <div className="kv"><span>距52周高</span><b>{pct2(ind.pct_from_high)}</b></div>
          <div className="kv"><span>20/50/200日线</span><b>{ind.sma20}/{ind.sma50}/{ind.sma200}</b></div>
          {ind.sy_yield != null && <div className="kv"><span>股东收益率</span><b>{(ind.sy_yield * 100).toFixed(1)}%</b></div>}
        </div>
      </div>}

      {/* 价格 + 均线 */}
      <div className="card"><h3>价格 + 均线（近120日）</h3><div ref={priceRef} style={{ height: 280 }} />{hist.length === 0 && <div className="muted">加载中/无数据…</div>}</div>

      {/* 概率带 5/20/60 */}
      <div className="card">
        <h3>到价概率带 <InfoDot text="不同时间跨度下,未来收益的70%概率范围 + 参考止损/目标。波动范围估计,非涨跌预测。" /></h3>
        <div className="tbl-scroll">
          <table>
            <thead><tr><th>跨度</th><th>最可能(中位)</th><th>70%区间</th><th>参考止损</th><th>参考目标</th><th>到目标概率</th></tr></thead>
            <tbody>
              {['h5', 'h20', 'h60'].map((k) => {
                const b = h.prob[k]; if (!b) return null
                const label = { h5: '5日', h20: '20日', h60: '60日' }[k]
                return <tr key={k}>
                  <td><b>{label}</b></td>
                  <td className={b.median >= 0 ? 'up' : 'down'}>{pct2(b.median)}</td>
                  <td className="muted">{pct2(b.band70[0])} ~ {pct2(b.band70[1])}</td>
                  <td>${b.stop}</td><td>${b.target}</td>
                  <td>{(b.p_hit_target * 100).toFixed(0)}%</td>
                </tr>
              })}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
