import { useEffect, useState } from 'react'
import {
  fetchNewsDigest, fetchNewsCalendar, fetchColumnSectors, saveColumnSectors, fetchSectorDigest, fetchNewsFeed,
  type NewsDigest, type SectorDigest, type CalendarEvent, type FeedItem, type Market,
} from '../api'
import NewsItemModal from '../components/NewsItemModal'
import EventInterpretModal from '../components/EventInterpretModal'

type EventPick = { title: string; context: string; kind: string }

const toneCls = (t?: string) => (t === '利好' ? 'up' : t === '利空' ? 'down' : 'muted')
// 剥离快讯标题里的【】包裹(阅读噪声)+ 取时间 HH:MM
const cleanTitle = (t: string) => t.replace(/^【(.+?)】/, '$1').trim()
const hhmm = (p?: string) => (p && p.length >= 16 ? p.slice(11, 16) : '')
const mmdd = (p?: string) => (p && p.length >= 10 ? p.slice(5, 10) : '')

// 今日要闻页(tab 式):综合 + 每个自定义板块一个 tab + 管理。每个 tab 都是完整一套。
export default function News({ market = 'us' }: { market?: Market }) {
  const [sectors, setSectors] = useState<string[]>([])
  const [tab, setTab] = useState<string>('综合') // '综合' | 板块名 | '管理'
  const [openId, setOpenId] = useState<number | null>(null)
  const [openEvent, setOpenEvent] = useState<EventPick | null>(null)

  useEffect(() => { setTab('综合'); if (market === 'cn') fetchColumnSectors().then(setSectors); else setSectors([]) }, [market])

  return (
    <>
      <div className="hint">
        📰 每日金融要闻(新闻源采集 + AI 分级合成)。<b>纯资讯参考,与选股策略完全独立,非投资建议。</b>
        {market === 'cn' && ' 顶部可切换「综合」与你关注的板块专栏。'}
      </div>

      {market === 'cn' && (
        <div className="tabs" style={{ marginBottom: 12 }}>
          <button className={tab === '综合' ? 'active' : ''} onClick={() => setTab('综合')}>综合</button>
          {sectors.map((s) => <button key={s} className={tab === s ? 'active' : ''} onClick={() => setTab(s)}>{s}</button>)}
          <button className={tab === '管理' ? 'active' : ''} onClick={() => setTab('管理')}>＋ 管理板块</button>
        </div>
      )}

      {tab === '管理'
        ? <ManageSectors sectors={sectors} onSaved={(ss) => { setSectors(ss); setTab(ss[0] || '综合') }} />
        : tab === '综合'
          ? <GeneralDigest market={market} onOpen={setOpenId} onOpenEvent={setOpenEvent} />
          : <SectorColumn sector={tab} onOpen={setOpenId} onOpenEvent={setOpenEvent} />}

      {openId && <NewsItemModal id={openId} onClose={() => setOpenId(null)} />}
      {openEvent && <EventInterpretModal event={openEvent} onClose={() => setOpenEvent(null)} />}
    </>
  )
}

// ── 综合 tab:全市场日报 + 可点新闻列表 + 日历 ──
function GeneralDigest({ market, onOpen, onOpenEvent }: { market: Market; onOpen: (id: number) => void; onOpenEvent: (e: EventPick) => void }) {
  const [d, setD] = useState<NewsDigest | null>(null)
  const [date, setDate] = useState(''); const [n, setN] = useState(0)
  const [feed, setFeed] = useState<FeedItem[]>([]); const [cal, setCal] = useState<CalendarEvent[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    setLoading(true)
    fetchNewsDigest().then((r) => { setD(r.digest); setDate(r.digest_date || ''); setN(r.n_source || 0) }).finally(() => setLoading(false))
    fetchNewsFeed().then(setFeed); fetchNewsCalendar().then(setCal)
  }, [market])
  if (loading) return <div className="card">加载今日要闻…</div>
  return (
    <>
      {d?.overview && <div className="card"><h3>今日综述 <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>{date} · 基于 {n} 条要闻</span></h3><p style={{ margin: 0, lineHeight: 1.7 }}>{d.overview}</p></div>}
      <TwoCol world={d?.world} domestic={d?.domestic} onOpenEvent={onOpenEvent} />
      <ImpactTable title="📊 板块影响" head="板块/主题" rows={(d?.market_impact || []).map((x) => ({ a: x.sector, b: x.reason, tone: x.tone }))} />
      <Transmission items={d?.global_transmission} />
      <NewsFeed feed={feed} onOpen={onOpen} />
      <Calendar cal={cal} />
      <Disclaimer />
    </>
  )
}

