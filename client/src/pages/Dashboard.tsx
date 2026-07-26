import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import type { Snapshot, Holding } from '../types'
import type { TickerMeta } from '../api'
import { pct, pct2, InfoDot, GradeBadge, SleeveBadge, actionColor, cnMarketAction } from '../ui'
import SearchSelect, { type SearchOption } from '../components/SearchSelect'
import AllocateModal from '../components/AllocateModal'
import RiskRibbon from '../components/RiskRibbon'
import { fetchUniverse, saveCapital, fetchPnL, addCustom, removeCustom, fetchDropped, fetchStrategy, saveStrategy, type StrategyKey, type UniverseItem, type DroppedItem, type Market } from '../api'

// A股策略腿 → sleeve 集合(头号腿·微盘 与 红利低波·大资金 二选一)。custom 自选不属任何策略,始终显示。
const STRAT_SLEEVES: Record<StrategyKey, Set<string>> = {
  headline: new Set(['smallcap', 'event', 'both']),
  dividend: new Set(['dividend']),
}
const STRAT_DESC: Record<StrategyKey, string> = {
  headline: '小市值 × 低换手,容量约千万级——A股长期最稳的维度。',
  dividend: '高股息 × 低波动,size中性,容量亿级+、回撤更低——大资金替代腿(与头号腿二选一,非叠加)。',
}

