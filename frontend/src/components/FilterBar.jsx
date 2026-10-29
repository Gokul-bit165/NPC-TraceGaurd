import React from 'react'
import { Filter, RotateCcw } from 'lucide-react'

export default function FilterBar({
  children,
  onReset,
  hasActiveFilters = false,
  className = '',
}) {
  return (
    <div className={`card p-3.5 ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-1 flex-wrap items-center gap-2.5">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400 mr-1">
            <Filter size={14} className="text-sky-400" />
            <span>Filters</span>
          </div>
          {children}
        </div>
        {hasActiveFilters && onReset && (
          <button
            type="button"
            onClick={onReset}
            className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-sky-300 transition"
          >
            <RotateCcw size={12} />
            <span>Reset filters</span>
          </button>
        )}
      </div>
    </div>
  )
}
