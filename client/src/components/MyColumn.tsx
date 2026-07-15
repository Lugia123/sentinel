import { useEffect, useState } from 'react'
import { fetchColumn, saveColumnSectors, generateColumn, type ColumnDigest, type Market } from '../api'

const toneCls = (t?: string) => (t === '利好' ? 'up' : t === '利空' ? 'down' : 'muted')

// 我的板块专栏:用户自定义关注行业/板块 → AI 生成聚焦专栏(用户隔离)。
export default function MyColumn({ market = 'cn' }: { market?: Market }) {
  const [sectors, setSectors] = useState<string[]>([])
  const [digest, setDigest] = useState<ColumnDigest | null>(null)
  const [input, setInput] = useState('')
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => { fetchColumn().then((r) => { setSectors(r.sectors); setDigest(r.digest); if (r.sectors.length === 0) setEditing(true) }) }, [market])

  const add = () => { const s = input.trim(); if (s && !sectors.includes(s) && sectors.length < 8) { setSectors([...sectors, s]); setInput('') } }
  const del = (s: string) => setSectors(sectors.filter((x) => x !== s))
  const save = async () => { setBusy(true); await saveColumnSectors(sectors); setEditing(false); const r = await generateColumn(); setDigest(r.digest); setBusy(false) }
  const refresh = async () => { setBusy(true); const r = await generateColumn(); setDigest(r.digest); setBusy(false) }

  return (
    <div className="card" style={{ borderColor: 'var(--gold)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <h3 style={{ margin: 0 }}>⭐ 我的板块专栏 <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>· 只属于你,聚焦你关注的行业</span></h3>
        <div>
          {!editing && <button className="ghost mini" onClick={() => setEditing(true)}>✎ 设置板块</button>}
          {!editing && sectors.length > 0 && <button className="ghost mini" onClick={refresh} disabled={busy}>{busy ? '生成中…' : '刷新专栏'}</button>}
        </div>
      </div>

      {editing ? (
        <div style={{ marginTop: 10 }}>
          <div style={{ marginBottom: 8 }}>
            {sectors.map((s) => <span key={s} className="picked-chip" style={{ marginRight: 6 }}>{s}<button onClick={() => del(s)} aria-label="删">×</button></span>)}
          </div>
          <div className="pos-add" style={{ margin: 0 }}>
            <input placeholder="输入行业/板块,如 半导体、白酒、新能源车" value={input}
              onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && add()} style={{ width: 240 }} />
            <button onClick={add} disabled={sectors.length >= 8}>+ 添加</button>
            <button className="primary" onClick={save} disabled={busy || sectors.length === 0}>{busy ? '保存生成中…' : '保存并生成专栏'}</button>
            {sectors.length > 0 && <button className="ghost mini" onClick={() => setEditing(false)}>取消</button>}
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>最多 8 个板块。保存后 AI 会从当日新闻里筛出与这些板块相关的,合成专属专栏。</div>
        </div>
      ) : (
        <div style={{ marginTop: 8 }}>
          <div style={{ marginBottom: 8 }}>{sectors.map((s) => <span key={s} className="pill" style={{ marginRight: 6 }}>{s}</span>)}</div>
          {digest ? (<>
            {digest.overview && <p style={{ margin: '4px 0 12px', lineHeight: 1.7 }}>{digest.overview}</p>}
            {(digest.items || []).map((it, i) => (
              <div key={i} style={{ marginBottom: 12, paddingBottom: 8, borderBottom: '1px solid #2c2418' }}>
                <div><b>{it.sector}</b> <span className={`pill ${toneCls(it.tone)}`} style={{ fontSize: 11 }}>{it.tone}</span>
                  <span className="muted" style={{ fontSize: 13, marginLeft: 8 }}>{it.impact}</span></div>
                <ul style={{ margin: '4px 0 0', paddingLeft: 20 }}>{(it.points || []).map((p, j) => <li key={j} className="muted" style={{ fontSize: 13 }}>{p}</li>)}</ul>
              </div>
            ))}
            {!(digest.items || []).length && <div className="muted">当日暂无与所选板块相关的新闻。</div>}
          </>) : <div className="muted">还没生成专栏。点「刷新专栏」由 AI 从当日新闻合成。</div>}
        </div>
      )}
      <div className="src-cite">专属你的板块资讯,基于当日新闻 AI 合成,非投资建议。</div>
    </div>
  )
}