export default function Dashboard({ snap, meta, watch, onToggleWatch, onSelect, onSelectDropped, onReload, onOpenRiskLight }: {
  snap: Snapshot; meta: TickerMeta; watch: Set<string>
  onToggleWatch: (t: string, on: boolean) => void; onSelect: (t: string) => void
  onSelectDropped: (d: DroppedItem) => void
  onReload: () => void
  onOpenRiskLight: () => void
}) {
  const chartRef = useRef<HTMLDivElement>(null)
  // 添加自定义股:两步(先选中→点添加,防误点);pending=正在算档位的(显示加载中行)
  const [picked, setPicked] = useState('')
  const [pending, setPending] = useState<Set<string>>(new Set())
  const [addErr, setAddErr] = useState('')
  const doAdd = async () => {
    const tk = picked
    if (!tk || pending.has(tk)) return
    setPicked(''); setAddErr('')
    setPending((s) => new Set(s).add(tk))
    try { await addCustom(tk); await onReload() } catch (e: any) { setAddErr(String(e.message || e)) }
    setPending((s) => { const n = new Set(s); n.delete(tk); return n })
  }
  const removeCustomStock = async (tk: string) => { await removeCustom(tk); await onReload() }
  // 资金池(每用户可编辑;改后重算缩放的快照)
  const [capEdit, setCapEdit] = useState(false)
  const isCN = snap.market === 'cn'
  // A股策略腿选择(头号腿/红利,二选一;按用户存后端)。仅前端过滤,快照已含全 sleeve,切换不重算。
  const [strategy, setStrategy] = useState<StrategyKey>('headline')
  useEffect(() => { if (isCN) fetchStrategy().then(setStrategy).catch(() => {}) }, [snap.market, isCN])
  const pickStrategy = async (s: StrategyKey) => {
    if (s === strategy) return
    setStrategy(s)
    try { await saveStrategy(s) } catch { /* 存失败不影响本地展示 */ }
  }
  // 当前策略下可见的持仓:美股=全部;A股=选中策略腿 + 自选(custom 始终显示)
  const inStrategy = (sl: string) => !isCN || sl === 'custom' || STRAT_SLEEVES[strategy].has(sl)
  const shown = snap.holdings.filter((h) => inStrategy(h.sleeve))
  const CUR = isCN ? '¥' : '$'
  const money = (x: number) => `${CUR}${x.toLocaleString('en-US', { maximumFractionDigits: 2 })}`
  const [capVal, setCapVal] = useState(String(snap.capital))
  const [capBusy, setCapBusy] = useState(false)
  const saveCap = async () => {
    const v = parseFloat(capVal)
    if (!(v >= 1)) return
    setCapBusy(true)
    try { await saveCapital(v); await onReload() } catch { /* ignore */ }
    setCapBusy(false); setCapEdit(false)
  }
  // 建议股数分配:纯工具弹窗(不回写列表)
  const [allocOpen, setAllocOpen] = useState(false)
  // 建议持仓 / 掉出推荐 tab
  const [listTab, setListTab] = useState<'rec' | 'dropped'>('rec')
  const [dropped, setDropped] = useState<DroppedItem[]>([])
  useEffect(() => { setListTab('rec'); fetchDropped().then(setDropped) }, [snap.market, snap.asof])
  const daysOut = (d: string) => Math.max(0, Math.round((new Date(snap.asof).getTime() - new Date(d).getTime()) / 86400000))
  // 我的持仓(和「我的持仓」页联动:把实际持仓股数显示到列表)
  const [myPos, setMyPos] = useState<Record<string, number>>({})
  useEffect(() => {
    fetchPnL().then((r) => {
      const m: Record<string, number> = {}
      ;(r.positions || []).forEach((p: any) => { m[String(p.ticker).toUpperCase()] = p.shares })
      setMyPos(m)
    }).catch(() => {})
  }, [snap])
  // 关注的置顶(保持各自组内原顺序)。策略推荐与「我的自选」分开成组。
  // 排序:⭐关注置顶 → 档位高→低 → 预期20日中位收益高→低(和下方区间图一致,从好到差)
  const medRet = (h: Holding) => h.prob?.['h20']?.median ?? -Infinity
  const byRank = (a: Holding, b: Holding) =>
    (watch.has(b.ticker) ? 1 : 0) - (watch.has(a.ticker) ? 1 : 0)
    || b.grade - a.grade
    || medRet(b) - medRet(a)
  const mainRows = shown.filter((h) => h.sleeve !== 'custom').sort(byRank)
  const customRows = shown.filter((h) => h.sleeve === 'custom').sort(byRank)
  const renderRow = (h: Holding) => {
    const b = h.prob?.['h20']
    const on = watch.has(h.ticker)
    const m = meta[h.ticker]
    const isCustom = h.sleeve === 'custom'
    return (
      <tr key={h.ticker} className="clickable" onClick={() => onSelect(h.ticker)}>
        <td onClick={(e) => { e.stopPropagation(); onToggleWatch(h.ticker, !on) }} style={{ cursor: 'pointer', textAlign: 'center' }}>
          <span className={on ? 'star on' : 'star'}>{on ? '★' : '☆'}</span>
        </td>
        <td><b>{h.ticker}</b>{(h.name || m?.cn) && <span className="cn">{h.name || m?.cn}</span>} <span className="go">›</span></td>
        <td className="muted">{m?.sector || '—'}</td>
        <td><SleeveBadge sleeve={h.sleeve} />{isCustom && <button className="rm-custom" title="从追踪移除" onClick={(e) => { e.stopPropagation(); removeCustomStock(h.ticker) }}>✕</button>}</td>
        <td>{CUR}{h.price}</td>
        <td className={myPos[h.ticker.toUpperCase()] ? 'gold' : 'muted'}>{myPos[h.ticker.toUpperCase()] || '—'}</td>
        <td><GradeBadge g={h.grade} label={h.grade_label} /></td>
        <td style={isCN
          ? { color: cnMarketAction(rl.level).color, fontWeight: 600 }
          : { color: actionColor(h.action), fontWeight: 600 }}>
          {isCN ? cnMarketAction(rl.level).text : h.action}</td>
        <td className="muted">{b ? <>{pct2(b.band70[0])} ~ {pct2(b.band70[1])}</> : '—'}</td>
      </tr>
    )
  }
  // 可添加的自定义股 = 全部可分析股(数据池1393只)里尚未在列表的(不再只限98大盘股)
  const [universe, setUniverse] = useState<UniverseItem[]>([])
  useEffect(() => { fetchUniverse().then(setUniverse) }, [snap.market]) // 切市场重拉对应池
  const heldSet = new Set(snap.holdings.map((h) => h.ticker))
  const addable: SearchOption[] = universe
    .filter((u) => !heldSet.has(u.ticker))
    .map((u) => ({ value: u.ticker, label: u.ticker, sub: u.cn ? `${u.cn}${u.sector ? ' · ' + u.sector : ''}` : '', keywords: u.cn }))
  // 横向布局:每股一行(按档位→中位排序),行多时容器内竖向滚动,不再横向挤成一团
  const rowH = 26
  const chartH = Math.max(240, shown.length * rowH + 60)
  useEffect(() => {
    if (!chartRef.current) return
    const chart = echarts.init(chartRef.current)
    // 排序:档位高的在上,同档位按中位收益降序(prob 可能缺 h20,如 A股新股数据不足)
    const med = (h: Holding) => h.prob?.['h20']?.median ?? 0
    const hs = [...shown].filter((h) => h.prob?.['h20']).sort((a, b) => b.grade - a.grade || med(b) - med(a))
    const bands = hs.map((h, i) => ({ value: [i, h.prob['h20'].band70[0] * 100, h.prob['h20'].band70[1] * 100, h.prob['h20'].median * 100], grade: h.grade }))
    const label = (i: number) => hs[i].ticker + ((hs[i].name || meta[hs[i].ticker]?.cn) ? ' ' + (hs[i].name || meta[hs[i].ticker]?.cn) : '')
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
  }, [snap, meta, strategy])

  const rl = snap.risk_light
  return (
    <>
      <div className="hint">
        👉 这是策略<b>今天算出来的建议持仓</b>。每一行是一只股票：<b>档位</b>越高越健康，<b>动作</b>告诉你该拿住还是减。
        <b>点任意一行</b>看它的详细指标 + AI 讲解「为什么选它」。这是研究工具，最终自己决定。
      </div>

      {/* 市场风险灯:一进来先看市场处在什么体制(制度带+宽度vs阈值),再看个股 */}
      <RiskRibbon market={(snap.market || 'us') as Market} onOpenDetail={onOpenRiskLight} title="市场风险灯" />

      <div className="row">
        <div className="card">
          <div className="muted">当前风险灯 <InfoDot text="市场级总仓位闸。绿=可满仓,黄=半仓,红=空仓观望。管总仓位,不针对单只股;详情见上方风险灯。" /></div>
          <div className="big"><span className={`light ${rl.level}`} />{rl.note}</div>
          {snap.market === 'cn'
            ? <div className="muted">市场宽度 {pct((rl as any).bench_breadth)} · 微盘拥挤度 {pct((rl as any).crowd_pct)}{(rl as any).diverge ? ' · 小盘背离⚠' : ''} · 建议总仓位 {pct(rl.exposure)}</div>
            : <div className="muted">大盘(SPY)年化波动 {pct(rl.spy_vol)} · 建议总仓位 {pct(rl.exposure)}</div>}
        </div>
        <div className="card">
          <div className="muted">策略建议组合{isCN && <span className="muted"> · {strategy === 'dividend' ? '红利低波' : '头号腿'}</span>}</div>
          <div className="big">{isCN ? mainRows.length : snap.portfolio.n_holdings} 只</div>
          <div className="muted">总仓位 {pct(snap.portfolio.gross_exposure)} · 留现金 {pct(snap.portfolio.cash_pct)}</div>
        </div>
        <div className="card">
          <div className="muted">我的资金池 <InfoDot text="你的可投金额。建议股数按它×风险平价算,改了会立刻按比例重算(每个用户独立)。" /></div>
          {!capEdit ? (
            <>
              <div className="big">{money(snap.capital)}</div>
              <button className="ghost mini" onClick={() => { setCapVal(String(snap.capital)); setCapEdit(true) }}>✎ 编辑</button>
            </>
          ) : (
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 4, flexWrap: 'wrap' }}>
              <span className="muted">{CUR}</span>
              <input value={capVal} onChange={(e) => setCapVal(e.target.value.replace(/[^0-9.]/g, ''))}
                onKeyDown={(e) => e.key === 'Enter' && saveCap()} style={{ width: 100 }} autoFocus />
              <button className="primary" onClick={saveCap} disabled={capBusy}>{capBusy ? '…' : '保存'}</button>
              <button className="ghost mini" onClick={() => setCapEdit(false)}>取消</button>
            </div>
          )}
        </div>
      </div>

      {isCN && (
        <div className="card strat-bar">
          <div className="strat-head">
            <span className="muted">A股策略 <InfoDot text="头号腿(微盘)与红利低波(大资金)是二选一的替代策略,不是同时持有——切换只换看哪套推荐,资金不叠加。小资金用头号腿;资金大到微盘吃不下(约千万级、冲击成本上升)用红利低波。你的自选股不受影响,始终显示。" /></span>
            <div className="seg" role="tablist">
              <button role="tab" aria-selected={strategy === 'headline'} className={strategy === 'headline' ? 'on' : ''} onClick={() => pickStrategy('headline')}>
                头号腿 · 微盘 <em>小资金</em>
              </button>
              <button role="tab" aria-selected={strategy === 'dividend'} className={strategy === 'dividend' ? 'on' : ''} onClick={() => pickStrategy('dividend')}>
                红利低波 <em>大资金</em>
              </button>
            </div>
          </div>
          <div className="muted strat-desc">{STRAT_DESC[strategy]}</div>
        </div>
      )}

      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginBottom: 6 }}>
          <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className={listTab === 'rec' ? '' : 'muted'} style={{ cursor: 'pointer' }} onClick={() => setListTab('rec')}>建议持仓</span>
            <span className={listTab === 'dropped' ? '' : 'muted'} style={{ cursor: 'pointer' }} onClick={() => setListTab('dropped')}>
              掉出推荐{dropped.length > 0 && <span className="pill g-neg1" style={{ marginLeft: 4 }}>{dropped.length}</span>}
            </span>
            <InfoDot text="掉出推荐=曾被策略选中、连续2个交易日不再满足入选条件的股票(30天后自动清理;连续2日重新入选会自动回归)。点行看 AI 分析掉出原因。" />
            {listTab === 'rec' && <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>· 点行看详情 · ★关注置顶</span>}
          </h3>
          {listTab === 'rec' && <div className="pos-add" style={{ margin: 0 }}>
            {picked
              ? <span className="picked-chip">{picked}{meta[picked]?.cn ? ' ' + meta[picked].cn : ''}<button onClick={() => setPicked('')} aria-label="取消">×</button></span>
              : <SearchSelect options={addable} onPick={setPicked}
                  placeholder="添加自定义股票:输代码或中文名" emptyText="没有匹配的可添加股票(或已在列表中)" />}
            <button className="primary" onClick={doAdd} disabled={!picked}>添加</button>
            <InfoDot text="先搜索选中一只(可输代码或中文名),再点「添加」纳入你的追踪列表(不会自动关注)。添加后会算它的档位/概率,列表出现「加载中」行,算完即显示。" />
            <button className="th-btn" onClick={() => setAllocOpen(true)} title="选股票 + 方式,算各股买多少(工具,不改列表)">⚖ 分配计算</button>
          </div>}
        </div>
        {addErr && <div className="down" style={{ fontSize: 13, marginBottom: 6 }}>{addErr}</div>}
        {listTab === 'dropped' && (
          <div className="tbl-scroll">
            <table>
              <thead><tr><th>标的</th><th>掉出日期</th><th>已掉出</th><th>掉出时档位</th><th>掉出时价</th><th>现价</th><th>掉出后涨跌 <InfoDot text="从最后在推荐中那天的收盘价到最新收盘价的涨跌——回头检验策略掉出得对不对。" /></th></tr></thead>
              <tbody>
                {dropped.map((d) => {
                  const chg = d.price_now > 0 && d.last_price > 0 ? (d.price_now - d.last_price) / d.last_price : null
                  return (
                    <tr key={d.ticker} className="clickable" onClick={() => onSelectDropped(d)}>
                      <td><b>{d.ticker}</b>{(d.name || meta[d.ticker]?.cn) && <span className="cn">{d.name || meta[d.ticker]?.cn}</span>} <span className="go">›</span></td>
                      <td className="muted">{d.dropped_at}</td>
                      <td>{daysOut(d.dropped_at)} 天</td>
                      <td><GradeBadge g={d.last_grade} /></td>
                      <td className="muted">{CUR}{d.last_price}</td>
                      <td>{d.price_now > 0 ? `${CUR}${d.price_now}` : '—'}</td>
                      <td className={chg == null ? 'muted' : chg >= 0 ? 'up' : 'down'}>{chg == null ? '—' : pct2(chg)}</td>
                    </tr>
                  )
                })}
                {dropped.length === 0 && <tr><td colSpan={7} className="muted" style={{ textAlign: 'center', padding: 20 }}>暂无掉出记录(股票连续 2 个交易日不再被策略选中才会出现在这里)</td></tr>}
              </tbody>
            </table>
          </div>
        )}
        {listTab === 'rec' && <div className="tbl-scroll">
          <table>
            <thead>
              <tr>
                <th></th>
                <th>标的</th>
                <th>板块</th>
                <th>选股依据 <InfoDot text={isCN ? "头号腿=小市值×低换手(A股长期最稳的维度)；事件腿=分析师上修+业绩预告惊喜；双腿=两者都占。" : "动量=趋势强涨得比大盘好；股东回报=回购分红多；双腿=两者都占。"} /></th>
                <th>现价</th>
                <th>我的持仓 <InfoDot text="你在「我的持仓」里录入的实际股数(和持仓页联动)。未持有显示 —。想算该买多少,用上方「⚖ 分配计算」。" /></th>
                <th>档位 <InfoDot text={isCN ? "趋势健康度 -3到+3,由3个信号(站上20/60/200日线)合成。A股逐票只看不减,档位仅展示趋势状态。" : "趋势健康度 -3到+3,由7个信号(站上均线/动量/排列等)合成。+1及以上=持有,往下=逐步减仓。"} /></th>
                <th>动作 <InfoDot text={isCN ? "A股逐票不按档位减仓(反转市,逐票减仓有害),动作由【市场级风险灯】统一决定:绿=持有满仓,黄=减至半仓,红=清仓观望——对列表里所有票一致生效。" : "档位对应的操作。只减不追涨:走弱才逐档减仓,趋势好就拿住。"} /></th>
                <th>未来20日区间 <InfoDot text="未来20天收益的70%概率范围(15%~85%分位)。这是波动范围估计,不是涨跌预测。" /></th>
              </tr>
            </thead>
            <tbody>
              {[...pending].map((tk) => (
                <tr key={'pending-' + tk} className="pending-row">
                  <td></td>
                  <td><b>{tk}</b>{meta[tk]?.cn && <span className="cn">{meta[tk].cn}</span>}</td>
                  <td colSpan={7} className="muted">⏳ 加载中…正在算它的档位/概率(约几秒),算完自动显示</td>
                </tr>
              ))}
              {mainRows.map(renderRow)}
              {mainRows.length === 0 && customRows.length === 0 && (
                <tr><td colSpan={9} className="muted" style={{ textAlign: 'center', padding: 20 }}>
                  {isCN ? '当前策略今日无推荐(风险灯/数据所致),可切换策略或看自选。' : '今日无推荐持仓。'}
                </td></tr>
              )}
              {customRows.length > 0 && (
                <tr className="grp-row">
                  <td></td>
                  <td colSpan={8} className="muted">
                    我的自选 <span className="pill b-custom" style={{ marginLeft: 2 }}>{customRows.length}</span>
                    <span style={{ marginLeft: 6, fontWeight: 400 }}>· 你添加的追踪股,不占策略仓位、建议股数为 0</span>
                  </td>
                </tr>
              )}
              {customRows.map(renderRow)}
            </tbody>
          </table>
        </div>}
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
        <AllocateModal holdings={shown} meta={meta} capital={snap.capital} exposure={rl.exposure}
          onClose={() => setAllocOpen(false)} />
      )}
    </>
  )
}
