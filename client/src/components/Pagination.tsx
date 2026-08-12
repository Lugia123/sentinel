import { useState } from 'react'

// 通用分页条:N 条 · 第 x/y 页 · 上一页 · 页码(首尾+当前邻近,省略号)· 下一页 · 每页N条 · 跳至。
// 受控:total/page(1基)/size + onPage/onSize。数据量小时全在前端切片,翻页零延迟。
export default function Pagination({ total, page, size, sizes = [20, 50, 100], onPage, onSize }: {
  total: number; page: number; size: number
  sizes?: number[]
  onPage: (p: number) => void
  onSize: (s: number) => void
}) {
  const pages = Math.max(1, Math.ceil(total / size))
  const cur = Math.min(page, pages)
  const [jump, setJump] = useState('')
  if (total === 0) return null

  // 页码序列:首、尾、当前±1,断裂处插省略号
  const nums: (number | '…')[] = []
  const raw = [1, 2, cur - 1, cur, cur + 1, pages - 1, pages].filter((n) => n >= 1 && n <= pages)
  let prev = 0
  for (const n of Array.from(new Set(raw)).sort((a, b) => a - b)) {
    if (prev && n - prev > 1) nums.push('…')
    nums.push(n); prev = n
  }

  const go = (p: number) => { const t = Math.min(Math.max(1, p), pages); if (t !== cur) onPage(t) }
  const doJump = () => { const v = parseInt(jump, 10); if (v >= 1) { go(v); setJump('') } }

  return (
    <div className="pagination">
      <span className="pg-total">{total} 条 · 第 {cur}/{pages} 页</span>
      <div className="pg-ctrls">
        <button className="pg-btn" disabled={cur <= 1} onClick={() => go(cur - 1)}>上一页</button>
        {nums.map((n, i) => n === '…'
          ? <span key={'e' + i} className="pg-ellipsis">…</span>
          : <button key={n} className={'pg-btn pg-num' + (n === cur ? ' on' : '')} onClick={() => go(n)}>{n}</button>)}
        <button className="pg-btn" disabled={cur >= pages} onClick={() => go(cur + 1)}>下一页</button>
        <select className="pg-size" value={size} onChange={(e) => onSize(parseInt(e.target.value, 10))}>
          {sizes.map((s) => <option key={s} value={s}>{s} 条/页</option>)}
        </select>
        <span className="pg-jump">跳至
          <input value={jump} onChange={(e) => setJump(e.target.value.replace(/[^0-9]/g, ''))}
            onKeyDown={(e) => e.key === 'Enter' && doJump()} onBlur={doJump} aria-label="跳至页码" />
        </span>
      </div>
    </div>
  )
}
