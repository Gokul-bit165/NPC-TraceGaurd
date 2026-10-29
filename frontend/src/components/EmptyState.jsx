import React from 'react'
import { Inbox } from 'lucide-react'

export default function EmptyState({
  icon: Icon = Inbox,
  title = 'No records found',
  message = 'There are no items matching your criteria or time range.',
  action,
  actionLabel,
  className = '',
}) {
  return (
    <div className={`flex flex-col items-center justify-center px-4 py-12 text-center ${className}`}>
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full border border-ink-600 bg-ink-900 text-slate-500">
        <Icon size={22} />
      </div>
      <h4 className="text-sm font-semibold text-slate-200">{title}</h4>
      {message && <p className="mt-1 max-w-sm text-xs leading-relaxed text-slate-400">{message}</p>}
      {action && actionLabel && (
        <button type="button" onClick={action} className="btn btn-ghost mt-4 text-xs">
          {actionLabel}
        </button>
      )}
    </div>
  )
}
