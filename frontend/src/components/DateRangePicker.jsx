import React from 'react'
import { Calendar } from 'lucide-react'

export default function DateRangePicker({
  days = 14,
  onChangeDays,
  presets = [
    { label: '7 days', value: 7 },
    { label: '14 days', value: 14 },
    { label: '30 days', value: 30 },
    { label: '90 days', value: 90 },
  ],
  startDate,
  endDate,
  onDateChange,
  showCustomDates = false,
  className = '',
}) {
  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`}>
      {presets && (
        <div className="flex items-center rounded-lg border border-ink-600 bg-ink-800 p-0.5" role="group" aria-label="Date range">
          {presets.map((p) => {
            const active = days === p.value
            return (
              <button
                key={p.value}
                type="button"
                aria-pressed={active}
                onClick={() => onChangeDays && onChangeDays(p.value)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  active ? 'bg-sky-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-100'
                }`}
              >
                {p.label}
              </button>
            )
          })}
        </div>
      )}

      {showCustomDates && (
        <div className="flex items-center gap-1.5 text-xs text-slate-400">
          <Calendar size={14} className="text-slate-500" />
          <input type="date" className="input !w-auto !py-1 !text-xs" value={startDate || ''} onChange={(e) => onDateChange && onDateChange('start', e.target.value)} title="Start date" />
          <span className="text-slate-500">to</span>
          <input type="date" className="input !w-auto !py-1 !text-xs" value={endDate || ''} onChange={(e) => onDateChange && onDateChange('end', e.target.value)} title="End date" />
        </div>
      )}
    </div>
  )
}
