import { useEffect, useRef, useState } from 'react'

export interface SelectOption {
  value: string
  label: string
  badge?: React.ReactNode // 右侧状态角标(如「已解读✓/未解读」)
}

// 黑金定制下拉(shadcn/ui Select 同款交互:键盘导航 + 勾选态 + 右侧角标),
// 纯 CSS 黑金主题,无 Tailwind/Radix 依赖。
export default function Select({ value, options, onChange, placeholder = '请选择', ariaLabel }: {
  value: string
  options: SelectOption[]
  onChange: (v: string) => void
  placeholder?: string
  ariaLabel?: string
}) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0) // 键盘高亮项
  const wrap = useRef<HTMLDivElement>(null)
  const sel = options.find((o) => o.value === value)

  // 点击外部关闭
  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false) }
    const onScroll = (e: Event) => { if (!wrap.current || !wrap.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    window.addEventListener('scroll', onScroll, true)
    return () => { document.removeEventListener('mousedown', onDoc); window.removeEventListener('scroll', onScroll, true) }
  }, [open])

  // 打开时把高亮定位到当前选中项
  useEffect(() => { if (open) setActive(Math.max(0, options.findIndex((o) => o.value === value))) }, [open])

  const pick = (v: string) => { onChange(v); setOpen(false) }

  const onKey = (e: React.KeyboardEvent) => {
    if (!open) {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') { e.preventDefault(); setOpen(true) }
      return
    }
    if (e.key === 'Escape') { setOpen(false); return }
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => Math.min(options.length - 1, i + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(0, i - 1)) }
    else if (e.key === 'Enter') { e.preventDefault(); if (options[active]) pick(options[active].value) }
  }

  return (
    <div className="sel" ref={wrap}>
      <button type="button" className="sel-trigger" aria-haspopup="listbox" aria-expanded={open} aria-label={ariaLabel}
        onClick={() => setOpen((o) => !o)} onKeyDown={onKey}>
        <span className="sel-value">{sel ? sel.label : <span className="sel-ph">{placeholder}</span>}</span>
        {sel?.badge && <span className="sel-trigger-badge">{sel.badge}</span>}
        <span className={`sel-caret ${open ? 'up' : ''}`}>▾</span>
      </button>
      {open && (
        <div className="sel-panel" role="listbox">
          {options.map((o, i) => (
            <div key={o.value} role="option" aria-selected={o.value === value}
              className={`sel-opt ${i === active ? 'active' : ''} ${o.value === value ? 'on' : ''}`}
              onMouseEnter={() => setActive(i)} onClick={() => pick(o.value)}>
              <span className="sel-check">{o.value === value ? '✓' : ''}</span>
              <span className="sel-label">{o.label}</span>
              {o.badge && <span className="sel-badge">{o.badge}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