// ── 板块 tab:围绕该板块的完整一套 ──
function SectorColumn({ sector, onOpen, onOpenEvent }: { sector: string; onOpen: (id: number) => void; onOpenEvent: (e: EventPick) => void }) {
  const [d, setD] = useState<SectorDigest | null>(null)
  const [date, setDate] = useState(''); const [feed, setFeed] = useState<FeedItem[]>([])
  const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false)
  const load = (refresh = false) => {
    setLoading(true)
    fetchSectorDigest(sector, refresh).then((r) => { setD(r.digest); setDate(r.digest_date || '') }).finally(() => { setLoading(false); setBusy(false) })
    fetchNewsFeed(sector).then(setFeed)
  }
  useEffect(() => { setD(null); load(false) }, [sector])
  return (
    <>
      <div className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0 }}>⭐ {sector} 专栏 <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>· 只属于你,聚焦「{sector}」{date && ` · ${date}`}</span></h3>
        <button className="ghost mini" onClick={() => { setBusy(true); load(true) }} disabled={busy}>{busy ? '生成中…（约20秒）' : '刷新专栏'}</button>
      </div>
      {loading && !d && <div className="card muted">加载专栏…</div>}
      {!loading && !d && <div className="card muted">还没生成「{sector}」专栏。点右上「刷新专栏」由 AI 从当日新闻合成一套聚焦该板块的资讯。</div>}
      {d && (<>
        {d.overview && <div className="card"><h3>{sector} · 今日综述</h3><p style={{ margin: 0, lineHeight: 1.7 }}>{d.overview}</p></div>}
        <TwoCol world={d.world} domestic={d.domestic} onOpenEvent={onOpenEvent} />
        <ImpactTable title="🎯 个股影响" head="个股" rows={(d.stock_impact || []).map((x) => ({ a: x.stock, b: x.reason, tone: x.tone }))} />
        <Transmission items={d.global_transmission} />
      </>)}
      <NewsFeed feed={feed} onOpen={onOpen} title={`📰 ${sector} 相关新闻`} />
      <Disclaimer />
    </>
  )
}

// ── 复用小组件 ──
type Evt = { title: string; impact: string; tone: string }
function TwoCol({ world, domestic, onOpenEvent }: { world?: Evt[]; domestic?: Evt[]; onOpenEvent: (e: EventPick) => void }) {
  const col = (title: string, kind: string, arr?: Evt[]) => (
    <div className="card" style={{ flex: 1 }}>
      <h3>{title} <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>· 点击展开 AI 解读</span></h3>
      {(arr || []).map((x, i) => (
        <div key={i} className="evt-item evt-click" onClick={() => onOpenEvent({ title: x.title, context: x.impact, kind })}>
          <div className="evt-title">{x.title} <span className={`pill ${toneCls(x.tone)}`} style={{ fontSize: 11 }}>{x.tone}</span></div>
          <div className="evt-impact">{x.impact}</div>
        </div>
      ))}
      {!(arr || []).length && <div className="muted">—</div>}
    </div>
  )
  return <div className="row">{col('🌍 世界大事', '世界大事', world)}{col('🇨🇳 国内大事', '国内大事', domestic)}</div>
}

function ImpactTable({ title, head, rows }: { title: string; head: string; rows: { a: string; b: string; tone: string }[] }) {
  if (!rows.length) return null
  return (
    <div className="card"><h3>{title}</h3>
      <div className="tbl-scroll"><table>
        <thead><tr><th>{head}</th><th>原因</th><th>方向</th></tr></thead>
        <tbody>{rows.map((x, i) => <tr key={i}><td><b>{x.a}</b></td><td className="muted">{x.b}</td><td className={toneCls(x.tone)}>{x.tone}</td></tr>)}</tbody>
      </table></div>
    </div>
  )
}

