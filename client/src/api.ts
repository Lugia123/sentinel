import type { Snapshot } from './types'

export async function fetchSnapshot(date?: string): Promise<Snapshot> {
  const q = date && date !== 'latest' ? `?date=${date}` : ''
  const r = await fetch(`/api/snapshot${q}`)
  if (!r.ok) throw new Error((await r.json()).error || '读取快照失败')
  return r.json()
}

export async function fetchDates(): Promise<string[]> {
  const r = await fetch('/api/snapshot/dates')
  if (!r.ok) return []
  return (await r.json()).dates || []
}

export async function runEngine(withSY = true): Promise<string> {
  const r = await fetch(`/api/run?sy=${withSY ? 1 : 0}`, { method: 'POST' })
  const j = await r.json()
  if (!r.ok) throw new Error(j.error || '引擎运行失败')
  return j.log || 'done'
}
