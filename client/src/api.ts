import type { Snapshot, Position, PnLResult, Version, HistPoint, Explanation } from './types'

// ── v2.0 双市场:全局当前市场(切换器设置,各 fetch 自动带 market)──
export type Market = 'us' | 'cn'
let currentMarket: Market = ((typeof localStorage !== 'undefined' && localStorage.getItem('sentinel_market')) as Market) || 'us'
export function getMarket(): Market { return currentMarket }
export function setMarket(m: Market) {
  currentMarket = m
  if (typeof localStorage !== 'undefined') localStorage.setItem('sentinel_market', m)
}
// mq: 往已有 query 串(可空)追加 market=cn(us 省略,向后兼容)
function mq(existing = ''): string {
  if (currentMarket !== 'cn') return existing
  return existing ? `${existing}&market=cn` : '?market=cn'
}

export async function fetchSnapshot(date?: string, market?: Market): Promise<Snapshot> {
  const q = date && date !== 'latest' ? `?date=${date}` : ''
  const mkq = market ? (q ? `${q}&market=${market}` : `?market=${market}`) : mq(q)
  const r = await fetch(`/api/snapshot${mkq}`)
  if (!r.ok) throw new Error((await r.json()).error || '读取快照失败')
  return r.json()
}

export async function fetchVersion(): Promise<Version> {
  const r = await fetch('/api/version')
  return r.ok ? r.json() : { version: 'dev', branch: '', commit: '' }
}

// AltStatus A股事件/红利数据源(tushare,需token会过期)健康。ok=false 时前端顶部红条告警。
export type AltStatus = { ok: boolean; source?: string; last_ok?: string; stale_hours?: number; last_error?: string }
export async function fetchAltStatus(): Promise<AltStatus> {
  try {
    const r = await fetch('/api/altstatus')
    return r.ok ? r.json() : { ok: true } // 拿不到状态时不误报
  } catch { return { ok: true } }
}

export async function runEngine(withSY = true): Promise<string> {
  const r = await fetch(`/api/run${mq(`?sy=${withSY ? 1 : 0}`)}`, { method: 'POST' })
  const j = await r.json()
  if (!r.ok) throw new Error(j.error || '引擎运行失败')
  return j.log || 'done'
}

export async function fetchPnL(date?: string): Promise<PnLResult> {
  const q = date && date !== 'latest' ? `?date=${date}` : ''
  const r = await fetch(`/api/positions${mq(q)}`)
  if (!r.ok) throw new Error((await r.json()).error || '读取持仓失败')
  return r.json()
}

