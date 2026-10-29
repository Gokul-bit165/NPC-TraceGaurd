import React from 'react'

// Tone drives a thin accent rail and the icon tint. Colour is never the only signal: callers pass a text `sub`/`badge`.
const TONES = {
  sky: { icon: 'text-sky-400 bg-sky-500/10', rail: 'bg-sky-500' },
  amber: { icon: 'text-amber-400 bg-amber-500/10', rail: 'bg-amber-500' },
  violet: { icon: 'text-violet-400 bg-violet-500/10', rail: 'bg-violet-500' },
  rose: { icon: 'text-rose-400 bg-rose-500/10', rail: 'bg-rose-500' },
  emerald: { icon: 'text-emerald-400 bg-emerald-500/10', rail: 'bg-emerald-500' },
  orange: { icon: 'text-orange-400 bg-orange-500/10', rail: 'bg-orange-500' },
}

export default function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  badge,
  tone = 'sky',
  size = 'md', // 'lg' gives the headline metric more weight
  onClick,
  className = '',
}) {
  const Tag = onClick ? 'button' : 'div'
  const t = TONES[tone] || TONES.sky
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={`card group relative flex w-full flex-col overflow-hidden text-left transition-colors ${size === 'lg' ? 'p-5' : 'p-4'} ${
        onClick ? 'cursor-pointer hover:border-sky-500/40 hover:bg-ink-700/40' : ''
      } ${className}`}
    >
      <span aria-hidden="true" className={`absolute inset-y-0 left-0 w-[3px] ${t.rail} opacity-80`} />
      <div className="flex items-center justify-between gap-2">
        <span className="eyebrow truncate">{label}</span>
        {Icon && (
          <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${t.icon}`}>
            <Icon size={16} />
          </span>
        )}
      </div>
      <div className={`num mt-2 ${size === 'lg' ? 'text-4xl' : 'text-3xl'}`}>
        {typeof value === 'number' ? value.toLocaleString() : value}
      </div>
      <div className="mt-1.5 flex items-center gap-2 text-xs text-slate-400">
        {badge}
        {sub && <span className="truncate">{sub}</span>}
      </div>
    </Tag>
  )
}
