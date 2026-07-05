import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchTrend, fetchTrendMulti, type TrendPoint } from '../api'
import type { TickerMeta } from '../api'
import { InfoDot } from '../ui'

const C = ['#c8a253', '#6fae86', '#cf6f5d', '#9a8ec4', '#7ba7b0', '#e6c878']

export default function Trends({ meta, watch }: { meta: TickerMeta; watch: Set<string> }) {
  const [mode, setMode] = useState<'single' | 'multi'>('single')
  const [tk, setTk] = useState('AMD')
  const [multiInput, setMultiInput] = useState('')
  const [single, setSingle] = useState<TrendPoint[]>([])
  const [multi, setMulti] = useState<Record<string, { date: string; grade: number }[]>>({})
  const ref = useRef<HTMLDivElement>(null)

  const loadSingle = async (t: string) => setSingle(await fetchTrend(t.trim().toUpperCase()))
  const loadMulti = async (ts: string[]) => setMulti(await fetchTrendMulti(ts))
  useEffect(() => { loadSingle('AMD') }, [])

  // 多股默认用关注列表
  const doMulti = () => {
    const ts = (multiInput.trim() ? multiInput.split(/[,，\s]+/) : Array.from(watch)).filter(Boolean)
    if (ts.length) loadMulti(ts.map((s) => s.toUpperCase()))
  }

  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    if (mode === 'single') {
      chart.setOption({
        backgroundColor: 'transparent', grid: { left: 45, right: 50, top: 30, bottom: 30 },
        legend: { textStyle: { color: '#aeb9c9' }, top: 0 },
        tooltip: { trigger: 'axis', backgroundColor: '#1b2433', borderColor: '#26303f', textStyle: { color: '#e6edf6' } },
        xAxis: { type: 'category', data: single.map((p) => p.date.slice(5)), axisLabel: { color: '#6b7787' }, axisLine: { lineStyle: { color: '#26303f' } } },
        yAxis: [
          { type: 'value', name: '档位', min: -3, max: 3, interval: 1, position: 'left', axisLabel: { color: '#c8a253' }, splitLine: { lineStyle: { color: '#241d15' } } },
          { type: 'value', name: '20日中位%', position: 'right', axisLabel: { color: '#6fae86', formatter: (v: number) => (v * 100).toFixed(0) + '%' }, splitLine: { show: false } },
        ],
        series: [
          { name: '档位', type: 'line', step: 'end', symbol: 'none', lineStyle: { color: '#c8a253', width: 2 }, data: single.map((p) => p.grade) },
          { name: '20日中位', type: 'line', yAxisIndex: 1, showSymbol: false, lineStyle: { color: '#6fae86' }, data: single.map((p) => p.median20) },
        ],
      })
    } else {
      const keys = Object.keys(multi)
      chart.setOption({
        backgroundColor: 'transparent', grid: { left: 45, right: 20, top: 30, bottom: 30 },
        legend: { textStyle: { color: '#aeb9c9' }, top: 0 },
        tooltip: { trigger: 'axis', backgroundColor: '#1b2433', borderColor: '#26303f', textStyle: { color: '#e6edf6' } },
        xAxis: { type: 'time', axisLabel: { color: '#6b7787' }, axisLine: { lineStyle: { color: '#26303f' } } },
        yAxis: { type: 'value', name: '档位', min: -3, max: 3, interval: 1, axisLabel: { color: '#6b7787' }, splitLine: { lineStyle: { color: '#241d15' } } },
        series: keys.map((k, i) => ({
          name: k + (meta[k] ? ' ' + meta[k].cn : ''), type: 'line', step: 'end', showSymbol: false,
          lineStyle: { color: C[i % C.length] }, data: multi[k].map((p) => [p.date, p.grade]),
        })),
      })
    }
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [single, multi, mode])

  return (
    <>
      <div className="hint">
        📈 看股票的<b>历史分析走势</b>：档位怎么变、20日中位怎么走。数据来自每天回填的策略快照。
        <b>注意</b>：某股只在「被策略选中」的日子有档位，所以常被选的股(如 AMD/INTC)走势连续，偶尔选中的会有断点。
      </div>
      <div className="tabs">
        <button className={mode === 'single' ? 'active' : ''} onClick={() => setMode('single')}>单股走势</button>
        <button className={mode === 'multi' ? 'active' : ''} onClick={() => setMode('multi')}>多股对比</button>
      </div>

      {mode === 'single' ? (
        <div className="card">
          <div className="pos-add">
            <input placeholder="代码 如 AMD" value={tk} onChange={(e) => setTk(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && loadSingle(tk)} />
            <button className="ghost" onClick={() => loadSingle(tk)}>查走势</button>
            <InfoDot text="金线=档位(-3~+3,左轴),绿线=未来20日中位收益(右轴)。看这只股的健康度随时间怎么变。" />
          </div>
          {single.length === 0 && <div className="muted">该股在回填区间内没有被选中的记录(试 AMD/INTC/MO 等常被选的)。</div>}
          <div ref={ref} style={{ height: 340 }} />
        </div>
      ) : (
        <div className="card">
          <div className="pos-add">
            <input placeholder="多个代码逗号分隔,留空用关注列表" value={multiInput} onChange={(e) => setMultiInput(e.target.value)} style={{ width: 220 }} onKeyDown={(e) => e.key === 'Enter' && doMulti()} />
            <button className="ghost" onClick={doMulti}>对比档位</button>
            <InfoDot text="对比多只股票的档位走势。留空则用你的关注列表。" />
          </div>
          {Object.keys(multi).length === 0 && <div className="muted">输入代码或先关注几只,点「对比档位」。</div>}
          <div ref={ref} style={{ height: 340 }} />
        </div>
      )}
    </>
  )
}
