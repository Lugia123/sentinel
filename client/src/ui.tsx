import { useState, type MouseEvent } from 'react'
import { createPortal } from 'react-dom'

export const pct = (x: number) => `${(x * 100).toFixed(1)}%`
export const pct2 = (x: number) => `${x >= 0 ? '+' : ''}${(x * 100).toFixed(1)}%`
export const usd = (x: number) => `$${x.toLocaleString('en-US', { maximumFractionDigits: 2 })}`

// 选股依据(腿)中文 + 说明
export const SLEEVE: Record<string, { label: string; hint: string; cls: string }> = {
  momentum: { label: '动量', hint: '因“趋势强、涨得比大盘好”被选中(动量腿)', cls: 'b-mom' },
  SY: { label: '股东回报', hint: '因“回购+分红多、回报股东”被选中(股东收益率腿)', cls: 'b-sy' },
  both: { label: '双腿', hint: '两条腿都选中它(趋势强 且 股东回报高)', cls: 'b-both' },
  // A股·头号腿(微盘):小市值×低换手
  smallcap: { label: '头号腿', hint: '因“小市值 + 低换手”被选中(头号腿·微盘,小资金)', cls: 'b-mom' },
  event: { label: '事件腿', hint: '因“分析师上修 + 业绩预告惊喜”被选中(size中性合成,容量友好)', cls: 'b-sy' },
  // A股·红利低波(大资金替代腿):高股息×低波
  dividend: { label: '红利低波', hint: '因“高股息 × 低波动”被选中(红利低波·大资金替代腿,与头号腿二选一)', cls: 'b-div' },
  custom: { label: '自选·追踪', hint: '你「添加自定义股票」加入的:非策略选中,但每天也算档位/概率(不占策略仓位,建议股数为0)', cls: 'b-custom' },
}

export const gradeCls = (g: number) => (g >= 2 ? 'g-3' : g >= 0 ? 'g-1' : g === -1 ? 'g-neg1' : 'g-neg2')
export const actionColor = (a: string) => (a.includes('清仓') ? 'var(--down)' : a.includes('减') ? 'var(--warn)' : 'var(--up)')

// A股单票不减仓(反转市,逐票减仓有害·R36),动作由【市场级风险灯】统一决定——
// 引擎里 action 恒"持有"只是占位,展示时必须翻译成市场级指令,否则用户会以为无论如何都拿着。
export const cnMarketAction = (level: string): { text: string; color: string } =>
  level === 'red' ? { text: '清仓观望', color: 'var(--down)' }
  : level === 'amber' ? { text: '减至半仓', color: 'var(--warn)' }
  : { text: '持有', color: 'var(--up)' }
export const verdictCls = (v: string) => (v === '多' ? 'up' : v === '空' ? 'down' : 'muted')

// 悬浮说明小圆点 —— tooltip 用 fixed 定位跟随触发点,绝不被表格 overflow 裁掉
export function InfoDot({ text }: { text: string }) {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)
  const enter = (e: MouseEvent) => {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
    setPos({ x: r.left + r.width / 2, y: r.top - 6 })
  }
  return (
    <span className="infodot" onMouseEnter={enter} onMouseLeave={() => setPos(null)}>
      ?
      {pos && createPortal(
        <span className="tip-fixed" style={{ left: pos.x, top: pos.y }}>{text}</span>,
        document.body,
      )}
    </span>
  )
}

export function GradeBadge({ g, label }: { g: number; label?: string }) {
  return <span className={`pill ${gradeCls(g)}`}>{g >= 0 ? `+${g}` : g}{label ? ` ${label}` : ''}</span>
}

export function SleeveBadge({ sleeve }: { sleeve: string }) {
  const s = SLEEVE[sleeve] || { label: sleeve, hint: '', cls: '' }
  return <span className={`pill ${s.cls}`} title={s.hint}>{s.label}</span>
}
