import { useEffect, useState } from 'react'
import Modal from './Modal'
import { fetchNewsItem, type NewsItemDetail } from '../api'

const clean = (t: string) => t.replace(/^【(.+?)】/, '$1').trim()
const SRC: Record<string, string> = { em_global: '东方财富', sina_global: '新浪财经', ths_global: '同花顺', cctv: '央视新闻', gdelt: '全球来源', stock_em: '东财个股' }
const srcCn = (s: string) => SRC[s] || s
// 去掉 AI 解读结尾自带的免责声明(底部已有完整版,避免重复)
const stripDisc = (html: string) => html.replace(/<p[^>]*class=["']disc["'][^>]*>[\s\S]*?<\/p>\s*$/i, '').trim()
// 无单篇 URL 的来源(新浪/央视等),用来源站内搜索兜底,让用户能找到原文
const searchUrl = (source: string, title: string) => {
  const q = encodeURIComponent(clean(title))
  if (source === 'sina_global') return `https://search.sina.com.cn/?q=${q}&c=news`
  if (source === 'cctv') return `https://search.cctv.com/search.php?qtext=${q}`
  return `https://www.baidu.com/s?wd=${q}`
}

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
          <h3 style={{ marginTop: 0, fontSize: 18, lineHeight: 1.4, color: 'var(--ink)', fontWeight: 700 }}>{clean(d.title)}</h3>
          <div className="muted" style={{ fontSize: 12.5, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span>{d.published?.slice(0, 16)}</span>
            <span>· {srcCn(d.source)}</span>
            <a className="src-link" href={d.url || searchUrl(d.source, d.title)} target="_blank" rel="noreferrer">
              {d.url ? '查看来源 ↗' : '搜索原文 ↗'}
            </a>
          </div>
          {d.body && clean(d.body) !== clean(d.title) &&
            <p style={{ lineHeight: 1.75, color: 'var(--ink-soft)', fontSize: 14 }}>{clean(d.body)}</p>}

          {d.sectors && d.sectors.length > 0 && (
            <div style={{ margin: '12px 0' }}>
              <span className="muted" style={{ marginRight: 6 }}>涉及板块</span>
              {d.sectors.map((s, i) => <span key={i} className="sec-tag">{s}</span>)}
            </div>
          )}

          {d.interpret
            ? <div className="doc-html" dangerouslySetInnerHTML={{ __html: stripDisc(d.interpret) }} />
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
