import React from 'react'
import { getStatusInfo } from '../utils/riskUtils.js'

export default function StatusBadge({ status, label: customLabel, className = '' }) {
  const info = getStatusInfo(status)
  const text = customLabel || info.label

  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${info.bg} ${className}`}
    >
      {text}
    </span>
  )
}
