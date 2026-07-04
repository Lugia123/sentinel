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

export async function fetchExplain(ticker: string, force = false): Promise<Explanation> {
  const r = await fetch(`/api/explain?ticker=${ticker}${force ? '&force=1' : ''}`)
  const j = await r.json()
  if (!r.ok) throw new Error(j.error || 'AI 讲解失败')
  return j
}
