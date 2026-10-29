import React from 'react'
import { getBandInfo } from '../utils/riskUtils.js'

export default function RiskBadge({ band, score, size = 'sm', className = '' }) {
  const b = getBandInfo(band ?? score)
  
  const sizeClasses = {
    xs: 'px-2 py-0.5 text-[10px] gap-1',
    sm: 'px-2.5 py-0.5 text-xs gap-1.5',
    md: 'px-3 py-1 text-sm gap-2',
    lg: 'px-3.5 py-1.5 text-base gap-2.5 font-bold',
  }[size] || 'px-2.5 py-0.5 text-xs gap-1.5'

  const displayScore = score !== undefined && score !== null ? ` ${score}` : ''

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
