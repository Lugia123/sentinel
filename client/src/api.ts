import type { Snapshot, Position, PnLResult, Version, HistPoint, Explanation } from './types'

export async function fetchSnapshot(date?: string): Promise<Snapshot> {
  const q = date && date !== 'latest' ? `?date=${date}` : ''
  const r = await fetch(`/api/snapshot${q}`)
  if (!r.ok) throw new Error((await r.json()).error || '读取快照失败')
  return r.json()
}

export async function fetchVersion(): Promise<Version> {
  const r = await fetch('/api/version')
  return r.ok ? r.json() : { version: 'dev', branch: '', commit: '' }
}

export async function runEngine(withSY = true): Promise<string> {
  const r = await fetch(`/api/run?sy=${withSY ? 1 : 0}`, { method: 'POST' })
  const j = await r.json()
  if (!r.ok) throw new Error(j.error || '引擎运行失败')
  return j.log || 'done'
}

export async function fetchPnL(date?: string): Promise<PnLResult> {
  const q = date && date !== 'latest' ? `?date=${date}` : ''
  const r = await fetch(`/api/positions${q}`)
  if (!r.ok) throw new Error((await r.json()).error || '读取持仓失败')
  return r.json()
}

export async function savePositions(ps: Position[]): Promise<void> {
  const r = await fetch('/api/positions', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(ps),
  })
  if (!r.ok) throw new Error((await r.json()).error || '保存持仓失败')
}

export async function fetchHistory(ticker: string, n = 120): Promise<HistPoint[]> {
  const r = await fetch(`/api/history?ticker=${ticker}&n=${n}`)
  if (!r.ok) return []
  return (await r.json()).history || []
}

export async function fetchWatchlist(): Promise<{ ticker: string; source: string }[]> {
  const r = await fetch('/api/watchlist')
  return r.ok ? (await r.json()).watchlist || [] : []
}
export async function addWatch(ticker: string, source = 'ai'): Promise<void> {
  await fetch(`/api/watchlist?ticker=${ticker}&source=${source}`, { method: 'POST' })
}
export async function removeWatch(ticker: string): Promise<void> {
  await fetch(`/api/watchlist?ticker=${ticker}`, { method: 'DELETE' })
}

export interface TrendPoint { date: string; grade: number; price: number; median20: number | null }
export async function fetchTrend(ticker: string, from?: string, to?: string): Promise<TrendPoint[]> {
  const qs = new URLSearchParams({ ticker }); if (from) qs.set('from', from); if (to) qs.set('to', to)
  const r = await fetch(`/api/trend?${qs}`)
  return r.ok ? (await r.json()).points || [] : []
}
// 富序列:每个交易日的多维指标(档位/中位/动量/波动/距高/概率带宽等)
export interface RichTrendPoint {
  date: string; grade: number | null; median20: number | null; mom21: number | null; mom126: number | null
  vol: number | null; pct_from_high: number | null; bandwidth: number | null; price: number | null; sy: number | null
}
export async function fetchTrendRich(tickers: string[]): Promise<Record<string, RichTrendPoint[]>> {
  if (!tickers.length) return {}
  const qs = new URLSearchParams({ tickers: tickers.join(',') })
  const r = await fetch(`/api/trend?${qs}`)
  return r.ok ? (await r.json()).series || {} : {}
}
// 有档位历史的可选股票(供多选下拉)
export async function fetchTrendTickers(): Promise<{ ticker: string; n: number }[]> {
  const r = await fetch('/api/trend/tickers')
  return r.ok ? (await r.json()).tickers || [] : []
}

import type { Holding } from './types'
export async function fetchFocus(ticker: string): Promise<{ asof: string; ticker: string; holding: Holding }> {
  const r = await fetch(`/api/focus?ticker=${ticker.toUpperCase()}`)
  const j = await r.json()
  if (!r.ok || j.error) throw new Error(j.error || '分析失败')
  return j
}

export async function fetchInvestigate(ticker: string, force = false): Promise<{ ticker: string; key: string; cached: boolean }> {
  const r = await fetch(`/api/investigate?ticker=${ticker}${force ? '&force=1' : ''}`)
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
  const r = await fetch(`/api/earnings/quarters?ticker=${ticker}`)
  const j = await r.json()
  if (!r.ok || j.error) throw new Error(j.error || '取财报失败')
  return j.quarters || []
}
export async function fetchEarningsInterpret(ticker: string, period: string, force = false): Promise<{ key: string; cached: boolean }> {
  const r = await fetch(`/api/earnings?ticker=${ticker}&period=${period}${force ? '&force=1' : ''}`)
  const j = await r.json()
  if (!r.ok || j.error) throw new Error(j.error || '财报解读失败')
  return j
}

export interface AllocItem { ticker: string; weight: number; shares: number; value: number; reason: string }
export interface AllocResult { mode: string; capital: number; allocations: AllocItem[]; cash_pct: number; note: string }
export async function fetchAIAllocate(tickers: string[], capital: number): Promise<AllocResult> {
  const r = await fetch('/api/allocate', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tickers, capital }),
  })
  const j = await r.json()
  if (!r.ok || j.error) throw new Error(j.error || 'AI 分配失败')
  return j
}

export async function fetchCapital(): Promise<number> {
  const r = await fetch('/api/capital')
  return r.ok ? (await r.json()).capital || 4000 : 4000
}
export async function saveCapital(capital: number): Promise<void> {
  const r = await fetch('/api/capital', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ capital }) })
  const j = await r.json().catch(() => ({})); if (!r.ok || j.error) throw new Error(j.error || '保存资金池失败')
}

export interface UniverseItem { ticker: string; cn?: string; sector?: string }
export async function fetchUniverse(): Promise<UniverseItem[]> {
  const r = await fetch('/api/universe')
  return r.ok ? (await r.json()).universe || [] : []
}

export type TickerMeta = Record<string, { cn: string; sector: string }>
export async function fetchMeta(): Promise<TickerMeta> {
  const r = await fetch('/api/meta')
  return r.ok ? r.json() : {}
}

export async function fetchExplain(ticker: string, force = false): Promise<Explanation> {
  const r = await fetch(`/api/explain?ticker=${ticker}${force ? '&force=1' : ''}`)
  const j = await r.json()
  if (!r.ok) throw new Error(j.error || 'AI 讲解失败')
  return j
}
