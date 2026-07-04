// 与 engine/schema.md 对齐的类型(数据契约)
export interface ProbBand {
  median: number
  band70: [number, number]
  stop: number
  target: number
  p_hit_target: number
  p_hit_stop: number
}
export interface Holding {
  ticker: string
  sleeve: 'momentum' | 'SY' | 'both'
  price: number
  base_weight: number
  target_shares: number
  target_value: number
  grade: number
  grade_label: string
  action: string
  action_weight: number
  prob: Record<string, ProbBand>
}
export interface RiskLight {
  level: 'green' | 'amber' | 'red'
  spy_vol: number
  exposure: number
  note: string
}
export interface Snapshot {
  asof: string
  generated_at: string
  capital: number
  disclaimer: string
  risk_light: RiskLight
  holdings: Holding[]
  portfolio: { n_holdings: number; gross_exposure: number; cash_pct: number }
}
