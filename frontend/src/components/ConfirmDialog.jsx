import React, { useEffect, useState } from 'react'
import { AlertTriangle, X } from 'lucide-react'

export default function ConfirmDialog({
  isOpen,
  title = 'Confirm Action',
  message,
  consequences,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  confirmTone = 'primary', // 'primary' | 'danger' | 'ok'
  onConfirm,
  onCancel,
  requireNote = false,
  notePlaceholder = 'Enter required explanation / note…',
  noteLabel = 'Rejection note (required)',
}) {
  const [note, setNote] = useState('')
  const [noteError, setNoteError] = useState('')

  // A previous note must not carry into the next dialog.
  useEffect(() => {
    if (isOpen) {
      setNote('')
      setNoteError('')
    }
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return
    const onKey = (e) => e.key === 'Escape' && onCancel?.()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isOpen, onCancel])

  if (!isOpen) return null

  const handleConfirm = () => {
    if (requireNote && (!note || !note.trim())) {
      setNoteError('A note is required to proceed with this rejection.')
      return
    }
    setNoteError('')
    onConfirm(note)
  }

  const toneClass = { primary: 'btn-primary', danger: 'btn-bad', ok: 'btn-ok' }[confirmTone] || 'btn-primary'

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/70 p-4 backdrop-blur-sm sm:items-center" onMouseDown={(e) => e.target === e.currentTarget && onCancel?.()}>
      <div role="dialog" aria-modal="true" aria-label={title} className="card flex max-h-[90vh] w-full max-w-lg flex-col shadow-pop animate-fade-in">
        <header className="flex items-center justify-between gap-3 border-b border-ink-600/70 px-5 py-3.5">
          <div className="flex min-w-0 items-center gap-2 text-base font-semibold text-slate-100">
            <AlertTriangle className={`shrink-0 ${confirmTone === 'danger' ? 'text-rose-400' : 'text-amber-400'}`} size={18} />
            <h3 className="truncate">{title}</h3>
          </div>
          <button type="button" onClick={onCancel} className="text-slate-400 transition-colors hover:text-slate-100" aria-label="Close dialog">
            <X size={18} />
          </button>
        </header>

        <div className="space-y-4 overflow-y-auto p-5">
          {message && <p className="text-sm leading-relaxed text-slate-300">{message}</p>}

          {consequences && (
            <div className="space-y-1 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-300">
              <div className="flex items-center gap-1.5 font-semibold uppercase tracking-wide">
                <AlertTriangle size={13} />
                <span>Impact &amp; consequences</span>
              </div>
              <p className="break-words leading-relaxed">{consequences}</p>
            </div>
          )}

          {requireNote && (
            <div className="space-y-1.5">
              <label htmlFor="confirm-note" className="label">{noteLabel}</label>
              <textarea
                id="confirm-note"
                rows={3}
                className="input"
                placeholder={notePlaceholder}
                value={note}
                autoFocus
                onChange={(e) => {
                  setNote(e.target.value)
                  if (noteError) setNoteError('')
                }}
              />
              {noteError && <p className="text-xs text-rose-400">{noteError}</p>}
            </div>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2.5 rounded-b-xl border-t border-ink-600/70 bg-ink-900 px-5 py-3">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>{cancelLabel}</button>
          <button type="button" className={`btn ${toneClass}`} onClick={handleConfirm}>{confirmLabel}</button>
        </footer>
      </div>
    </div>
  )
}
