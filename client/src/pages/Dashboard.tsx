import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { Snapshot, Holding } from '../types'
import { pct, pct2, usd, InfoDot, GradeBadge, SleeveBadge, actionColor } from '../ui'

export default function Dashboard({ snap, onSelect }: { snap: Snapshot; onSelect: (t: string) => void }) {
  const chartRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!chartRef.current) return
    const chart = echarts.init(chartRef.current)
    const hs = snap.holdings
    const bands = hs.map((h, i) => ({ value: [i, h.prob['h20'].band70[0] * 100, h.prob['h20'].band70[1] * 100, h.prob['h20'].median * 100], grade: h.grade }))
    chart.setOption({
      backgroundColor: 'transparent',
      grid: { left: 55, right: 20, top: 12, bottom: 40 },
      tooltip: {
        backgroundColor: '#1b2433', borderColor: '#26303f', textStyle: { color: '#e6edf6' },
        formatter: (p: any) => {
          const h = hs[p.data.value[0]]; const b = h.prob['h20']
          return `<b>${h.ticker}</b>（未来20日）<br/>最可能落在：${pct2(b.median)}<br/>70%概率区间：${pct2(b.band70[0])} ~ ${pct2(b.band70[1])}<br/>参考止损 $${b.stop} / 目标 $${b.target}`
        },
      },
      xAxis: { type: 'category', data: hs.map((h) => h.ticker), axisLabel: { color: '#6b7787' }, axisLine: { lineStyle: { color: '#26303f' } } },
      yAxis: { type: 'value', name: '未来20日\n收益范围', nameTextStyle: { color: '#6b7787', fontSize: 10 }, axisLabel: { formatter: '{value}%', color: '#6b7787' }, splitLine: { lineStyle: { color: '#26303f' } } },
      series: [{
        type: 'custom',
        encode: { x: 0, y: [1, 2, 3] }, // 让 y 轴涵盖 上/下沿/中位 全范围(修正正区间被截断)
        renderItem: (params: any, api: any) => {
          const idx = api.value(0)
          const lo = api.coord([idx, api.value(1)]); const hi = api.coord([idx, api.value(2)]); const med = api.coord([idx, api.value(3)])
          const g = bands[params.dataIndex].grade
          const color = g >= 2 ? '#2ecc9b' : g >= 0 ? '#4d9dff' : g === -1 ? '#f5a623' : '#ff5c6c'
          const w = 16
          return { type: 'group', children: [
            { type: 'rect', shape: { x: lo[0] - w / 2, y: hi[1], width: w, height: lo[1] - hi[1] }, style: { fill: color, opacity: 0.3 } },
            { type: 'line', shape: { x1: med[0] - w / 2, y1: med[1], x2: med[0] + w / 2, y2: med[1] }, style: { stroke: color, lineWidth: 2 } },
          ] }
        },
        data: bands,
      }],
    })
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [snap])

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
          <div className="muted">总仓位 {pct(snap.portfolio.gross_exposure)} · 留现金 {pct(snap.portfolio.cash_pct)} · 资金池 {usd(snap.capital)}</div>
        </div>
      </div>

      <div className="card">
        <h3>建议持仓 <span className="muted" style={{ fontWeight: 400 }}>· 点行看详情</span></h3>
        <div className="tbl-scroll">
          <table>
            <thead>
              <tr>
                <th>标的</th>
                <th>选股依据 <InfoDot text="动量=趋势强涨得比大盘好；股东回报=回购分红多；双腿=两者都占。" /></th>
                <th>现价</th>
                <th>建议股数 <InfoDot text="按你的资金池 + 风险平价(波动低的多给点)算出的目标股数,可买碎股。" /></th>
                <th>档位 <InfoDot text="趋势健康度 -3到+3,由7个信号(站上均线/动量/排列等)合成。+1及以上=持有,往下=逐步减仓。" /></th>
                <th>动作 <InfoDot text="档位对应的操作。只减不追涨:走弱才逐档减仓,趋势好就拿住。" /></th>
                <th>未来20日区间 <InfoDot text="未来20天收益的70%概率范围(15%~85%分位)。这是波动范围估计,不是涨跌预测。" /></th>
              </tr>
            </thead>
            <tbody>
              {snap.holdings.map((h: Holding) => {
                const b = h.prob['h20']
                return (
                  <tr key={h.ticker} className="clickable" onClick={() => onSelect(h.ticker)}>
                    <td><b>{h.ticker}</b> <span className="go">›</span></td>
                    <td><SleeveBadge sleeve={h.sleeve} /></td>
                    <td>${h.price}</td>
                    <td>{h.target_shares}</td>
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
        <h3>未来 20 日收益范围图 <InfoDot text="每根竖条=该股未来20天70%概率的收益范围,横线=最可能的中位。条越长说明这股波动越大(不确定性越高)。颜色随档位。这是波动范围,不是方向预测。" /></h3>
        <div ref={chartRef} style={{ height: 300 }} />
        <div className="muted" style={{ marginTop: 6 }}>条越长=波动越大越不确定;这是「可能的波动范围」，不是「会涨会跌」的预测。</div>
      </div>
    </>
  )
}
