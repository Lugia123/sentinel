import { useEffect, useState } from 'react'
import { fetchTrendRich, fetchTrendTickers, type RichTrendPoint } from '../api'
import type { TickerMeta, Market } from '../api'
import MultiSelect from '../components/MultiSelect'
import TrendChart, { type MetricDef } from '../components/TrendChart'
import type { SearchOption } from '../components/SearchSelect'
import { InfoDot } from '../ui'

// 可选的分析维度(都来自每日快照,挖出来对比)
// 每个维度=1个主指标 + 相关辅助指标(单选1只股时叠加显示,多选时只显示主指标做对比)。
// 注:未来20日中位/概率带宽 = 年化波动率 × 固定常数,无独立信息,已并入年化波动率不单列。
const METRICS: MetricDef[] = [
  { key: 'grade', label: '档位(-3 ~ +3)', pct: false, fixed: true,
    aux: [{ key: 'price', label: '收盘价', dollar: true }, { key: 'sma20', label: '20日线', dollar: true }] },
  { key: 'mom21', label: '近21日动量', pct: true, fixed: false,
    aux: [{ key: 'mom126', label: '近半年动量', dollar: false }] },
  { key: 'mom126', label: '近半年动量', pct: true, fixed: false,
    aux: [{ key: 'mom21', label: '近21日动量', dollar: false }] },
  { key: 'vol', label: '年化波动率', pct: true, fixed: false,
    aux: [{ key: 'price', label: '收盘价', dollar: true }] },
  { key: 'pct_from_high', label: '距52周高', pct: true, fixed: false,
    aux: [{ key: 'price', label: '收盘价', dollar: true }] },
]
const METRIC_OPTS: SearchOption[] = METRICS.map((m) => ({ value: m.key, label: m.label }))

export default function Trends({ meta, market = 'us' }: { meta: TickerMeta; watch: Set<string>; market?: Market }) {
  const [avail, setAvail] = useState<SearchOption[]>([])
  const [names, setNames] = useState<Record<string, string>>({}) // ticker→中文名(A股来自后端;美股来自 meta)
  const [sel, setSel] = useState<string[]>([]) // 无默认股票
  const [metrics, setMetrics] = useState<string[]>([]) // 无默认维度
  const [series, setSeries] = useState<Record<string, RichTrendPoint[]>>({})

  // 只拉可选股票清单(有档位历史),不预选任何股票/维度——由用户自己挑;切市场重拉并清空已选
  useEffect(() => {
    setSel([]); setSeries({})
    fetchTrendTickers().then((ts) => {
      const nm: Record<string, string> = {}
      ts.forEach((t) => { const n = t.name || meta[t.ticker]?.cn; if (n) nm[t.ticker] = n })
      setNames(nm)
      setAvail(ts.map((t): SearchOption => ({
        value: t.ticker, label: t.ticker,
        sub: (nm[t.ticker] || '') + ` · ${t.n}天`, keywords: nm[t.ticker],
      })))
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta, market])

  useEffect(() => { fetchTrendRich(sel).then(setSeries) }, [sel])

  const shownMetrics = METRICS.filter((m) => metrics.includes(m.key))

  return (
    <>
      <div className="hint">
        📈 挑股票 + 选<b>分析维度</b>(每个维度一张图)。<b>只选 1 只</b>=深度模式,图上会叠加相关<b>辅助指标</b>(如档位图配 收盘价+20日线);<b>选多只</b>=对比模式,只画主指标。
        <b>注意</b>:只有「被策略选中过」的交易日才有数据,常被选的股曲线连续,偶尔选中的会有断点。
        {market === 'cn' && <><br /><b>A股提示</b>:A股快照目前只记录档位/价格/概率带,动量·波动·距高等维度暂无数据,建议选「档位」维度。</>}
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
            <TrendChart m={m} series={series} names={names} cur={market === 'cn' ? '¥' : '$'} />
          </div>
        ))}
      </div>
    </>
  )
}