export async function savePositions(ps: Position[]): Promise<void> {
  const r = await fetch(`/api/positions${mq()}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(ps),
  })
  if (!r.ok) throw new Error((await r.json()).error || '保存持仓失败')
}

export async function fetchHistory(ticker: string, n = 120, market?: Market): Promise<HistPoint[]> {
  const mk = market ?? currentMarket
  const r = await fetch(`/api/history?ticker=${ticker}&n=${n}${mk === 'cn' ? '&market=cn' : ''}`)
  if (!r.ok) return []
  return (await r.json()).history || []
}

// 未来20日收益范围·逐日历史(详情页两图:收益% / 价格锥)。lo/hi=70%区间收益,mid=中位;仅A股。
export interface BandHistPoint { date: string; close: number; lo: number; hi: number; mid: number }
export async function fetchBandHist(ticker: string, n = 120, market?: Market): Promise<BandHistPoint[]> {
  const mk = market ?? currentMarket
  if (mk !== 'cn') return [] // 暂仅A股
  const r = await fetch(`/api/bandhist?ticker=${ticker}&n=${n}&market=cn`)
  if (!r.ok) return []
  return (await r.json()).points || []
}

// 个股资金流·量能(仅A股,纯展示)。金额单位亿元;流入为正。
export interface MFPoint { date: string; main: number | null; retail: number | null; net: number | null; elg: number | null; lg: number | null; md: number | null; sm: number | null; vol_ratio: number | null; turn: number | null; pct: number | null; close: number | null }
export interface MFSummary { main_5d: number | null; main_20d: number | null; retail_5d: number | null; consec: number; vol_ratio: number | null; turn: number | null; pct: number | null; buckets_today: { elg: number | null; lg: number | null; md: number | null; sm: number | null }; state: string; tone: string; divergence: string; has_moneyflow: boolean }
export interface MoneyFlow { ticker: string; asof: string; summary: MFSummary; points: MFPoint[] }
export async function fetchMoneyflow(ticker: string, days = 40, market?: Market): Promise<MoneyFlow | null> {
  const mk = market ?? currentMarket
  if (mk !== 'cn') return null // 暂仅A股
  const r = await fetch(`/api/moneyflow?ticker=${ticker}&days=${days}&market=cn`)
  if (!r.ok) return null
  const j = await r.json()
  return j.error ? null : j
}

// 板块资金热力(A股行业,纯展示)。net=今日主力净流入(亿),net5=近5日累计。
export interface SectorItem { name: string; net: number; net5: number; pct: number | null; rate: number | null; lead: string }
export interface SectorFlow { asof: string; days: number; industries: SectorItem[] }
export async function fetchSectorFlow(): Promise<SectorFlow | null> {
  const r = await fetch('/api/moneyflow/sector')
  if (!r.ok) return null
  const j = await r.json()
  return j.error ? null : j
}

export interface WatchItem { ticker: string; starred: boolean; custom: boolean }
export async function fetchWatchlist(): Promise<WatchItem[]> {
  const r = await fetch(`/api/watchlist${mq()}`)
  return r.ok ? (await r.json()).watchlist || [] : []
}
// 关注★(独立于自定义追踪)
export async function setStar(ticker: string, on: boolean): Promise<void> {
  await fetch(`/api/watchlist/star${mq(`?ticker=${ticker}&on=${on ? 1 : 0}`)}`, { method: 'POST' })
}
// 加自定义追踪股(不关注;后端同步预热档位,约3秒)
export async function addCustom(ticker: string): Promise<void> {
  const r = await fetch(`/api/watchlist/custom${mq(`?ticker=${ticker}`)}`, { method: 'POST' })
  const j = await r.json().catch(() => ({})); if (!r.ok || j.error) throw new Error(j.error || '添加失败')
}
export async function removeCustom(ticker: string): Promise<void> {
  await fetch(`/api/watchlist/custom${mq(`?ticker=${ticker}`)}`, { method: 'DELETE' })
}

export interface TrendPoint { date: string; grade: number; price: number; median20: number | null }
export async function fetchTrend(ticker: string, from?: string, to?: string): Promise<TrendPoint[]> {
  const qs = new URLSearchParams({ ticker }); if (from) qs.set('from', from); if (to) qs.set('to', to); if (currentMarket==='cn') qs.set('market','cn')
  const r = await fetch(`/api/trend?${qs}`)
  return r.ok ? (await r.json()).points || [] : []
}
// 富序列:每个交易日的多维指标(档位/中位/动量/波动/距高/概率带宽等)
export interface RichTrendPoint {
  date: string; grade: number | null; median20: number | null; mom21: number | null; mom126: number | null
  vol: number | null; pct_from_high: number | null; bandwidth: number | null; price: number | null
  sma20: number | null; sma50: number | null; sy: number | null
}
export async function fetchTrendRich(tickers: string[]): Promise<Record<string, RichTrendPoint[]>> {
  if (!tickers.length) return {}
  const qs = new URLSearchParams({ tickers: tickers.join(',') }); if (currentMarket==='cn') qs.set('market','cn')
  const r = await fetch(`/api/trend?${qs}`)
  return r.ok ? (await r.json()).series || {} : {}
}
// 有档位历史的可选股票(供多选下拉;A股带 name 中文名,美股走 meta 映射)
export async function fetchTrendTickers(): Promise<{ ticker: string; n: number; name?: string }[]> {
  const r = await fetch(`/api/trend/tickers${mq()}`)
  return r.ok ? (await r.json()).tickers || [] : []
}

// 掉出推荐列表(曾被策略选中、经 CD 防抖后判定掉出)
export interface DroppedItem {
  ticker: string; name: string; last_seen: string; dropped_at: string
  last_price: number; last_grade: number; price_now: number; context: string
}
export async function fetchDropped(): Promise<DroppedItem[]> {
  const r = await fetch(`/api/dropped${mq()}`)
  return r.ok ? (await r.json()).dropped || [] : []
}

// 风险灯历史(近60天):asof/等级/暴露/宽度(A股)/spy_vol(美股)
export interface RiskHistItem {
  asof: string; level: string; exposure: number
  breadth: number | null; breadth_ma: number | null; crowd: number | null; amount_ratio: number | null; spy_vol: number | null; diverge: boolean | null
}
export async function fetchRiskHistory(market?: Market): Promise<RiskHistItem[]> {
  const q = market ? `?market=${market}` : mq()   // 显式市场(历史页本地切换)或跟随全局
  const r = await fetch(`/api/risklight/history${q}`)
  return r.ok ? (await r.json()).history || [] : []
}

import type { Holding } from './types'
export async function fetchFocus(ticker: string): Promise<{ asof: string; ticker: string; holding: Holding }> {
  const r = await fetch(`/api/focus?ticker=${ticker.toUpperCase()}${currentMarket==='cn'?'&market=cn':''}`)
  const j = await r.json()
  if (!r.ok || j.error) throw new Error(j.error || '分析失败')
  return j
}

export async function fetchInvestigate(ticker: string, force = false): Promise<{ ticker: string; key: string; cached: boolean }> {
  const r = await fetch(`/api/investigate${mq(`?ticker=${ticker}${force ? '&force=1' : ''}`)}`)
  const j = await r.json()
  if (!r.ok || j.error) throw new Error(j.error || '背景调查失败')
  return j
}
export async function fetchBlobHTML(key: string): Promise<string> {
  const r = await fetch(`/api/blob?key=${encodeURIComponent(key)}`)
  return r.ok ? r.text() : ''
}
export interface EarnQuarter { period: string; revenue: number | null; net_income: number | null; operating_income: number | null; gross_profit: number | null; eps: number | null; cached?: boolean }
export async function fetchEarningsQuarters(ticker: string): Promise<EarnQuarter[]> {
  const r = await fetch(`/api/earnings/quarters${mq(`?ticker=${ticker}`)}`)
  const j = await r.json()
  if (!r.ok || j.error) throw new Error(j.error || '取财报失败')
  return j.quarters || []
}
export async function fetchEarningsInterpret(ticker: string, period: string, force = false): Promise<{ key: string; cached: boolean }> {
  const r = await fetch(`/api/earnings${mq(`?ticker=${ticker}&period=${period}${force ? '&force=1' : ''}`)}`)
  const j = await r.json()
  if (!r.ok || j.error) throw new Error(j.error || '财报解读失败')
  return j
}

export interface AllocItem { ticker: string; weight: number; shares: number; value: number; reason: string }
export interface AllocResult { mode: string; capital: number; allocations: AllocItem[]; cash_pct: number; note: string }
export async function fetchAIAllocate(tickers: string[], capital: number): Promise<AllocResult> {
  const r = await fetch(`/api/allocate${mq()}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tickers, capital }),
  })
  const j = await r.json()
  if (!r.ok || j.error) throw new Error(j.error || 'AI 分配失败')
  return j
}

