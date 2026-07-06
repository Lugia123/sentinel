import { useEffect, useRef, useState } from 'react'
import type { SearchOption } from './SearchSelect'

// 黑金多选搜索下拉:已选显示为 chips,输入过滤,点选加入,×移除。
// 用于「分析走势」多股对比——只列有档位历史的股。
export default function MultiSelect({ value, options, onChange, placeholder = '搜索添加…', max = 8 }: {
  value: string[]
  options: SearchOption[]
  onChange: (v: string[]) => void
  placeholder?: string
  max?: number
}) {
  const [open, setOpen] = useState(false)
  const [qy, setQy] = useState('')
  const [active, setActive] = useState(0)
  const wrap = useRef<HTMLDivElement>(null)

  const q = qy.trim().toLowerCase()
  const avail = options.filter((o) => !value.includes(o.value))
  const filtered = q
    ? avail.filter((o) => o.value.toLowerCase().includes(q) || (o.label + (o.sub || '') + (o.keywords || '')).toLowerCase().includes(q))
    : avail
  const shown = filtered.slice(0, 50)
  const full = value.length >= max

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false) }
    const onScroll = (e: Event) => { if (!wrap.current || !wrap.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    window.addEventListener('scroll', onScroll, true)
    return () => { document.removeEventListener('mousedown', onDoc); window.removeEventListener('scroll', onScroll, true) }
  }, [open])
  useEffect(() => { setActive(0) }, [qy])

  const add = (v: string) => { if (!full) { onChange([...value, v]); setQy('') } }
  const remove = (v: string) => onChange(value.filter((x) => x !== v))
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setActive((i) => Math.min(shown.length - 1, i + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(0, i - 1)) }
    else if (e.key === 'Enter') { e.preventDefault(); if (shown[active]) add(shown[active].value) }
    else if (e.key === 'Backspace' && !qy && value.length) { remove(value[value.length - 1]) }
    else if (e.key === 'Escape') { setOpen(false) }
  }
  const lbl = (v: string) => options.find((o) => o.value === v)?.label || v

  return (
    <div className="ss" ref={wrap} style={{ minWidth: 320 }}>
      <div className="ms-chips ss-input" style={{ cursor: 'text' }} onClick={() => setOpen(true)}>
        {value.map((v) => (
          <span key={v} className="ms-chip">{lbl(v)}<button onClick={(e) => { e.stopPropagation(); remove(v) }} aria-label="移除">×</button></span>
        ))}
        <input className="ms-inline" value={qy} placeholder={value.length ? '' : placeholder}
          onChange={(e) => { setQy(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)} onKeyDown={onKey}
          style={{ flex: 1, minWidth: 80, background: 'none', border: 0, color: 'var(--ink)', fontSize: 13, outline: 'none' }} />
      </div>
      {open && (
        <div className="ss-panel" role="listbox">
          {full && <div className="ss-empty">最多选 {max} 只(先移除再加)</div>}
          {!full && shown.length === 0 && <div className="ss-empty">无匹配</div>}
          {!full && shown.map((o, i) => (
            <div key={o.value} role="option" className={`ss-opt ${i === active ? 'active' : ''}`}
              onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); add(o.value) }}>
              <span className="ss-label">{o.label}</span>
              {o.sub && <span className="ss-sub">{o.sub}</span>}
            </div>
          ))}
          {!full && filtered.length > shown.length && <div className="ss-more">还有 {filtered.length - shown.length} 项,继续输入缩小</div>}
        </div>
      )}
    </div>
  )
}
