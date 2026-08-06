import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchSectorFlow, type SectorFlow, type SectorItem } from '../api'
import { InfoDot, riseColor, fallColor, cssVar } from '../ui'
import MacroFlow from '../components/MacroFlow'

// 「资金流」页 —— 三尺度资金全景(纯展示,不进策略)。
// P2 板块资金热力(本文件):行业净流入排行 + 全景 treemap + 近5日持续吸金榜。
// P3(后续):大盘 + 北向 区块接入本页顶部。
const yi = (x: number | null | undefined) => (x == null ? '—' : `${x >= 0 ? '+' : ''}${x.toFixed(1)}亿`)

// 双向横条排行:正=流入(涨色/右),负=流出(跌色/左)
function RankBars({ items, field }: { items: SectorItem[]; field: 'net' | 'net5' }) {
  const max = Math.max(...items.map((i) => Math.abs(i[field])), 0.01)
  return (
    <div className="sf-rank">
      {items.map((it) => {
        const v = it[field]
        const w = (Math.abs(v) / max) * 100
        return (
          <div className="sf-row" key={it.name}>
            <span className="sf-name" title={it.name}>{it.name}</span>
            <div className="sf-track">
              <div className="sf-bar" style={{ [v >= 0 ? 'left' : 'right']: '50%', width: `${w / 2}%`, background: v >= 0 ? 'var(--rise)' : 'var(--fall)' } as any} />
            </div>
            <span className={`sf-amt ${v >= 0 ? 'up' : 'down'}`}>{yi(v)}</span>
          </div>
        )
      })}
    </div>
  )
}

export default function MoneyFlowPage() {
  const [sf, setSf] = useState<SectorFlow | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState(false)
  const treeRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let alive = true
    setLoading(true); setErr(false)
    fetchSectorFlow().then((d) => { if (!alive) return; if (d) setSf(d); else setErr(true); setLoading(false) })
    return () => { alive = false }
  }, [])

  // 全景 treemap:面积=|今日净额|,颜色=方向(涨色入/跌色出),取 |net| 前 40
  useEffect(() => {
    if (!treeRef.current || !sf) return
    const chart = echarts.init(treeRef.current)
    const rise = riseColor(), fall = fallColor(), border = cssVar('--bg') || '#0c0a07'
    const top = [...sf.industries].sort((a, b) => Math.abs(b.net) - Math.abs(a.net)).slice(0, 40)
    const data = top.map((i) => ({
      name: i.net >= 0 ? `${i.name}\n+${i.net.toFixed(0)}亿` : `${i.name}\n${i.net.toFixed(0)}亿`,
      value: Math.abs(i.net),
      itemStyle: { color: i.net >= 0 ? rise : fall },
    }))
    chart.setOption({
      backgroundColor: 'transparent',
      tooltip: { backgroundColor: '#1f1913', borderColor: '#2c2418', textStyle: { color: '#f1e9da' }, formatter: (p: any) => p.name.replace('\n', ' ') },
      series: [{
        type: 'treemap', data, roam: false, nodeClick: false, breadcrumb: { show: false },
        width: '100%', height: '100%', top: 2, left: 2, right: 2, bottom: 2,
        label: { color: '#0c0a07', fontSize: 11, fontWeight: 600, overflow: 'truncate' },
        itemStyle: { borderColor: border, borderWidth: 2, gapWidth: 2 },
        emphasis: { label: { color: '#0c0a07' } },
      }],
    })
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [sf])

  if (loading) return <div className="card muted">资金流数据加载中…</div>
  if (err || !sf) return <div className="card"><h3>资金流</h3><div className="muted">板块资金流暂不可用（数据接口故障或非交易日）。</div></div>

  const ind = sf.industries
  const inflow = ind.filter((i) => i.net > 0).slice(0, 12)
  const outflow = [...ind].filter((i) => i.net < 0).sort((a, b) => a.net - b.net).slice(0, 12)
  const cum = [...ind].sort((a, b) => b.net5 - a.net5).slice(0, 12)

  return (
    <>
      <div className="sub" style={{ marginBottom: 14 }}>
        资金流全景 · 数据截至 {sf.asof} · 纯展示，非投资建议
      </div>

      {/* 大盘 + 北向(P3)*/}
      <MacroFlow />

      <div className="card">
        <div className="sf-head">
          <h3>板块资金热力 · 行业 <InfoDot text="东财行业板块主力净流入(超大单+大单)。面积图=今日全景(面积=净额大小,颜色=方向);左右榜=今日流入/流出前列;吸金榜=近5日累计(重累计,连续流入比单日更有意义)。颜色随你的涨跌配色。纯展示,非投资建议。" /></h3>
          <span className="muted" style={{ fontSize: 12 }}>今日 {ind.length} 个行业 · 近{sf.days}日</span>
        </div>

        {/* 全景 treemap */}
        <div className="sf-sub">全行业全景（面积=今日主力净额，颜色=方向）</div>
        <div ref={treeRef} style={{ height: 320 }} />

        {/* 今日 流入/流出 双榜 */}
        <div className="sf-cols">
          <div>
            <div className="sf-sub">今日主力净流入 · 前12</div>
            <RankBars items={inflow} field="net" />
          </div>
          <div>
            <div className="sf-sub">今日主力净流出 · 前12</div>
            <RankBars items={outflow} field="net" />
          </div>
        </div>

        {/* 近5日持续吸金榜 */}
        <div className="sf-sub" style={{ marginTop: 16 }}>持续吸金榜 · 近{sf.days}日主力净流入累计 · 前12</div>
        <RankBars items={cum} field="net5" />
      </div>
    </>
  )
}