export async function fetchCapital(): Promise<number> {
  const r = await fetch(`/api/capital${mq()}`)
  return r.ok ? (await r.json()).capital || 4000 : 4000
}
export async function saveCapital(capital: number): Promise<void> {
  const r = await fetch(`/api/capital${mq()}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ capital }) })
  const j = await r.json().catch(() => ({})); if (!r.ok || j.error) throw new Error(j.error || '保存资金池失败')
}

// A股策略偏好(headline 头号腿·微盘 / dividend 红利低波·大资金,二选一;按用户×市场存)
export type StrategyKey = 'headline' | 'dividend'
export async function fetchStrategy(): Promise<StrategyKey> {
  const r = await fetch(`/api/strategy${mq()}`)
  return r.ok && (await r.json()).strategy === 'dividend' ? 'dividend' : 'headline'
}
export async function saveStrategy(strategy: StrategyKey): Promise<void> {
  const r = await fetch(`/api/strategy${mq()}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ strategy }) })
  const j = await r.json().catch(() => ({})); if (!r.ok || j.error) throw new Error(j.error || '保存策略失败')
}

// ── 新闻模块(只读 overlay,与策略解耦)──
export interface NewsDigest {
  overview?: string
  world?: { title: string; impact: string; tone: string }[]
  domestic?: { title: string; impact: string; tone: string }[]
  market_impact?: { sector: string; reason: string; tone: string }[]
  global_transmission?: { event: string; cn_sectors: string; timing: string; tone: string }[]
}
export async function fetchNewsDigest(): Promise<{ digest_date?: string; digest: NewsDigest | null; n_source?: number }> {
  const r = await fetch(`/api/news/digest${mq()}`)
  if (!r.ok) return { digest: null }
  const j = await r.json()
  return { digest_date: j.digest_date, digest: j.digest ? JSON.parse(j.digest) : null, n_source: j.n_source }
}

