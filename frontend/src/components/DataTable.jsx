import React, { useMemo, useState } from 'react'
import { ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react'
import LoadingState from './LoadingState.jsx'
import EmptyState from './EmptyState.jsx'
import ErrorState from './ErrorState.jsx'
import Pagination from './Pagination.jsx'

export default function DataTable({
  columns = [],
  data = [],
  loading = false,
  error = null,
  onRowClick,
  selectedRowId,
  idKey = 'id',
  emptyTitle = 'No data available',
  emptyMessage = 'There are no records to display.',
  sortable = true,
  defaultSortKey,
  defaultSortDir = 'desc',
  pagination = null, // { page, pageSize, total, onPageChange }
  className = '',
}) {
  const [sortKey, setSortKey] = useState(defaultSortKey)
  const [sortDir, setSortDir] = useState(defaultSortDir)

  const handleHeaderClick = (col) => {
    if (!sortable || col.sortable === false) return
    if (sortKey === col.key) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(col.key)
      setSortDir('desc')
    }
  }

  const displayData = useMemo(() => {
    const rows = [...(data || [])]
    if (!sortKey || pagination?.serverSort) return rows
    return rows.sort((a, b) => {
      const va = a[sortKey]
      const vb = b[sortKey]
      if (va === vb) return 0
      if (va === null || va === undefined) return 1
      if (vb === null || vb === undefined) return -1
      if (typeof va === 'string') {
        const cmp = va.localeCompare(vb)
        return sortDir === 'asc' ? cmp : -cmp
      }
      return sortDir === 'asc' ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1)
    })
  }, [data, sortKey, sortDir, pagination?.serverSort])

  return (
    <div className={`card overflow-hidden ${className}`}>
      {error && <div className="p-4"><ErrorState error={error} /></div>}

      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead className="border-b border-ink-600/70 bg-ink-900">
            <tr>
              {columns.map((col) => {
                const isSorted = sortKey === col.key
                const canSort = sortable && col.sortable !== false
                return (
                  <th
                    key={col.key}
                    scope="col"
                    aria-sort={isSorted ? (sortDir === 'asc' ? 'ascending' : 'descending') : undefined}
                    onClick={() => canSort && handleHeaderClick(col)}
                    className={`th select-none ${col.className || ''} ${canSort ? 'cursor-pointer hover:text-slate-100' : ''}`}
                  >
                    <div className={`flex items-center gap-1.5 ${col.align === 'right' ? 'justify-end' : ''}`}>
                      <span>{col.label}</span>
                      {canSort && (
                        <span className="text-slate-500">
                          {isSorted ? (
                            sortDir === 'asc' ? <ArrowUp size={13} className="text-sky-400" /> : <ArrowDown size={13} className="text-sky-400" />
                          ) : (
                            <ArrowUpDown size={12} className="opacity-40" />
                          )}
                        </span>
                      )}
                    </div>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-600/50">
            {loading && displayData.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="p-0"><LoadingState /></td>
              </tr>
            ) : displayData.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="p-0">
                  <EmptyState title={emptyTitle} message={emptyMessage} />
                </td>
              </tr>
            ) : (
              displayData.map((row, idx) => {
                const isSelected = selectedRowId !== undefined && row[idKey] === selectedRowId
                return (
                  <tr
                    key={row[idKey] ?? idx}
                    onClick={() => onRowClick && onRowClick(row)}
                    className={`transition-colors ${onRowClick ? 'cursor-pointer hover:bg-ink-700/50' : ''} ${
                      isSelected ? 'bg-sky-500/10 shadow-[inset_2px_0_0_rgb(var(--sky-500))]' : ''
                    }`}
                  >
                    {columns.map((col) => (
                      <td key={col.key} className={`td ${col.align === 'right' ? 'text-right' : ''} ${col.cellClassName || ''}`}>
                        {col.render ? col.render(row[col.key], row, idx) : (row[col.key] ?? '—')}
                      </td>
                    ))}
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {pagination && (
        <div className="border-t border-ink-600/70 bg-ink-900 p-3">
          <Pagination
            page={pagination.page}
            pageSize={pagination.pageSize}
            total={pagination.total}
            onPageChange={pagination.onPageChange}
          />
        </div>
      )}
    </div>
  )
}
