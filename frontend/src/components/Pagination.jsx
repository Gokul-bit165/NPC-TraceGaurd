import React from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

export default function Pagination({
  page = 0,
  pageSize = 25,
  total = 0,
  onPageChange,
  className = '',
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const startRecord = total === 0 ? 0 : page * pageSize + 1
  const endRecord = Math.min((page + 1) * pageSize, total)

  return (
    <div className={`flex flex-wrap items-center justify-between gap-3 text-xs text-slate-400 ${className}`}>
      <div className="font-medium">
        Showing <span className="text-slate-200">{startRecord.toLocaleString()}</span> to{' '}
        <span className="text-slate-200">{endRecord.toLocaleString()}</span> of{' '}
        <span className="text-slate-200">{total.toLocaleString()}</span> entries
      </div>
      <div className="flex items-center gap-2">
        <button
          className="btn btn-ghost !px-2.5 !py-1 text-xs"
          disabled={page === 0}
          onClick={() => onPageChange(page - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft size={14} /> Previous
        </button>
        <span className="px-2 font-mono text-slate-300">
          Page {page + 1} of {totalPages}
        </span>
        <button
          className="btn btn-ghost !px-2.5 !py-1 text-xs"
          disabled={page + 1 >= totalPages}
          onClick={() => onPageChange(page + 1)}
          aria-label="Next page"
        >
          Next <ChevronRight size={14} />
        </button>
      </div>
    </div>
  )
}