export interface CalendarEvent { event_date: string; category: string; title: string; importance: number }
export async function fetchNewsCalendar(): Promise<CalendarEvent[]> {
  const r = await fetch(`/api/news/calendar${mq()}`)
  return r.ok ? (await r.json()).calendar || [] : []
}

// 用户自定义板块专栏(tab 式,每板块完整 digest;用户隔离)
// 板块 digest 复用与综合相同的结构,但 market_impact 换成 stock_impact(个股影响)
export interface SectorDigest {
  overview?: string
  world?: { title: string; impact: string; tone: string }[]
  domestic?: { title: string; impact: string; tone: string }[]
  stock_impact?: { stock: string; reason: string; tone: string }[]
  global_transmission?: { event: string; timing: string; tone: string }[]
}
export async function fetchColumnSectors(): Promise<string[]> {
  const r = await fetch(`/api/news/column${mq()}`)
  return r.ok ? (await r.json()).sectors || [] : []
}
export async function saveColumnSectors(sectors: string[]): Promise<void> {
  await fetch(`/api/news/column${mq()}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sectors }) })
}
export async function fetchSectorDigest(sector: string, refresh = false): Promise<{ digest_date?: string; digest: SectorDigest | null }> {
  const r = await fetch(`/api/news/column/digest${mq(`?sector=${encodeURIComponent(sector)}${refresh ? '&refresh=1' : ''}`)}`)
  const j = await r.json()
  return { digest_date: j.digest_date, digest: j.digest ? JSON.parse(j.digest) : null }
}
// 可点新闻列表(综合=近期宏观;板块=命中板块词)
export interface FeedItem { id: number; title: string; source: string; url: string; published: string }
export async function fetchNewsFeed(sector?: string): Promise<FeedItem[]> {
  const q = sector ? `?sector=${encodeURIComponent(sector)}` : ''
  const r = await fetch(`/api/news/feed${mq(q)}`)
  return r.ok ? (await r.json()).feed || [] : []
}

export interface NewsItemDetail {
  title: string; body: string; url: string; source: string; published: string
  interpret: string; sectors: string[]; ai_error?: string
}
export async function fetchNewsItem(id: number, force = false): Promise<NewsItemDetail> {
  const r = await fetch(`/api/news/item?id=${id}${force ? '&force=1' : ''}`)
  return r.json()
}

// 世界大事/国内大事条目的按需 AI 解读(digest 事件无 news_item id,按标题解读)
export interface EventInterpret { interpret: string; sectors: string[]; ai_error?: string }
export async function fetchEventInterpret(title: string, context: string, force = false): Promise<EventInterpret> {
  const r = await fetch('/api/news/event-interpret', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, context, market: getMarket(), force }),
  })
  return r.json()
}

export interface StockNewsItem { id: number; title: string; source: string; url: string; published: string; relation: string }
export interface NewsFlag { type: string; level: string; text: string; basis: string; note: string }
export interface StockNews {
  ticker: string; news: StockNewsItem[]; summary?: string; flags: NewsFlag[]
  keywords?: { kw: string; weight: number; why: string }[]; disclaimer?: string; note?: string
}
export async function fetchStockNews(ticker: string, refresh = false): Promise<StockNews> {
  const r = await fetch(`/api/news/stock${mq(`?ticker=${ticker}${refresh ? '&refresh=1' : ''}`)}`)
  const j = await r.json()
  let kw
  try { kw = j.keywords_json ? JSON.parse(j.keywords_json) : undefined } catch { kw = undefined }
  return { ticker: j.ticker, news: j.news || [], summary: j.summary, flags: j.flags || [], keywords: kw, disclaimer: j.disclaimer, note: j.note }
}

export interface UniverseItem { ticker: string; cn?: string; sector?: string }
export async function fetchUniverse(): Promise<UniverseItem[]> {
  const r = await fetch(`/api/universe${mq()}`)
  return r.ok ? (await r.json()).universe || [] : []
}

export type TickerMeta = Record<string, { cn: string; sector: string }>
export async function fetchMeta(): Promise<TickerMeta> {
  const r = await fetch('/api/meta')
  return r.ok ? r.json() : {}
}

export async function fetchExplain(ticker: string, force = false): Promise<Explanation> {
  const r = await fetch(`/api/explain${mq(`?ticker=${ticker}${force ? '&force=1' : ''}`)}`)
  const j = await r.json()
  if (!r.ok) throw new Error(j.error || 'AI 讲解失败')
  return j
}