function Transmission({ items }: { items?: { event: string; timing: string; tone: string }[] }) {
  if (!items?.length) return null
  return (
    <div className="card"><h3>🔗 全球传导 <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>· 全球事件 → A股,含提前/滞后</span></h3>
      <div className="tbl-scroll"><table>
        <thead><tr><th>全球事件</th><th>时序(提前/滞后)</th><th>方向</th></tr></thead>
        <tbody>{items.map((x, i) => <tr key={i}><td><b>{x.event}</b></td><td className="muted">{x.timing}</td><td className={toneCls(x.tone)}>{x.tone}</td></tr>)}</tbody>
      </table></div>
    </div>
  )
}

const SRC_CN: Record<string, string> = { em_global: '东财', sina_global: '新浪', ths_global: '同花顺', cctv: '央视', gdelt: '全球', stock_em: '东财个股' }
function NewsFeed({ feed, onOpen, title = '📰 相关新闻' }: { feed: FeedItem[]; onOpen: (id: number) => void; title?: string }) {
  return (
    <div className="card"><h3>{title} <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>· 点击展开 AI 解读 + 来源</span></h3>
      {feed.length === 0 && <div className="muted">暂无</div>}
      <div className="news-list">
        {feed.map((n) => (
          <div key={n.id} className="news-item" onClick={() => onOpen(n.id)}>
            <div className="news-time"><span className="nd-date">{mmdd(n.published)}</span><span className="nd-time">{hhmm(n.published)}</span></div>
            <div className="news-main">
              <div className="news-headline">{cleanTitle(n.title)}</div>
              <div className="news-meta"><span className="news-src-tag">{SRC_CN[n.source] || n.source}</span></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function Calendar({ cal }: { cal: CalendarEvent[] }) {
  if (!cal.length) return null
  return (
    <div className="card"><h3>📅 未来事件日历</h3>
      <div className="tbl-scroll"><table>
        <thead><tr><th>日期</th><th>类别</th><th>事件</th></tr></thead>
        <tbody>{cal.slice(0, 20).map((e, i) => (
          <tr key={i}><td className="muted">{e.event_date}</td>
            <td><span className="pill muted" style={{ fontSize: 11 }}>{e.category === 'earnings' ? '财报' : e.category === 'macro' ? '宏观' : e.category}</span></td>
            <td>{e.title}</td></tr>
        ))}</tbody>
      </table></div>
    </div>
  )
}

function Disclaimer() {
  return <div className="src-cite">📰 资讯由新闻源(财联社/央视/东财/GDELT 等)采集,AI 分级合成。研究经严格回测:新闻对 A股无强可交易 alpha,本页仅作信息/情境参考,<b>非策略信号,非投资建议</b>。</div>
}

// ── 管理板块 ──
function ManageSectors({ sectors, onSaved }: { sectors: string[]; onSaved: (ss: string[]) => void }) {
  const [list, setList] = useState<string[]>(sectors)
  const [input, setInput] = useState(''); const [busy, setBusy] = useState(false)
  const add = () => { const s = input.trim(); if (s && !list.includes(s) && list.length < 10) { setList([...list, s]); setInput('') } }
  const del = (s: string) => setList(list.filter((x) => x !== s))
  const save = async () => { setBusy(true); await saveColumnSectors(list); setBusy(false); onSaved(list) }
  return (
    <div className="card">
      <h3>管理板块专栏 <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>· 每个板块一个 tab,只属于你</span></h3>
      <div style={{ margin: '10px 0' }}>
        {list.map((s) => <span key={s} className="picked-chip" style={{ marginRight: 6, marginBottom: 4, display: 'inline-block' }}>{s}<button onClick={() => del(s)} aria-label="删">×</button></span>)}
        {!list.length && <span className="muted">还没加板块。下方添加,如 半导体、白酒、新能源车、创新药、光伏…</span>}
      </div>
      <div className="pos-add" style={{ margin: 0 }}>
        <input placeholder="输入行业/板块名" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && add()} style={{ width: 220 }} />
        <button onClick={add} disabled={list.length >= 10}>+ 添加</button>
        <button className="primary" onClick={save} disabled={busy}>{busy ? '保存中…' : '保存'}</button>
      </div>
      <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>最多 10 个。保存后每个板块成为一个 tab,进入后可「刷新专栏」由 AI 从当日新闻合成一套聚焦该板块的完整资讯(综述/世界/国内/个股影响/全球传导/相关新闻)。</div>
    </div>
  )
}
