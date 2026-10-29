import React from 'react'
import { getBandInfo } from '../utils/riskUtils.js'

// `aligned` renders a fixed-width badge for table columns: dot + label on the left, score right-aligned
// in tabular figures, so Critical 100 / Critical 90 / Medium 36 line up row to row.
export default function RiskBadge({ band, score, size = 'sm', aligned = false, className = '' }) {
  const b = getBandInfo(band ?? score)
  
  const sizeClasses = {
    xs: 'px-2 py-0.5 text-[10px] gap-1',
    sm: 'px-2.5 py-0.5 text-xs gap-1.5',
    md: 'px-3 py-1 text-sm gap-2',
    lg: 'px-3.5 py-1.5 text-base gap-2.5 font-bold',
  }[size] || 'px-2.5 py-0.5 text-xs gap-1.5'

  const displayScore = score !== undefined && score !== null ? ` ${score}` : ''

  if (aligned) {
    const hasScore = score !== undefined && score !== null
    return (
      <span
        className={`inline-flex h-6 w-[116px] items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 text-xs font-semibold ${b.cls} ${className}`}
      >
        <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: b.dot }} />
        <span className="text-left">{b.label}</span>
        {hasScore && <span className="ml-auto min-w-[3ch] text-right tabular-nums">{score}</span>}
      </span>
    )
  }

  return (
    <span
      className={`inline-flex items-center rounded-full border font-semibold ${b.cls} ${sizeClasses} ${className}`}
    >
      <span
        className="shrink-0 rounded-full"
        style={{
          width: size === 'lg' ? 8 : 6,
          height: size === 'lg' ? 8 : 6,
          background: b.dot,
        }}
      />
      <span>{b.label}{displayScore}</span>
    </span>
  )
}
