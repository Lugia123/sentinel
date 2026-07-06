import { useEffect, useRef, useState } from 'react'

export interface SearchOption {
  value: string
  label: string // 主文本(如代码)
  sub?: string // 次文本(如中文名·板块)
  keywords?: string // 额外可匹配文本(中文名等)
}

// 黑金搜索下拉(shadcn Combobox 同款):输入即过滤,选中触发 onPick 并清空。
// 用于「添加自定义股票」——只能从有效清单里选,杜绝打错。
export default function SearchSelect({ options, onPick, placeholder = '搜索…', emptyText = '无匹配', disabled }: {
  options: SearchOption[]
  onPick: (value: string) => void
  placeholder?: string
  emptyText?: string
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [qy, setQy] = useState('')
  const [active, setActive] = useState(0)
  const wrap = useRef<HTMLDivElement>(null)

  const q = qy.trim().toLowerCase()
  const filtered = q
    ? options.filter((o) => o.value.toLowerCase().includes(q) || (o.label + (o.sub || '') + (o.keywords || '')).toLowerCase().includes(q))
    : options
  const shown = filtered.slice(0, 50)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false) }
    // 页面滚动时关下拉(避免异步滚动时透出背后内容);下拉自身内部滚动不触发 window scroll
    const onScroll = (e: Event) => { if (!wrap.current || !wrap.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    window.addEventListener('scroll', onScroll, true)
    return () => { document.removeEventListener('mousedown', onDoc); window.removeEventListener('scroll', onScroll, true) }
  }, [open])
  useEffect(() => { setActive(0) }, [qy])

  const pick = (v: string) => { onPick(v); setQy(''); setOpen(false) }
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setActive((i) => Math.min(shown.length - 1, i + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(0, i - 1)) }
    else if (e.key === 'Enter') { e.preventDefault(); if (shown[active]) pick(shown[active].value) }
    else if (e.key === 'Escape') { setOpen(false) }
  }

  return (
    <div className="ss" ref={wrap}>
      <input className="ss-input" value={qy} placeholder={placeholder} disabled={disabled}
        onChange={(e) => { setQy(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)} onKeyDown={onKey} />
      {open && !disabled && (
        <div className="ss-panel" role="listbox">
          {shown.length === 0 && <div className="ss-empty">{emptyText}</div>}
          {shown.map((o, i) => (
            <div key={o.value} role="option" className={`ss-opt ${i === active ? 'active' : ''}`}
              onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); pick(o.value) }}>
              <span className="ss-label">{o.label}</span>
              {o.sub && <span className="ss-sub">{o.sub}</span>}
            </div>
          ))}
          {filtered.length > shown.length && <div className="ss-more">还有 {filtered.length - shown.length} 项,继续输入缩小范围</div>}
        </div>
      )}
    </div>
  )
}
