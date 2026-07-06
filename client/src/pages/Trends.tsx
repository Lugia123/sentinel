import { useEffect, useState } from 'react'
import { fetchTrendRich, fetchTrendTickers, type RichTrendPoint } from '../api'
import type { TickerMeta } from '../api'
import MultiSelect from '../components/MultiSelect'
import TrendChart, { type MetricDef } from '../components/TrendChart'
import type { SearchOption } from '../components/SearchSelect'
import { InfoDot } from '../ui'

// 可选的分析维度(都来自每日快照,挖出来对比)
const METRICS: MetricDef[] = [
  { key: 'grade', label: '档位(-3 ~ +3)', pct: false, fixed: true },
  { key: 'median20', label: '未来20日中位预测', pct: true, fixed: false },
  { key: 'mom21', label: '近21日动量', pct: true, fixed: false },
  { key: 'mom126', label: '近半年动量', pct: true, fixed: false },
  { key: 'vol', label: '年化波动率', pct: true, fixed: false },
  { key: 'pct_from_high', label: '距52周高', pct: true, fixed: false },
  { key: 'bandwidth', label: '概率带宽(不确定性)', pct: true, fixed: false },
]
const METRIC_OPTS: SearchOption[] = METRICS.map((m) => ({ value: m.key, label: m.label }))

export default function Trends({ meta }: { meta: TickerMeta; watch: Set<string> }) {
  const [avail, setAvail] = useState<SearchOption[]>([])
  const [sel, setSel] = useState<string[]>([]) // 无默认股票
  const [metrics, setMetrics] = useState<string[]>([]) // 无默认维度
  const [series, setSeries] = useState<Record<string, RichTrendPoint[]>>({})

  // 只拉可选股票清单(有档位历史),不预选任何股票/维度——由用户自己挑
  useEffect(() => {
    fetchTrendTickers().then((ts) => {
      setAvail(ts.map((t): SearchOption => ({
        value: t.ticker, label: t.ticker,
        sub: (meta[t.ticker]?.cn || '') + ` · ${t.n}天`, keywords: meta[t.ticker]?.cn,
      })))
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta])

  useEffect(() => { fetchTrendRich(sel).then(setSeries) }, [sel])

  const shownMetrics = METRICS.filter((m) => metrics.includes(m.key))

  return (
    <>
      <div className="hint">
        📈 挑几只股票,选<b>一个或多个分析维度</b>,看它们随时间怎么变化(每个维度一张图)。所有维度都来自每天回填的策略快照。
        <b>注意</b>:只有「被策略选中过」的交易日才有数据,常被选的股(如 AMD/INTC)曲线连续,偶尔选中的会有断点。
      </div>
      <div className="card">
        <div className="trend-ctl">
          <div>
            <div className="ctl-lbl">股票(可多选,最多8只) <InfoDot text="只列有档位历史的股票(策略选中过的)。输代码或中文名搜索。" /></div>
            <MultiSelect value={sel} options={avail} onChange={setSel} placeholder="搜索添加股票…" max={8} />
          </div>
          <div>
            <div className="ctl-lbl">分析维度(可多选,每个一张图)</div>
            <MultiSelect value={metrics} options={METRIC_OPTS} onChange={setMetrics}
              placeholder="选维度…" max={METRICS.length} />
          </div>
        </div>
        {(sel.length === 0 || metrics.length === 0) && (
          <div className="muted" style={{ marginTop: 12 }}>
            上面先<b>搜索添加股票</b>(1 只或多只),再<b>选分析维度</b>(1 个或多个,每个维度一张图),即可开始对比。
          </div>
        )}
        {sel.length > 0 && shownMetrics.map((m) => (
          <div key={m.key} className="trend-panel">
            <TrendChart m={m} series={series} meta={meta} />
          </div>
        ))}
      </div>
    </>
  )
}
