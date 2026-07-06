import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import type { Snapshot, Holding } from '../types'
import type { TickerMeta } from '../api'
import { pct, pct2, usd, InfoDot, GradeBadge, SleeveBadge, actionColor } from '../ui'
import SearchSelect, { type SearchOption } from '../components/SearchSelect'
import AllocateModal from '../components/AllocateModal'
import { fetchUniverse, saveCapital, type UniverseItem } from '../api'

export default function Dashboard({ snap, meta, watch, onToggleWatch, onSelect, onCustom, onReload }: {
  snap: Snapshot; meta: TickerMeta; watch: Set<string>
  onToggleWatch: (t: string, on: boolean) => void; onSelect: (t: string) => void; onCustom: (t: string) => void
  onReload: () => void
}) {
  const chartRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(false)
  // 资金池(每用户可编辑;改后重算缩放的快照)
  const [capEdit, setCapEdit] = useState(false)
  const [capVal, setCapVal] = useState(String(snap.capital))
  const [capBusy, setCapBusy] = useState(false)
  const saveCap = async () => {
    const v = parseFloat(capVal)
    if (!(v >= 1)) return
    setCapBusy(true)
    try { await saveCapital(v); await onReload() } catch { /* ignore */ }
    setCapBusy(false); setCapEdit(false)
  }
  const pickCustom = async (tk: string) => { setLoading(true); await onCustom(tk); setLoading(false) }
  // 建议股数分配(覆盖):alloc 非空时列表显示分配结果而非策略默认股数
  const [allocOpen, setAllocOpen] = useState(false)
  const [alloc, setAlloc] = useState<Record<string, number> | null>(null)
  const [allocNote, setAllocNote] = useState('')
  // 关注的置顶(保持各自组内原顺序)
  const rows = [...snap.holdings].sort((a, b) => (watch.has(b.ticker) ? 1 : 0) - (watch.has(a.ticker) ? 1 : 0))
  // 可添加的自定义股 = 全部可分析股(数据池1393只)里尚未在列表的(不再只限98大盘股)
  const [universe, setUniverse] = useState<UniverseItem[]>([])
  useEffect(() => { fetchUniverse().then(setUniverse) }, [])
  const heldSet = new Set(snap.holdings.map((h) => h.ticker))
  const addable: SearchOption[] = universe
    .filter((u) => !heldSet.has(u.ticker))
    .map((u) => ({ value: u.ticker, label: u.ticker, sub: u.cn ? `${u.cn}${u.sector ? ' · ' + u.sector : ''}` : '', keywords: u.cn }))
  // 横向布局:每股一行(按档位→中位排序),行多时容器内竖向滚动,不再横向挤成一团
  const rowH = 26
  const chartH = Math.max(240, snap.holdings.length * rowH + 60)
  useEffect(() => {
    if (!chartRef.current) return
    const chart = echarts.init(chartRef.current)
    // 排序:档位高的在上,同档位按中位收益降序
    const hs = [...snap.holdings].sort((a, b) => b.grade - a.grade || b.prob['h20'].median - a.prob['h20'].median)
    const bands = hs.map((h, i) => ({ value: [i, h.prob['h20'].band70[0] * 100, h.prob['h20'].band70[1] * 100, h.prob['h20'].median * 100], grade: h.grade }))
    const label = (i: number) => hs[i].ticker + (meta[hs[i].ticker] ? ' ' + meta[hs[i].ticker].cn : '')
    // 左轴宽度自适应:按最长标签估算像素(中文≈13px,其余≈7.5px @12px字号),避免长名被遮挡
    const labelPx = (s: string) => [...s].reduce((w, c) => w + (/[一-鿿]/.test(c) ? 13 : 7.5), 0)
    const gridLeft = Math.min(200, Math.max(90, Math.ceil(Math.max(...hs.map((_, i) => labelPx(label(i))))) + 18))
    chart.setOption({
      backgroundColor: 'transparent',
      grid: { left: gridLeft, right: 24, top: 26, bottom: 30 },
      tooltip: {
        backgroundColor: '#1f1913', borderColor: '#2c2418', textStyle: { color: '#f1e9da' },
        formatter: (p: any) => {
          const h = hs[p.data.value[0]]; const b = h.prob['h20']
          return `<b>${h.ticker}</b>（未来20日）<br/>最可能落在：${pct2(b.median)}<br/>70%概率区间：${pct2(b.band70[0])} ~ ${pct2(b.band70[1])}<br/>参考止损 $${b.stop} / 目标 $${b.target}`
        },
      },
      xAxis: { type: 'value', name: '收益范围', nameTextStyle: { color: '#b0a488', fontSize: 12 }, axisLabel: { formatter: '{value}%', color: '#b0a488' }, splitLine: { lineStyle: { color: '#241d15' } } },
      yAxis: {
        type: 'category', inverse: true, data: hs.map((_, i) => label(i)),
        axisLabel: { color: '#b0a488', fontSize: 12 }, axisLine: { lineStyle: { color: '#2c2418' } }, axisTick: { show: false },
      },
      series: [{
        type: 'custom',
        encode: { x: [1, 2, 3], y: 0 },
        renderItem: (params: any, api: any) => {
          const cat = api.value(0)
          const lo = api.coord([api.value(1), cat]); const hi = api.coord([api.value(2), cat]); const med = api.coord([api.value(3), cat])
          const g = bands[params.dataIndex].grade
          const color = g >= 2 ? '#6fae86' : g >= -1 ? '#c8a253' : '#cf6f5d' // 颜色=档位健康度
          const bh = 13, y = lo[1] - bh / 2
          return { type: 'group', children: [
            { type: 'rect', shape: { x: lo[0], y, width: hi[0] - lo[0], height: bh }, style: { fill: color, opacity: 0.32 } },
            { type: 'line', shape: { x1: med[0], y1: y, x2: med[0], y2: y + bh }, style: { stroke: color, lineWidth: 2 } },
          ] }
        },
        data: bands,
      }],
    })
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [snap, meta])

  const rl = snap.risk_light
  return (
    <>
      <div className="hint">
        👉 这是策略<b>今天算出来的建议持仓</b>。每一行是一只股票：<b>档位</b>越高越健康，<b>动作</b>告诉你该拿住还是减。
        <b>点任意一行</b>看它的详细指标 + AI 讲解「为什么选它」。这是研究工具，最终自己决定。
      </div>

      <div className="row">
        <div className="card">
          <div className="muted">风险灯 <InfoDot text="看整体市场波动大不大。绿=正常可满仓，黄=波动偏高建议降点仓，红=波动很大大幅降仓。它管的是总仓位，不针对单只股。" /></div>
          <div className="big"><span className={`light ${rl.level}`} />{rl.note}</div>
          <div className="muted">大盘(SPY)年化波动 {pct(rl.spy_vol)} · 建议总仓位 {pct(rl.exposure)}</div>
        </div>
        <div className="card">
          <div className="muted">策略建议组合</div>
          <div className="big">{snap.portfolio.n_holdings} 只</div>
          <div className="muted">总仓位 {pct(snap.portfolio.gross_exposure)} · 留现金 {pct(snap.portfolio.cash_pct)}</div>
        </div>
        <div className="card">
          <div className="muted">我的资金池 <InfoDot text="你的可投金额。建议股数按它×风险平价算,改了会立刻按比例重算(每个用户独立)。" /></div>
          {!capEdit ? (
            <>
              <div className="big">{usd(snap.capital)}</div>
              <button className="ghost mini" onClick={() => { setCapVal(String(snap.capital)); setCapEdit(true) }}>✎ 编辑</button>
            </>
          ) : (
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 4, flexWrap: 'wrap' }}>
              <span className="muted">$</span>
              <input value={capVal} onChange={(e) => setCapVal(e.target.value.replace(/[^0-9.]/g, ''))}
                onKeyDown={(e) => e.key === 'Enter' && saveCap()} style={{ width: 100 }} autoFocus />
              <button className="primary" onClick={saveCap} disabled={capBusy}>{capBusy ? '…' : '保存'}</button>
              <button className="ghost mini" onClick={() => setCapEdit(false)}>取消</button>
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginBottom: 6 }}>
          <h3 style={{ margin: 0 }}>建议持仓 <span className="muted" style={{ fontWeight: 400 }}>· 点行看详情 · ★关注置顶</span></h3>
          <div className="pos-add" style={{ margin: 0 }}>
            <SearchSelect options={addable} onPick={pickCustom} disabled={loading}
              placeholder={loading ? '分析中…' : '添加自定义股票:输代码或中文名'}
              emptyText="没有匹配的可添加股票(或已在列表中)" />
            <InfoDot text="从有数据的股票里搜索添加(输代码或中文名)。已在列表里的不再出现。选中后用同一套档位/概率规则分析它,并纳入关注。" />
          </div>
        </div>
        {alloc && (
          <div className="alloc-banner">
            ⚖ 已应用<b>自定义分配</b>{allocNote ? ` · ${allocNote}` : ''}(建议股数列已按分配显示,未分配的为 0)
            <button className="linkbtn" onClick={() => { setAlloc(null); setAllocNote('') }}>恢复策略默认</button>
          </div>
        )}
        <div className="tbl-scroll">
          <table>
            <thead>
              <tr>
                <th></th>
                <th>标的</th>
                <th>板块</th>
                <th>选股依据 <InfoDot text="动量=趋势强涨得比大盘好；股东回报=回购分红多；双腿=两者都占。" /></th>
                <th>现价</th>
                <th>建议股数 <InfoDot text="按你的资金池 + 风险平价(波动低的多给点)算出的目标股数,可买碎股。点右侧「分配」可自选股票重算或用AI分配。" />
                  <button className="th-btn" onClick={() => setAllocOpen(true)}>⚖ 分配</button></th>
                <th>档位 <InfoDot text="趋势健康度 -3到+3,由7个信号(站上均线/动量/排列等)合成。+1及以上=持有,往下=逐步减仓。" /></th>
                <th>动作 <InfoDot text="档位对应的操作。只减不追涨:走弱才逐档减仓,趋势好就拿住。" /></th>
                <th>未来20日区间 <InfoDot text="未来20天收益的70%概率范围(15%~85%分位)。这是波动范围估计,不是涨跌预测。" /></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((h: Holding) => {
                const b = h.prob['h20']
                const on = watch.has(h.ticker)
                const m = meta[h.ticker]
                return (
                  <tr key={h.ticker} className="clickable" onClick={() => onSelect(h.ticker)}>
                    <td onClick={(e) => { e.stopPropagation(); onToggleWatch(h.ticker, !on) }} style={{ cursor: 'pointer', textAlign: 'center' }}>
                      <span className={on ? 'star on' : 'star'}>{on ? '★' : '☆'}</span>
                    </td>
                    <td><b>{h.ticker}</b>{m && <span className="cn">{m.cn}</span>} <span className="go">›</span></td>
                    <td className="muted">{m?.sector || '—'}</td>
                    <td><SleeveBadge sleeve={h.sleeve} /></td>
                    <td>${h.price}</td>
                    <td className={alloc ? (alloc[h.ticker] ? 'gold' : 'muted') : ''}>{alloc ? (alloc[h.ticker] ?? 0) : h.target_shares}</td>
                    <td><GradeBadge g={h.grade} label={h.grade_label} /></td>
                    <td style={{ color: actionColor(h.action), fontWeight: 600 }}>{h.action}</td>
                    <td className="muted">{pct2(b.band70[0])} ~ {pct2(b.band70[1])}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h3>未来 20 日收益范围图 <InfoDot text="每行=一只股票未来20天70%概率的收益范围,竖线=最可能的中位。按档位从高到低排序。这是波动范围,不是方向预测。" /></h3>
        <div style={{ maxHeight: 520, overflowY: 'auto' }}>
          <div ref={chartRef} style={{ height: chartH }} />
        </div>
        <div className="chart-legend">
          <span><i className="lg" style={{ background: '#6fae86' }} />绿=偏强(+2~+3)</span>
          <span><i className="lg" style={{ background: '#c8a253' }} />金=中性/转弱(-1~+1)</span>
          <span><i className="lg" style={{ background: '#cf6f5d' }} />红=跌势(-2~-3)</span>
        </div>
        <div className="muted" style={{ marginTop: 6 }}>
          <b>每行一只股</b>(按档位从高到低排),<b>颜色=档位健康度</b>,<b>横条长度=波动大小</b>——两者独立:红色不代表条短,只代表趋势转弱。股票多时可在框内滚动。这是波动范围,非涨跌预测。
        </div>
      </div>

      {allocOpen && (
        <AllocateModal holdings={snap.holdings} meta={meta} capital={snap.capital} exposure={rl.exposure}
          onApply={(m, note) => { setAlloc(m); setAllocNote(note) }} onClose={() => setAllocOpen(false)} />
      )}
    </>
  )
}
