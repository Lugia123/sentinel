import { useEffect, useState } from 'react'
import { fetchNewsDigest, fetchNewsCalendar, type NewsDigest, type CalendarEvent, type Market } from '../api'

// 今日金融要闻日报页(纯展示 news_digest,与策略解耦)。资讯参考,非策略信号。
const toneCls = (t?: string) => (t === '利好' ? 'up' : t === '利空' ? 'down' : 'muted')

export default function News({ market = 'us' }: { market?: Market }) {
  const [d, setD] = useState<NewsDigest | null>(null)
  const [date, setDate] = useState('')
  const [n, setN] = useState(0)
  const [cal, setCal] = useState<CalendarEvent[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    setLoading(true)
    fetchNewsDigest().then((r) => { setD(r.digest); setDate(r.digest_date || ''); setN(r.n_source || 0) }).finally(() => setLoading(false))
    fetchNewsCalendar().then(setCal)
  }, [market])

  if (loading) return <div className="card">加载今日要闻…</div>
  if (!d) return (
    <div className="card">
      <h3>今日要闻</h3>
      <div className="muted">暂无日报。{market === 'cn' ? 'A股' : '美股'}新闻采集/生成后这里会显示当日要闻。</div>
    </div>
  )
  return (
    <>
      <div className="hint">
        📰 每日金融要闻日报（由新闻源采集 + AI 分级合成）。<b>纯资讯参考,与选股策略完全独立,非投资建议。</b>
        {date && <span className="muted"> · {date} · 基于 {n} 条要闻</span>}
      </div>

      {d.overview && <div className="card"><h3>今日综述</h3><p style={{ margin: 0, lineHeight: 1.7 }}>{d.overview}</p></div>}

      <div className="row">
        <div className="card" style={{ flex: 1 }}>
          <h3>🌍 世界大事</h3>
          {(d.world || []).map((x, i) => (
            <div key={i} style={{ marginBottom: 10 }}>
              <div><b>{x.title}</b> <span className={`pill ${toneCls(x.tone)}`} style={{ fontSize: 11 }}>{x.tone}</span></div>
              <div className="muted" style={{ fontSize: 13 }}>{x.impact}</div>
            </div>
          ))}
          {!(d.world || []).length && <div className="muted">—</div>}
        </div>
        <div className="card" style={{ flex: 1 }}>
          <h3>🇨🇳 国内大事</h3>
          {(d.domestic || []).map((x, i) => (
            <div key={i} style={{ marginBottom: 10 }}>
              <div><b>{x.title}</b> <span className={`pill ${toneCls(x.tone)}`} style={{ fontSize: 11 }}>{x.tone}</span></div>
              <div className="muted" style={{ fontSize: 13 }}>{x.impact}</div>
            </div>
          ))}
          {!(d.domestic || []).length && <div className="muted">—</div>}
        </div>
      </div>

      {(d.market_impact || []).length > 0 && (
        <div className="card">
          <h3>📊 板块影响</h3>
          <div className="tbl-scroll">
            <table>
              <thead><tr><th>板块/主题</th><th>原因</th><th>方向</th></tr></thead>
              <tbody>
                {(d.market_impact || []).map((x, i) => (
                  <tr key={i}><td><b>{x.sector}</b></td><td className="muted">{x.reason}</td>
                    <td className={toneCls(x.tone)}>{x.tone}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {(d.global_transmission || []).length > 0 && (
        <div className="card">
          <h3>🔗 全球传导 <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>· 全球事件 → A股板块,含提前/滞后</span></h3>
          <div className="tbl-scroll">
            <table>
              <thead><tr><th>全球事件</th><th>传导板块</th><th>时序(提前/滞后)</th><th>方向</th></tr></thead>
              <tbody>
                {(d.global_transmission || []).map((x, i) => (
                  <tr key={i}><td><b>{x.event}</b></td><td>{x.cn_sectors}</td>
                    <td className="muted">{x.timing}</td><td className={toneCls(x.tone)}>{x.tone}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {cal.length > 0 && (
        <div className="card">
          <h3>📅 未来事件日历</h3>
          <div className="tbl-scroll">
            <table>
              <thead><tr><th>日期</th><th>类别</th><th>事件</th></tr></thead>
              <tbody>
                {cal.slice(0, 20).map((e, i) => (
                  <tr key={i}><td className="muted">{e.event_date}</td>
                    <td><span className="pill muted" style={{ fontSize: 11 }}>{e.category === 'earnings' ? '财报' : e.category === 'macro' ? '宏观' : e.category}</span></td>
                    <td>{e.title}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="src-cite">📰 资讯由新闻源(财联社/央视/东财/GDELT 等)采集,AI 分级合成。研究经严格回测:
        新闻对 A股无强可交易 alpha,本页仅作信息/情境参考,<b>非策略信号,非投资建议</b>。</div>
    </>
  )
}
