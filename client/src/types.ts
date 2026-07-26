// 与 engine/schema.md 对齐的类型(数据契约)
export interface ProbBand {
  median: number
  band70: [number, number]
  stop: number
  target: number
  p_hit_target: number
  p_hit_stop: number
}
export interface Signal { name: string; detail: string; verdict: '多' | '空' | '中' }
export interface Indicators {
  // 美股(us 快照)
  mom126?: number | null; mom21?: number | null; vol_annual?: number | null
  sma20?: number; sma50?: number; sma200?: number
  pct_from_high?: number; sy_yield?: number | null
  // A股(cn 快照:头号腿/事件腿指标)
  float_mktcap_yi?: number | null; turn20?: number | null; event_score?: number | null
}
export interface Holding {
  ticker: string
  name?: string  // A股中文名(cn 快照自带;us 走 meta 映射)
  sleeve: 'momentum' | 'SY' | 'both' | 'custom' | 'focus' | 'smallcap' | 'event'
  price: number
  base_weight: number
  target_shares: number
  target_value: number
  grade: number
  grade_label: string
  action: string
  action_weight: number
  prob: Record<string, ProbBand>
  reason?: string
  signals?: Signal[]
  indicators?: Indicators
}
export interface RiskLight {
  level: 'green' | 'amber' | 'red'
  spy_vol: number
  exposure: number
  note: string
}
export interface Snapshot {
  market?: 'us' | 'cn'  // v2.0 双市场(缺=us)
  asof: string
  generated_at: string
  capital: number
  disclaimer: string
  risk_light: RiskLight
  holdings: Holding[]
  portfolio: { n_holdings: number; gross_exposure: number; cash_pct: number }
}

export interface Position { ticker: string; shares: number; cost: number }
export interface PnLRow extends Position {
  price: number; priced: boolean
  market_value: number; cost_value: number; pnl: number; pnl_pct: number
}
export interface PnLResult {
  asof: string
  positions: PnLRow[]
  summary: { market_value: number; cost_value: number; pnl: number; pnl_pct: number }
}
export interface Version { version: string; branch: string; commit: string }
// sma_mid:美股=50日线,A股=60日线(后端 /api/history 的 mid_window 指明窗口)
export interface HistPoint { date: string; close: number | null; sma20: number | null; sma_mid: number | null; sma200: number | null }
export interface Explanation { ticker: string; asof: string; content: string; cached: boolean }
