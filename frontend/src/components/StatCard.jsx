import React from 'react'

const TONES = {
  sky: 'text-sky-400 bg-sky-500/10',
  amber: 'text-amber-400 bg-amber-500/10',
  violet: 'text-violet-400 bg-violet-500/10',
  rose: 'text-rose-400 bg-rose-500/10',
  emerald: 'text-emerald-400 bg-emerald-500/10',
  orange: 'text-orange-400 bg-orange-500/10',
}

export default function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  tone = 'sky',
  onClick,
  className = '',
}) {
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={`card flex w-full items-start gap-3.5 p-4 text-left transition-colors ${
        onClick ? 'cursor-pointer hover:border-sky-500/40 hover:bg-ink-700/40' : ''
      } ${className}`}
    >
      {Icon && (
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${TONES[tone] || TONES.sky}`}>
          <Icon size={20} />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs font-medium text-slate-400">{label}</div>
        <div className="mt-1 text-2xl font-semibold tabular-nums tracking-tight text-slate-100">
          {typeof value === 'number' ? value.toLocaleString() : value}
        </div>
        {sub && <div className="mt-0.5 truncate text-xs text-slate-500">{sub}</div>}
      </div>
    </Tag>
  )
}
