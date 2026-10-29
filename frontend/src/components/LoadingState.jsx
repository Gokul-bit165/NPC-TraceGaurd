import React from 'react'
import { Loader2 } from 'lucide-react'

// `variant="page"` renders a skeleton of a typical page (header, stat row, two panels) so the layout
// does not jump when data arrives; the default is a compact inline spinner.
export default function LoadingState({ message = 'Loading security data…', minHeight = 'h-48', variant = 'inline' }) {
  if (variant === 'page') {
    return (
      <div className="space-y-6" role="status" aria-live="polite">
        <span className="sr-only">{message}</span>
        <div className="space-y-2">
          <div className="skeleton h-6 w-64" />
          <div className="skeleton h-4 w-full max-w-xl" />
        </div>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="card p-4">
              <div className="skeleton h-3 w-20" />
              <div className="skeleton mt-3 h-7 w-16" />
            </div>
          ))}
        </div>
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="card p-4 lg:col-span-2">
            <div className="skeleton h-4 w-40" />
            <div className="skeleton mt-4 h-48 w-full" />
          </div>
          <div className="card p-4">
            <div className="skeleton h-4 w-32" />
            <div className="mt-4 space-y-3">
              {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-9 w-full" />)}
            </div>
          </div>
        </div>
        <div className="flex items-center justify-center gap-2 text-sm text-slate-400">
          <Loader2 className="animate-spin text-sky-400" size={16} />
          {message}
        </div>
      </div>
    )
  }

  return (
    <div className={`flex flex-col items-center justify-center gap-3 p-8 text-slate-400 ${minHeight}`} role="status" aria-live="polite">
      <Loader2 className="animate-spin text-sky-400" size={24} />
      <span className="text-sm font-medium">{message}</span>
    </div>
  )
}
