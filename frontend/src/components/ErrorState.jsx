import React from 'react'
import { AlertCircle, RefreshCw } from 'lucide-react'

export default function ErrorState({ error, title = 'Request failed', onRetry, className = '' }) {
  if (!error) return null

  const errorString = typeof error === 'string' ? error : error?.detail || error?.message || 'An unexpected error occurred'

  return (
    <div className={`rounded-xl border border-rose-500/30 bg-rose-500/5 p-4 ${className}`} role="alert">
      <div className="flex flex-wrap items-start gap-3">
        <AlertCircle className="mt-0.5 shrink-0 text-rose-400" size={18} />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-rose-300">{title}</div>
          <div className="mt-0.5 break-words text-sm leading-relaxed text-slate-300">{errorString}</div>
        </div>
        {onRetry && (
          <button type="button" onClick={onRetry} className="btn btn-ghost !border-rose-500/40 text-xs !text-rose-300">
            <RefreshCw size={13} />
            <span>Retry</span>
          </button>
        )}
      </div>
    </div>
  )
}
