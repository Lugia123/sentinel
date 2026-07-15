import { useEffect, useState } from 'react'
import Modal from './Modal'
import { fetchNewsItem, type NewsItemDetail } from '../api'

// 新闻详情弹窗:AI 解读(涉及板块+传导)+ 来源链接。资讯参考,非投资建议。
export default function NewsItemModal({ id, onClose }: { id: number; onClose: () => void }) {
  const [d, setD] = useState<NewsItemDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const load = (force = false) => { setLoading(true); fetchNewsItem(id, force).then(setD).finally(() => setLoading(false)) }
  useEffect(() => { load(false) }, [id])

  return (
    <Modal wide title="📰 新闻详情" onClose={onClose}>
      {loading && !d && <div className="muted">加载并解读中…（首次约 20 秒）</div>}
      {d && (
        <div>
          <h3 style={{ marginTop: 0 }}>{d.title}</h3>
          <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>
            {d.published?.slice(0, 16)} · {d.source}
            {d.url && <> · <a href={d.url} target="_blank" rel="noreferrer">查看来源 ↗</a></>}
          </div>
          {d.body && d.body !== d.title && <p style={{ lineHeight: 1.7 }}>{d.body}</p>}

          {d.sectors && d.sectors.length > 0 && (
            <div style={{ margin: '10px 0' }}>
              涉及板块:{d.sectors.map((s, i) => <span key={i} className="pill" style={{ marginRight: 6 }}>{s}</span>)}
            </div>
          )}

          {d.interpret
            ? <div className="doc-html" dangerouslySetInnerHTML={{ __html: d.interpret }} />
            : (
              <div className="muted" style={{ padding: '10px 0' }}>
                {d.ai_error
                  ? <>AI 解读暂不可用（{d.ai_error.includes('Balance') || d.ai_error.includes('余额') ? 'DeepSeek 账户余额不足,充值后可用' : d.ai_error}）。可点上方「查看来源」阅读原文。</>
                  : <>暂无 AI 解读。<button className="ghost mini" onClick={() => load(true)}>生成解读</button></>}
              </div>
            )}
          <div className="src-cite">AI 依常识解读,非实时核实,非投资建议。原文请以来源链接为准。</div>
        </div>
      )}
    </Modal>
  )
}
