import { createPortal } from 'react-dom'
import { useEffect } from 'react'

// 黑金模态窗(遮罩点击/Esc 关闭)。
export default function Modal({ title, onClose, children, wide, xwide }: {
  title: React.ReactNode
  onClose: () => void
  children: React.ReactNode
  wide?: boolean
  xwide?: boolean
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])
  return createPortal(
    <div className="modal-overlay" onMouseDown={onClose}>
      <div className={`modal ${wide ? 'wide' : ''} ${xwide ? 'xwide' : ''}`} onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="modal-x" onClick={onClose} aria-label="关闭">×</button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>,
    document.body,
  )
}
