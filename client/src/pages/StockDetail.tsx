import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchHistory, fetchExplain, fetchInvestigate, fetchBlobHTML, fetchEarningsQuarters, fetchEarningsInterpret, fetchStockNews, fetchBandHist, type EarnQuarter, type StockNews, type BandHistPoint } from '../api'
import type { Holding, HistPoint, RiskLight } from '../types'
import type { TickerMeta, Market, DroppedItem } from '../api'
import { pct2, GradeBadge, SleeveBadge, actionColor, verdictCls, InfoDot, cnMarketAction } from '../ui'
import Select, { type SelectOption } from '../components/Select'
import EarningsChart from '../components/EarningsChart'
import ProbBandChart from '../components/ProbBandChart'
import MoneyFlowCard from '../components/MoneyFlowCard'
import NewsItemModal from '../components/NewsItemModal'

export default function StockDetail({ h, meta, market = 'us', riskLight, dropped }: { h: Holding; meta: TickerMeta; market?: Market; riskLight?: RiskLight; dropped?: DroppedItem }) {
  const m = meta[h.ticker]
  const isCN = market === 'cn'
  const cur = isCN ? '¥' : '$'
  // A股动作=市场级风险灯统一指令(单票不按档位减仓);美股=单票档位映射
  const act = isCN && riskLight ? cnMarketAction(riskLight.level) : { text: h.action, color: actionColor(h.action) }
  const [tab, setTab] = useState<'overview' | 'bg' | 'earnings' | 'news'>('overview')
  // 相关新闻(仅 A股;懒加载,类似背调)
  const [news, setNews] = useState<StockNews | null>(null); const [newsLoading, setNewsLoading] = useState(false)
  const [newsItemId, setNewsItemId] = useState<number | null>(null)
  const loadNews = async (refresh = false) => {
    setNewsLoading(true)
    try { setNews(await fetchStockNews(h.ticker, refresh)) } catch { /* ignore */ }
    setNewsLoading(false)
  }
  useEffect(() => { if (tab === 'news' && !news && !newsLoading) loadNews(false) }, [tab])
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
  const [band, setBand] = useState<BandHistPoint[]>([]) // 未来20日收益范围·逐日历史(仅A股)
  const [ai, setAi] = useState<string>(''); const [aiLoading, setAiLoading] = useState(true); const [aiErr, setAiErr] = useState('')
  const priceRef = useRef<HTMLDivElement>(null)
  const bandPctRef = useRef<HTMLDivElement>(null)   // 图1:收益% 范围带
  const bandPxRef = useRef<HTMLDivElement>(null)     // 图2:价格锥

  useEffect(() => { fetchHistory(h.ticker).then(setHist) }, [h.ticker])
  useEffect(() => { if (isCN) fetchBandHist(h.ticker).then(setBand); else setBand([]) }, [h.ticker, isCN])
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
      series: [mk('close', '收盘', '#f1e9da', 2), mk('sma20', '20日线', '#6fae86'), mk('sma_mid', isCN ? '60日线' : '50日线', '#c8a253'), mk('sma200', '200日线', '#cf6f5d')],
    })
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [hist, tab]) // 含 tab:从背调/财报切回概览时容器重新挂载,须重新 init(否则图空白)

  // 图1:未来20日收益范围(%)—— 每天从当日起未来20交易日的70%收益区间(填充带)+中位线,0线基准。
  // 带随波动率呼吸:变宽=波动放大。严格无前视,末点与上方概率带表一致。
  useEffect(() => {
    if (tab !== 'overview' || !bandPctRef.current || band.length === 0) return
    const chart = echarts.init(bandPctRef.current)
    const dates = band.map((p) => p.date.slice(5))
    const loP = band.map((p) => +(p.lo * 100).toFixed(2))
    const hiP = band.map((p) => +(p.hi * 100).toFixed(2))
    const midP = band.map((p) => +(p.mid * 100).toFixed(2))
    const spanP = band.map((p) => +((p.hi - p.lo) * 100).toFixed(2)) // 堆叠差=区间宽度
    chart.setOption({
      backgroundColor: 'transparent', grid: { left: 55, right: 15, top: 30, bottom: 30 },
      legend: { data: ['中位', '70%区间'], textStyle: { color: '#bcae97' }, top: 0 },
      tooltip: {
        trigger: 'axis', backgroundColor: '#1f1913', borderColor: '#2c2418', textStyle: { color: '#f1e9da' },
        formatter: (ps: any) => {
          const i = ps[0].dataIndex
          return `${band[i].date}<br/>区间 ${loP[i]}% ~ ${hiP[i]}%<br/>中位 ${midP[i]}%`
        },
      },
      xAxis: { type: 'category', data: dates, axisLabel: { color: '#b0a488' }, axisLine: { lineStyle: { color: '#2c2418' } } },
      yAxis: { type: 'value', axisLabel: { color: '#b0a488', formatter: '{value}%' }, splitLine: { lineStyle: { color: '#2c2418' } } },
      series: [
        // 堆叠填充带:下沿(透明线)+ 区间宽度(金色半透明面)
        { name: '_lo', type: 'line', stack: 'band', data: loP, symbol: 'none', lineStyle: { opacity: 0 }, silent: true, z: 1 },
        { name: '70%区间', type: 'line', stack: 'band', data: spanP, symbol: 'none', lineStyle: { opacity: 0 }, areaStyle: { color: 'rgba(200,162,83,.20)' }, z: 1 },
        {
          name: '中位', type: 'line', data: midP, symbol: 'none', lineStyle: { color: '#e6c878', width: 1.5 }, z: 2,
          markLine: { silent: true, symbol: 'none', lineStyle: { color: '#6b5f3e', type: 'dashed' }, data: [{ yAxis: 0 }], label: { show: false } },
        },
      ],
    })
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [band, tab])

  // 图2:价格锥 —— 同一组带换算成价位 close×(1+lo/hi),贴着收盘线的包络;可与上方价格图/后续真实走势对照。
  useEffect(() => {
    if (tab !== 'overview' || !bandPxRef.current || band.length === 0) return
    const chart = echarts.init(bandPxRef.current)
    const dates = band.map((p) => p.date.slice(5))
    const close = band.map((p) => p.close)
    const loP = band.map((p) => +(p.close * (1 + p.lo)).toFixed(2))
    const spanP = band.map((p) => +(p.close * (p.hi - p.lo)).toFixed(2))
    const hiP = band.map((p) => +(p.close * (1 + p.hi)).toFixed(2))
    chart.setOption({
      backgroundColor: 'transparent', grid: { left: 55, right: 15, top: 30, bottom: 30 },
      legend: { data: ['收盘', '未来20日价位区间'], textStyle: { color: '#bcae97' }, top: 0 },
      tooltip: {
        trigger: 'axis', backgroundColor: '#1f1913', borderColor: '#2c2418', textStyle: { color: '#f1e9da' },
        formatter: (ps: any) => {
          const i = ps[0].dataIndex
          return `${band[i].date}<br/>收盘 ${cur}${close[i]}<br/>区间 ${cur}${loP[i]} ~ ${cur}${hiP[i]}`
        },
      },
      xAxis: { type: 'category', data: dates, axisLabel: { color: '#b0a488' }, axisLine: { lineStyle: { color: '#2c2418' } } },
      yAxis: { type: 'value', scale: true, axisLabel: { color: '#b0a488' }, splitLine: { lineStyle: { color: '#2c2418' } } },
      series: [
        { name: '_lo', type: 'line', stack: 'px', data: loP, symbol: 'none', lineStyle: { opacity: 0 }, silent: true, z: 1 },
        { name: '未来20日价位区间', type: 'line', stack: 'px', data: spanP, symbol: 'none', lineStyle: { opacity: 0 }, areaStyle: { color: 'rgba(123,167,176,.20)' }, z: 1 },
        { name: '收盘', type: 'line', data: close, symbol: 'none', lineStyle: { color: '#f1e9da', width: 2 }, z: 2 },
      ],
    })
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [band, tab])

  const ind = h.indicators
  const dChg = dropped && dropped.price_now > 0 && dropped.last_price > 0
    ? (dropped.price_now - dropped.last_price) / dropped.last_price : null
  return (
    <>
      {dropped && (
        <div className="card" style={{ borderColor: 'var(--warn)', marginBottom: 10 }}>
          <b style={{ color: 'var(--warn)' }}>⚠ 已掉出推荐</b>
          <span className="muted" style={{ marginLeft: 8 }}>
            最后在推荐中 {dropped.last_seen} · 判定掉出 {dropped.dropped_at}
            {dChg != null && <> · 掉出后 <span className={dChg >= 0 ? 'up' : 'down'}>{pct2(dChg)}</span>({cur}{dropped.last_price} → {cur}{dropped.price_now})</>}
          </span>
          <div className="muted" style={{ marginTop: 4, fontSize: 13 }}>
            下方档位/指标/概率为<b>掉出前最后一天</b>的快照数据;「AI 讲解」已切换为<b>掉出原因分析</b>。连续 2 个交易日重新满足入选条件会自动回归推荐。
          </div>
        </div>
      )}
      <div className="card detail-head">
        <div>
          <span className="dh-tk">{h.ticker}</span>
          {(h.name || m?.cn) && <span className="cn" style={{ fontSize: 15 }}>{h.name || m?.cn}{m?.sector ? ` · ${m.sector}` : ''}</span>} <SleeveBadge sleeve={h.sleeve} />
          <span className="dh-px">{cur}{h.price}</span>
        </div>
        <div>
          <GradeBadge g={h.grade} label={h.grade_label} /> <span style={{ color: act.color, fontWeight: 700, marginLeft: 8 }}>{act.text}</span>
        </div>
      </div>

      <div className="tabs">
        <button className={tab === 'overview' ? 'active' : ''} onClick={() => setTab('overview')}>策略概览</button>
        <button className={tab === 'bg' ? 'active' : ''} onClick={() => setTab('bg')}>背景调查</button>
        <button className={tab === 'earnings' ? 'active' : ''} onClick={() => setTab('earnings')}>财报解读</button>
        {isCN && <button className={tab === 'news' ? 'active' : ''} onClick={() => setTab('news')}>相关新闻</button>}
      </div>

      {tab === 'news' && (
        <div className="card ai-card">
          <h3>📰 相关新闻 <span className="muted" style={{ fontWeight: 400 }}>· 资讯参考,非策略信号</span>
            <button className="ghost mini" style={{ float: 'right' }} onClick={() => loadNews(true)} disabled={newsLoading}>{newsLoading ? '刷新中…' : '刷新'}</button>
          </h3>
          {newsLoading && !news && <div className="muted">加载相关新闻…（首次约 20 秒）</div>}
          {news && (<>
            {news.summary && <div className="alloc-note" style={{ marginBottom: 10 }}>🧭 当前叙事:{news.summary}</div>}
            {news.keywords && news.keywords.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                {news.keywords.map((k, i) => (
                  <span key={i} className="pill" style={{ marginRight: 6, marginBottom: 4, display: 'inline-block' }}
                    title={k.why}>{k.kw} <span className="muted" style={{ fontSize: 11 }}>{(k.weight * 100).toFixed(0)}</span></span>
                ))}
              </div>
            )}
            {news.flags && news.flags.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                {news.flags.map((f, i) => (
                  <div key={i} className="muted" style={{ padding: '4px 0', fontSize: 13,
                    color: f.type === 'avoid_risk' ? 'var(--warn)' : f.type === 'attention' ? 'var(--up)' : undefined }}>
                    {f.type === 'avoid_risk' ? '⚠' : f.type === 'attention' ? '👀' : '📊'} <b>{f.text}</b>
                    <span className="muted" style={{ fontSize: 12 }}> · {f.basis} · {f.note}</span>
                  </div>
                ))}
              </div>
            )}
            {news.news.length === 0 && <div className="muted">暂无采集到的相关新闻。点「刷新」触发采集(约 20 秒)。</div>}
            <div className="news-list">
              {news.news.map((n, i) => (
                <div key={i} className="news-item" onClick={() => n.id && setNewsItemId(n.id)}>
                  <div className="news-time"><span className="nd-date">{n.published && n.published.length >= 10 ? n.published.slice(5, 10) : ''}</span><span className="nd-time">{n.published && n.published.length >= 16 ? n.published.slice(11, 16) : ''}</span></div>
                  <div className="news-main">
                    <div className="news-headline">{n.title.replace(/^【(.+?)】/, '$1').trim()}</div>
                    <div className="news-meta"><span className="news-src-tag">{n.source}</span>{n.relation !== 'company' ? ` · ${n.relation}` : ''}</div>
                  </div>
                </div>
              ))}
            </div>
            <div className="src-cite">{news.disclaimer || '资讯/关注/风险提示,非投资建议。'}</div>
          </>)}
        </div>
      )}
      {newsItemId && <NewsItemModal id={newsItemId} onClose={() => setNewsItemId(null)} />}

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
              {isCN
                ? <>请以 <a href={`http://www.cninfo.com.cn/new/fulltextSearch?notautosubmit=&keyWord=${h.ticker.replace(/^\w+\./, '')}`} target="_blank" rel="noreferrer">巨潮资讯网公告/年报</a>、交易所披露平台为准核实。</>
                : <>请以 <a href={`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=${h.ticker}&type=10-K`} target="_blank" rel="noreferrer">SEC EDGAR 年报</a>、公司投资者关系官网为准核实。</>}
            </div>
          )}
        </div>
      )}

      {tab === 'earnings' && (
        <div className="card ai-card">
          <h3>📊 财报解读 <span className="muted" style={{ fontWeight: 400 }}>· {isCN ? '公开财报数据(单季差分)' : 'SEC 官方数据'} + AI 解读</span></h3>
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
              <div className="muted" style={{ marginBottom: 2 }}>营收 / 净利润 / 净利率(近8季 · {isCN ? '新浪财经利润表,已差分成单季' : 'SEC 官方数据'})</div>
              <EarningsChart quarters={quarters} unit={isCN ? '亿元' : '亿美元'} />
            </div>
          )}
          {earnLoading && <div className="muted">正在解读财报…（首次约 30 秒）</div>}
          {earnHtml && !earnLoading && <div className="doc-html" dangerouslySetInnerHTML={{ __html: earnHtml }} />}
          {!earnHtml && !earnLoading && quarters.length > 0 && <div className="muted">切换季度自动解读(解读过的会秒回)。</div>}
          {quarters.length > 0 && (
            <div className="src-cite">
              {isCN
                ? <>📚 数据来源:新浪财经利润表(累计值已差分为单季)。请以 <a href={`http://www.cninfo.com.cn/new/fulltextSearch?notautosubmit=&keyWord=${h.ticker.replace(/^\w+\./, '')}`} target="_blank" rel="noreferrer">巨潮资讯网</a> 官方公告为准。图表为原始数据确定性绘制,非 AI 生成;解读文字为 AI 基于同一数据生成。</>
                : <>📚 数据来源:<a href={`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=${h.ticker}&type=10-Q`} target="_blank" rel="noreferrer">SEC EDGAR</a>
              {' '}官方季度财报(us-gaap XBRL 概念:Revenues / NetIncomeLoss / OperatingIncomeLoss / GrossProfit / EPS)。图表为原始数据确定性绘制,非 AI 生成;解读文字为 AI 基于同一数据生成。</>}
            </div>
          )}
        </div>
      )}

      {tab === 'overview' && (<>
      {h.reason && <div className="card"><h3>为什么选它</h3><p style={{ margin: 0 }}>{h.reason}</p></div>}

      {/* AI 讲解 */}
      <div className="card ai-card">
        <h3>🤖 {dropped ? 'AI 掉出分析' : 'AI 讲解'} <span className="muted" style={{ fontWeight: 400 }}>· {dropped ? 'DeepSeek 分析为什么掉出推荐' : 'DeepSeek 按策略规则白话解读'}</span>
          <button className="ghost mini" style={{ float: 'right' }} onClick={() => loadAI(true)} disabled={aiLoading}>{aiLoading ? '生成中…' : '重新讲解'}</button>
        </h3>
        {aiLoading && <div className="muted">正在生成讲解…（首次约几秒）</div>}
        {aiErr && <div className="down" style={{ fontSize: 13 }}>{aiErr}</div>}
        {!aiLoading && ai && <div className="ai-text" dangerouslySetInnerHTML={{ __html: ai }} />}
      </div>

      {/* 档位分解 */}
      {h.signals && <div className="card">
        <h3>档位怎么算的 <InfoDot text={isCN ? "3个子信号(站上20/60/200日线),多=看多(+1),空=看空(-1),求和映射到 -3~+3。全好就是+3。" : "7个子信号,多=看多(+1),空=看空(-1),中=中性(0),求和后映射到 -3~+3。全好就是+3。"} /></h3>
        <div className="sig-grid">
          {h.signals.map((s, i) => (
            <div key={i} className="sig">
              <span className={`sig-dot ${verdictCls(s.verdict)}`}>{s.verdict === '多' ? '✓' : s.verdict === '空' ? '✕' : '–'}</span>
              <div><div className="sig-name">{s.name}</div><div className="muted">{s.detail}</div></div>
            </div>
          ))}
        </div>
        <div className="muted" style={{ marginTop: 8 }}>
          {isCN
            ? <>当前档位 <GradeBadge g={h.grade} label={h.grade_label} />(仅展示趋势,不触发单票减仓)→ 动作由市场级风险灯决定:「<span style={{ color: act.color, fontWeight: 600 }}>{act.text}</span>」{riskLight ? `(当前风险灯:${riskLight.note})` : ''}</>
            : <>当前档位 <GradeBadge g={h.grade} label={h.grade_label} /> → 动作「{h.action}」（只减不追涨）</>}
        </div>
      </div>}

      {/* 关键指标 */}
      {ind && <div className="card">
        <h3>关键指标（原值，不藏）</h3>
        <div className="kv-grid">
          {isCN ? (<>
            <div className="kv"><span>流通市值</span><b>{ind.float_mktcap_yi != null ? ind.float_mktcap_yi.toFixed(1) + ' 亿' : '—'}</b></div>
            <div className="kv"><span>20日均换手</span><b>{ind.turn20 != null ? ind.turn20.toFixed(2) + '%' : '—'}</b></div>
            {ind.event_score != null && <div className="kv"><span>事件分(rev+PEAD)</span><b>{ind.event_score.toFixed(3)}</b></div>}
          </>) : (<>
            <div className="kv"><span>近半年动量</span><b>{ind.mom126 != null ? pct2(ind.mom126) : '—'}</b></div>
            <div className="kv"><span>近21日动量</span><b>{ind.mom21 != null ? pct2(ind.mom21) : '—'}</b></div>
            <div className="kv"><span>年化波动</span><b>{ind.vol_annual != null ? (ind.vol_annual * 100).toFixed(0) + '%' : '—'}</b></div>
            <div className="kv"><span>距52周高</span><b>{ind.pct_from_high != null ? pct2(ind.pct_from_high) : '—'}</b></div>
            <div className="kv"><span>20/50/200日线</span><b>{ind.sma20}/{ind.sma50}/{ind.sma200}</b></div>
            {ind.sy_yield != null && <div className="kv"><span>股东收益率</span><b>{(ind.sy_yield * 100).toFixed(1)}%</b></div>}
          </>)}
        </div>
      </div>}

      {/* 价格 + 均线 */}
      <div className="card"><h3>价格 + 均线（近120日）</h3><div ref={priceRef} style={{ height: 280 }} />{hist.length === 0 && <div className="muted">加载中/无数据…</div>}</div>

      {/* 未来20日收益范围·逐日历史(仅A股):图1 收益% / 图2 价格锥 —— 与价格图 x 轴对齐 */}
      {isCN && (
        <div className="card">
          <h3>未来20日收益范围 · 近120日 <InfoDot text="对过去每一天,用当日往前的数据估算「从那天起未来20交易日」收益的70%区间(严格无前视)。带变宽=那阵子波动放大。上图看收益百分比,下图换算成价位锥(可与价格走势对照)。末点与上方概率带一致。波动范围估计,非涨跌预测。" /></h3>
          {band.length === 0
            ? <div className="muted">加载中/数据不足(需≥120交易日)…</div>
            : <>
                <div className="muted" style={{ fontSize: 12, margin: '2px 0 6px' }}>① 收益视角(%)——70%区间随时间的宽窄变化</div>
                <div ref={bandPctRef} style={{ height: 200 }} />
                <div className="muted" style={{ fontSize: 12, margin: '10px 0 6px' }}>② 价格视角——区间换算成价位,贴着收盘线的包络</div>
                <div ref={bandPxRef} style={{ height: 220 }} />
              </>}
        </div>
      )}

      {/* 概率带 5/20/60 */}
      <div className="card">
        <h3>到价概率带 <InfoDot text={isCN ? "未来20日收益的70%概率范围 + 参考止损/目标(A股目前只算20日跨度)。波动范围估计,非涨跌预测。" : "不同时间跨度下,未来收益的70%概率范围 + 参考止损/目标。波动范围估计,非涨跌预测。"} /></h3>
        <ProbBandChart prob={h.prob} />
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
                  <td>{cur}{b.stop}</td><td>{cur}{b.target}</td>
                  <td>{(b.p_hit_target * 100).toFixed(0)}%</td>
                </tr>
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* 资金流·量能(仅A股,纯展示)*/}
      {isCN && <MoneyFlowCard ticker={h.ticker} />}
      </>)}
    </>
  )
}
