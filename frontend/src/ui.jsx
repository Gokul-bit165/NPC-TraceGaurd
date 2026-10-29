import React from 'react'
import { getBandInfo } from './utils/riskUtils.js'
import { formatDate, formatPct } from './utils/formatters.js'
import LoadingState from './components/LoadingState.jsx'
import ErrorState from './components/ErrorState.jsx'

// Re-export new modular components for backward compatibility
export { default as StatCard } from './components/StatCard.jsx'
export { default as RiskBadge } from './components/RiskBadge.jsx'
export { default as StatusBadge } from './components/StatusBadge.jsx'
export { default as DataTable } from './components/DataTable.jsx'
export { default as SearchBar } from './components/SearchBar.jsx'
export { default as FilterBar } from './components/FilterBar.jsx'
export { default as DateRangePicker } from './components/DateRangePicker.jsx'
export { default as Pagination } from './components/Pagination.jsx'
export { default as LoadingState } from './components/LoadingState.jsx'
export { default as EmptyState } from './components/EmptyState.jsx'
export { default as ErrorState } from './components/ErrorState.jsx'
export { default as ConfirmDialog } from './components/ConfirmDialog.jsx'
export { default as EvidencePanel } from './components/EvidencePanel.jsx'
export { default as NotificationToast } from './components/NotificationToast.jsx'
export { default as PageHeader } from './components/PageHeader.jsx'
export { default as ErrorBoundary } from './components/ErrorBoundary.jsx'
export { ThemeToggle } from './theme.jsx'

export function Band({ band, score }) {
  const b = getBandInfo(band ?? score)
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${b.cls}`}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: b.dot }} />
      {b.label}{score !== undefined && score !== null ? ` ${score}` : ''}
    </span>
  )
}

const CHIP_TONES = {
  slate: 'bg-ink-700 text-slate-300 border-ink-600',
  sky: 'bg-sky-500/10 text-sky-300 border-sky-500/30',
  violet: 'bg-violet-500/10 text-violet-300 border-violet-500/30',
  rose: 'bg-rose-500/10 text-rose-300 border-rose-500/30',
  emerald: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
  amber: 'bg-amber-500/10 text-amber-300 border-amber-500/30',
  orange: 'bg-orange-500/10 text-orange-300 border-orange-500/30',
}

export const Chip = ({ children, tone = 'slate', className = '' }) => (
  <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-medium ${CHIP_TONES[tone] || CHIP_TONES.slate} ${className}`}>
    {children}
  </span>
)

export const Card = ({ title, right, children, className = '', headerClassName = '', bodyClassName = 'p-4 sm:p-5', id }) => (
  <section id={id} className={`card ${className}`}>
    {(title || right) && (
      <header className={`flex flex-wrap items-center justify-between gap-2 border-b border-ink-600/70 px-4 py-3 sm:px-5 ${headerClassName}`}>
        {typeof title === 'string' ? (
          <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
        ) : (
          title
        )}
        {right}
      </header>
    )}
    <div className={bodyClassName}>{children}</div>
  </section>
)

// Legacy alias kept for older call sites; new code should use StatCard.
export { default as Stat } from './components/StatCard.jsx'

export const Spinner = ({ message = 'Loading…' }) => <LoadingState message={message} />

export const ErrorBox = ({ error, onRetry }) => <ErrorState error={error} onRetry={onRetry} />

export const Empty = ({ children }) => (
  <div className="p-8 text-center text-sm text-slate-500">{children}</div>
)

export const when = (iso) => formatDate(iso)
export const pct = (x, dec = 1) => formatPct(x, dec)

export const CodeChip = ({ code, onClick, className = '' }) => {
  const Tag = onClick ? 'button' : 'span'
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={`inline-flex items-center rounded border border-ink-600 bg-ink-900 px-1.5 py-0.5 font-mono text-[11px] text-sky-300 transition-colors ${
        onClick ? 'cursor-pointer hover:border-sky-500 hover:bg-sky-500/10' : ''
      } ${className}`}
    >
      {code}
    </Tag>
  )
}

// Renders narrative text with [REASON_CODE] tags as interactive chips so each claim points at a ledger line.
// Text is rendered as React text nodes only, so model-written content can never inject markup.
export function Narrative({ text, onReasonCodeClick }) {
  const parts = (text || '').split(/(\[[A-Z][A-Z0-9_]+\])/g)
  return (
    <p className="text-sm leading-7 text-slate-300">
      {parts.map((p, i) => {
        if (/^\[[A-Z][A-Z0-9_]+\]$/.test(p)) {
          const code = p.slice(1, -1)
          return (
            <CodeChip
              key={i}
              code={code}
              className="mx-0.5 align-baseline"
              onClick={onReasonCodeClick ? () => onReasonCodeClick(code) : undefined}
            />
          )
        }
        return <span key={i}>{p}</span>
      })}
    </p>
  )
}

export function useLoad(fn, deps = []) {
  const [state, set] = React.useState({ data: null, error: null, loading: true })
  const run = React.useCallback(() => {
    set((s) => ({ ...s, loading: true }))
    return fn()
      .then((r) => set({ data: r.data, error: null, loading: false }))
      .catch((e) => set({ data: null, error: e?.response?.data?.detail?.message || e?.response?.data?.detail || e.message, loading: false }))
  }, deps) // eslint-disable-line
  React.useEffect(() => { run() }, [run])
  return { ...state, reload: run }
}
