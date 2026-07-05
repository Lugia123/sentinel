import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchHistory, fetchExplain, fetchInvestigate, fetchBlobHTML, fetchEarningsQuarters, fetchEarningsInterpret, type EarnQuarter } from '../api'
import type { Holding, HistPoint } from '../types'
import type { TickerMeta } from '../api'
import { pct2, GradeBadge, SleeveBadge, actionColor, verdictCls, InfoDot } from '../ui'
import Select, { type SelectOption } from '../components/Select'
import EarningsChart from '../components/EarningsChart'

export default function StockDetail({ h, meta }: { h: Holding; meta: TickerMeta }) {
  const m = meta[h.ticker]
  const [tab, setTab] = useState<'overview' | 'bg' | 'earnings'>('overview')
  // 背景调查:取回 HTML 片段注入页面(不用 iframe,随整页滚)
  const [bgHtml, setBgHtml] = useState(''); const [bgLoading, setBgLoading] = useState(false); const [bgErr, setBgErr] = useState('')
  const loadBg = async (force = false) => {
    setBgLoading(true); setBgErr('')
    try { const r = await fetchInvestigate(h.ticker, force); setBgHtml(await fetchBlobHTML(r.key)) }
    catch (e: any) { setBgErr(String(e.message || e)) }
    setBgLoading(false)
  }
  useEffect(() => { if (tab === 'bg' && !bgHtml && !bgLoading) loadBg(false) }, [tab])
  // 财报解读
  const [quarters, setQuarters] = useState<EarnQuarter[]>([]); const [qSel, setQSel] = useState('')
  const [earnHtml, setEarnHtml] = useState(''); const [earnLoading, setEarnLoading] = useState(false); const [earnErr, setEarnErr] = useState('')
  useEffect(() => {
    if (tab === 'earnings' && quarters.length === 0) {
      fetchEarningsQuarters(h.ticker).then((qs) => { setQuarters(qs); if (qs[0]) setQSel(qs[0].period) }).catch((e) => setEarnErr(String(e.message || e)))
    }
  }, [tab])
  const loadEarn = async (force = false) => {
    if (!qSel) return
    setEarnLoading(true); setEarnErr(''); setEarnHtml('')
    try {
      const r = await fetchEarningsInterpret(h.ticker, qSel, force)
      setEarnHtml(await fetchBlobHTML(r.key))
      setQuarters((qs) => qs.map((q) => (q.period === qSel ? { ...q, cached: true } : q))) // 解读完→下拉角标翻「已解读」
    } catch (e: any) { setEarnErr(String(e.message || e)) }
    setEarnLoading(false)
  }
  // 和背景调查一致:进入财报tab或切换季度时自动加载(已解读过的会秒回缓存,没解读的自动解读一次)
  useEffect(() => { if (tab === 'earnings' && qSel && !earnHtml && !earnLoading) loadEarn(false) }, [tab, qSel])
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
      legend: { textStyle: { color: '#bcae97' }, top: 0 },
      tooltip: { trigger: 'axis', backgroundColor: '#1f1913', borderColor: '#2c2418', textStyle: { color: '#f1e9da' } },
      xAxis: { type: 'category', data: hist.map((p) => p.date?.slice(5)), axisLabel: { color: '#b0a488' }, axisLine: { lineStyle: { color: '#2c2418' } } },
      yAxis: { type: 'value', scale: true, axisLabel: { color: '#b0a488' }, splitLine: { lineStyle: { color: '#2c2418' } } },
      series: [mk('close', '收盘', '#f1e9da', 2), mk('sma20', '20日线', '#6fae86'), mk('sma50', '50日线', '#c8a253'), mk('sma200', '200日线', '#cf6f5d')],
    })
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [hist, tab]) // 含 tab:从背调/财报切回概览时容器重新挂载,须重新 init(否则图空白)

  const ind = h.indicators
  return (
    <>
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

      <div className="tabs">
        <button className={tab === 'overview' ? 'active' : ''} onClick={() => setTab('overview')}>策略概览</button>
        <button className={tab === 'bg' ? 'active' : ''} onClick={() => setTab('bg')}>背景调查</button>
        <button className={tab === 'earnings' ? 'active' : ''} onClick={() => setTab('earnings')}>财报解读</button>
      </div>

      {tab === 'bg' && (
        <div className="card ai-card">
          <h3>🏢 公司背景调查 <span className="muted" style={{ fontWeight: 400 }}>· AI 调研</span>
            <button className="ghost mini" style={{ float: 'right' }} onClick={() => loadBg(true)} disabled={bgLoading}>{bgLoading ? '调研中…' : '重新背调'}</button>
          </h3>
          {bgLoading && <div className="muted">正在调研公司背景…（首次约 30 秒）</div>}
          {bgErr && <div className="down" style={{ fontSize: 13 }}>{bgErr}</div>}
          {bgHtml && !bgLoading && <div className="doc-html" dangerouslySetInnerHTML={{ __html: bgHtml }} />}
          {bgHtml && !bgLoading && (
            <div className="src-cite">
              📚 信息来源:AI(DeepSeek)依训练时掌握的公开资料综合生成,<b>非实时联网检索</b>,具体数字可能过时。
              请以 <a href={`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=${h.ticker}&type=10-K`} target="_blank" rel="noreferrer">SEC EDGAR 年报</a>、公司投资者关系官网为准核实。
            </div>
          )}
        </div>
      )}

      {tab === 'earnings' && (
        <div className="card ai-card">
          <h3>📊 财报解读 <span className="muted" style={{ fontWeight: 400 }}>· SEC 官方数据 + AI 解读</span></h3>
          {earnErr && <div className="down" style={{ fontSize: 13, marginBottom: 8 }}>{earnErr}</div>}
          <div className="pos-add">
            {quarters.length === 0
              ? <div className="muted">加载季度…</div>
              : <Select value={qSel} placeholder="选择季度" ariaLabel="选择季度"
                  onChange={(v) => { setQSel(v); setEarnHtml('') }}
                  options={quarters.map((q): SelectOption => ({
                    value: q.period, label: `${q.period} 季报`,
                    badge: q.cached ? <span className="earn-done">已解读 ✓</span> : <span className="earn-todo">未解读</span>,
                  }))} />}
            <button className="ghost" onClick={() => loadEarn(false)} disabled={earnLoading || !qSel}>{earnLoading ? '解读中…' : '解读这一季'}</button>
            {earnHtml && <button className="ghost mini" onClick={() => loadEarn(true)} disabled={earnLoading}>重新解读</button>}
          </div>
          {quarters.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <div className="muted" style={{ marginBottom: 2 }}>营收 / 净利润 / 净利率(近8季 · SEC 官方数据)</div>
              <EarningsChart quarters={quarters} />
            </div>
          )}
          {earnLoading && <div className="muted">正在解读财报…（首次约 30 秒）</div>}
          {earnHtml && !earnLoading && <div className="doc-html" dangerouslySetInnerHTML={{ __html: earnHtml }} />}
          {!earnHtml && !earnLoading && quarters.length > 0 && <div className="muted">切换季度自动解读(解读过的会秒回)。</div>}
          {quarters.length > 0 && (
            <div className="src-cite">
              📚 数据来源:<a href={`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=${h.ticker}&type=10-Q`} target="_blank" rel="noreferrer">SEC EDGAR</a>
              {' '}官方季度财报(us-gaap XBRL 概念:Revenues / NetIncomeLoss / OperatingIncomeLoss / GrossProfit / EPS)。图表为原始数据确定性绘制,非 AI 生成;解读文字为 AI 基于同一数据生成。
            </div>
          )}
        </div>
      )}

      {tab === 'overview' && (<>
      {h.reason && <div className="card"><h3>为什么选它</h3><p style={{ margin: 0 }}>{h.reason}</p></div>}

      {/* AI 讲解 */}
      <div className="card ai-card">
        <h3>🤖 AI 讲解 <span className="muted" style={{ fontWeight: 400 }}>· DeepSeek 按策略规则白话解读</span>
          <button className="ghost mini" style={{ float: 'right' }} onClick={() => loadAI(true)} disabled={aiLoading}>{aiLoading ? '生成中…' : '重新讲解'}</button>
        </h3>
        {aiLoading && <div className="muted">正在生成讲解…（首次约几秒）</div>}
        {aiErr && <div className="down" style={{ fontSize: 13 }}>{aiErr}</div>}
        {!aiLoading && ai && <div className="ai-text" dangerouslySetInnerHTML={{ __html: ai }} />}
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
      </>)}
    </>
  )
}
