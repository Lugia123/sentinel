import { useEffect, useState } from 'react'
import Modal from './Modal'
import { fetchEventInterpret, type EventInterpret } from '../api'

// 去掉 AI 解读结尾自带的免责声明(底部已有完整版,避免重复)
const stripDisc = (html: string) => html.replace(/<p[^>]*class=["']disc["'][^>]*>[\s\S]*?<\/p>\s*$/i, '').trim()

// 「世界大事/国内大事」条目的深度 AI 解读弹窗(digest 事件无来源单条,按事件本身现场解读)。
export default function EventInterpretModal({ event, onClose }: { event: { title: string; context: string; kind: string }; onClose: () => void }) {
  const [d, setD] = useState<EventInterpret | null>(null)
  const [loading, setLoading] = useState(true)
  const load = (force = false) => { setLoading(true); fetchEventInterpret(event.title, event.context, force).then(setD).finally(() => setLoading(false)) }
  useEffect(() => { load(false) }, [event.title])

  return (
    <Modal wide title={`${event.kind} · 深度解读`} onClose={onClose}>
      <h3 style={{ marginTop: 0, fontSize: 18, lineHeight: 1.4, color: 'var(--ink)', fontWeight: 700 }}>{event.title}</h3>
      {event.context && <p style={{ lineHeight: 1.7, color: 'var(--ink-soft)', fontSize: 13.5, margin: '0 0 12px' }}>{event.context}</p>}

      {loading && !d && <div className="muted">AI 解读中…（首次约 20 秒）</div>}
      {d && (
        <div>
          {d.sectors && d.sectors.length > 0 && (
            <div style={{ margin: '4px 0 12px' }}>
              <span className="muted" style={{ marginRight: 6 }}>涉及板块</span>
              {d.sectors.map((s, i) => <span key={i} className="sec-tag">{s}</span>)}
            </div>
          )}
          {d.interpret
            ? <div className="doc-html" dangerouslySetInnerHTML={{ __html: stripDisc(d.interpret) }} />
            : (
              <div className="muted" style={{ padding: '10px 0' }}>
                {d.ai_error
                  ? <>AI 解读暂不可用（{d.ai_error.includes('Balance') || d.ai_error.includes('余额') ? 'DeepSeek 账户余额不足,充值后可用' : d.ai_error}）。</>
                  : <>暂无解读。<button className="ghost mini" onClick={() => load(true)}>重新生成</button></>}
              </div>
            )}
          <div className="src-cite">AI 依常识解读,非实时核实,非投资建议。</div>
        </div>
      )}
    </Modal>
  )
}
