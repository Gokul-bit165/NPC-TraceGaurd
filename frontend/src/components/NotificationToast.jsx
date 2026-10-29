import React, { useEffect } from 'react'
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react'

export default function NotificationToast({
  show,
  message,
  type = 'success', // 'success' | 'error' | 'info'
  onClose,
  duration = 4000,
}) {
  useEffect(() => {
    if (!show || !duration) return
    const timer = setTimeout(() => {
      if (onClose) onClose()
    }, duration)
    return () => clearTimeout(timer)
  }, [show, duration, onClose])

  if (!show || !message) return null

  const icons = {
    success: <CheckCircle2 className="shrink-0 text-emerald-400" size={18} />,
    error: <AlertCircle className="shrink-0 text-rose-400" size={18} />,
    info: <Info className="shrink-0 text-sky-400" size={18} />,
  }

  const borders = {
    success: 'border-emerald-500/40',
    error: 'border-rose-500/40',
    info: 'border-sky-500/40',
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className={`fixed bottom-5 left-4 right-4 z-50 ml-auto flex max-w-md items-center gap-2.5 rounded-xl border bg-ink-800 p-4 shadow-pop animate-fade-in sm:left-auto sm:right-5 ${borders[type] || borders.info}`}
    >
      {icons[type] || icons.info}
      <span className="flex-1 text-sm font-medium text-slate-200">{message}</span>
      {onClose && (
        <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-100" aria-label="Dismiss notification">
          <X size={14} />
        </button>
      )}
    </div>
  )
}
