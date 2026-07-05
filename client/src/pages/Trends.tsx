import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchTrendRich, fetchTrendTickers, type RichTrendPoint } from '../api'
import type { TickerMeta } from '../api'
import Select from '../components/Select'
import MultiSelect from '../components/MultiSelect'
import type { SearchOption } from '../components/SearchSelect'
import { InfoDot } from '../ui'

const C = ['#c8a253', '#6fae86', '#cf6f5d', '#9a8ec4', '#7ba7b0', '#e6c878', '#d19a66', '#84b6c4']

// 可切换的分析维度(都来自每日快照,挖出来对比)
const METRICS = [
  { key: 'grade', label: '档位(-3 ~ +3)', pct: false, fixed: true },
  { key: 'median20', label: '未来20日中位预测', pct: true, fixed: false },
  { key: 'mom21', label: '近21日动量', pct: true, fixed: false },
  { key: 'mom126', label: '近半年动量', pct: true, fixed: false },
  { key: 'vol', label: '年化波动率', pct: true, fixed: false },
  { key: 'pct_from_high', label: '距52周高', pct: true, fixed: false },
  { key: 'bandwidth', label: '概率带宽(不确定性)', pct: true, fixed: false },
] as const
type MetricKey = typeof METRICS[number]['key']

export default function Trends({ meta, watch }: { meta: TickerMeta; watch: Set<string> }) {
  const [avail, setAvail] = useState<SearchOption[]>([])
  const [sel, setSel] = useState<string[]>([])
  const [metric, setMetric] = useState<MetricKey>('grade')
  const [series, setSeries] = useState<Record<string, RichTrendPoint[]>>({})
  const ref = useRef<HTMLDivElement>(null)

  // 初始化:拉可选股票(有档位历史),默认选样本最多的3只(优先关注列表里的)
  useEffect(() => {
    fetchTrendTickers().then((ts) => {
      const opts = ts.map((t): SearchOption => ({
        value: t.ticker, label: t.ticker,
        sub: (meta[t.ticker]?.cn || '') + ` · ${t.n}天`, keywords: meta[t.ticker]?.cn,
      }))
      setAvail(opts)
      const watched = ts.filter((t) => watch.has(t.ticker)).map((t) => t.ticker)
      const def = (watched.length ? watched : ts.map((t) => t.ticker)).slice(0, 3)
      setSel(def)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta])

  useEffect(() => { fetchTrendRich(sel).then(setSeries) }, [sel])

  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    const m = METRICS.find((x) => x.key === metric)!
    const keys = Object.keys(series)
    chart.setOption({
      backgroundColor: 'transparent', grid: { left: 52, right: 20, top: 34, bottom: 30 },
      legend: { textStyle: { color: '#bcae97' }, top: 0 },
      tooltip: {
        trigger: 'axis', backgroundColor: '#1f1913', borderColor: '#2c2418', textStyle: { color: '#f1e9da' },
        valueFormatter: (v: any) => (v == null ? '—' : m.pct ? (v * 100).toFixed(1) + '%' : String(v)),
      },
      xAxis: { type: 'time', axisLabel: { color: '#b0a488' }, axisLine: { lineStyle: { color: '#2c2418' } } },
      yAxis: {
        type: 'value', name: m.label, nameTextStyle: { color: '#b0a488', fontSize: 12 },
        ...(m.fixed ? { min: -3, max: 3, interval: 1 } : {}),
        axisLabel: { color: '#b0a488', formatter: (v: number) => (m.pct ? (v * 100).toFixed(0) + '%' : String(v)) },
        splitLine: { lineStyle: { color: '#241d15' } },
      },
      series: keys.map((k, i) => ({
        name: k + (meta[k] ? ' ' + meta[k].cn : ''), type: 'line', step: metric === 'grade' ? 'end' : false,
        showSymbol: false, connectNulls: false,
        lineStyle: { color: C[i % C.length], width: 2 }, itemStyle: { color: C[i % C.length] },
        data: (series[k] || []).map((p) => [p.date, (p as any)[metric]]),
      })),
    })
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [series, metric, meta])

  return (
    <>
      <div className="hint">
        📈 挑几只股票,选一个<b>分析维度</b>,看它们随时间怎么变化。所有维度都来自每天回填的策略快照。
        <b>注意</b>:只有「被策略选中过」的交易日才有数据,所以常被选的股(如 AMD/INTC)曲线连续,偶尔选中的会有断点。
      </div>
      <div className="card">
        <div className="trend-ctl">
          <div>
            <div className="ctl-lbl">股票(可多选,最多8只) <InfoDot text="只列有档位历史的股票(策略选中过的)。输代码或中文名搜索。" /></div>
            <MultiSelect value={sel} options={avail} onChange={setSel} placeholder="搜索添加股票…" max={8} />
          </div>
          <div>
            <div className="ctl-lbl">分析维度</div>
            <Select value={metric} onChange={(v) => setMetric(v as MetricKey)}
              options={METRICS.map((m) => ({ value: m.key, label: m.label }))} ariaLabel="分析维度" />
          </div>
        </div>
        {sel.length === 0 && <div className="muted" style={{ marginTop: 12 }}>上面搜索添加股票开始对比。</div>}
        <div ref={ref} style={{ height: 380, marginTop: 8 }} />
      </div>
    </>
  )
}
