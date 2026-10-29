import React from 'react'

export default function PageHeader({
  title,
  description,
  right,
  badge,
  icon: Icon,
  className = '',
}) {
  return (
    <div className={`flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between ${className}`}>
      <div className="flex min-w-0 items-start gap-3">
        {Icon && (
          <div className="hidden h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-sky-500/25 bg-sky-500/10 text-sky-400 sm:flex">
            <Icon size={20} />
          </div>
        )}
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-xl font-semibold tracking-tight text-slate-100 sm:text-2xl">{title}</h1>
            {badge}
          </div>
          {description && (
            <p className="max-w-3xl text-sm leading-relaxed text-slate-400">{description}</p>
          )}
        </div>
      </div>
      {right && <div className="flex shrink-0 flex-wrap items-center gap-2.5">{right}</div>}
    </div>
  )
}
