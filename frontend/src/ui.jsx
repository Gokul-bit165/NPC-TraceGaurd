import React from 'react'
import { Loader2 } from 'lucide-react'

export const BAND = {
  critical: { label: 'Critical', cls: 'bg-rose-600/20 text-rose-300 border-rose-500/50', dot: '#f43f5e' },
  high: { label: 'High', cls: 'bg-orange-500/20 text-orange-300 border-orange-500/50', dot: '#f97316' },
  medium: { label: 'Medium', cls: 'bg-amber-400/15 text-amber-300 border-amber-400/40', dot: '#fbbf24' },
  low: { label: 'Low', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40', dot: '#34d399' },
}

export function Band({ band, score }) {
  const b = BAND[band] || BAND.low
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${b.cls}`}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: b.dot }} />
      {b.label}{score !== undefined && score !== null ? ` ${score}` : ''}
    </span>
  )
}

export const Chip = ({ children, tone = 'slate' }) => {
  const t = { slate: 'bg-ink-700 text-slate-300', sky: 'bg-sky-500/15 text-sky-300', violet: 'bg-violet-500/15 text-violet-300', rose: 'bg-rose-500/15 text-rose-300', emerald: 'bg-emerald-500/15 text-emerald-300', amber: 'bg-amber-400/15 text-amber-300' }[tone]
  return <span className={`inline-block rounded px-1.5 py-0.5 text-[11px] font-medium ${t}`}>{children}</span>
}

export const Card = ({ title, right, children, className = '' }) => (
  <section className={`card ${className}`}>
    {(title || right) && (
      <header className="flex items-center justify-between border-b border-ink-600/60 px-4 py-2.5">
        <h3 className="text-sm font-semibold text-slate-200">{title}</h3>
        {right}
      </header>
    )}
    <div className="p-4">{children}</div>
  </section>
)

export const Stat = ({ icon: Icon, label, value, sub, tone = 'sky' }) => {
  const c = { sky: 'text-sky-400', rose: 'text-rose-400', amber: 'text-amber-300', emerald: 'text-emerald-400', violet: 'text-violet-400' }[tone]
  return (
    <div className="card flex items-start gap-3 p-4">
      <div className={`rounded-lg bg-ink-700 p-2 ${c}`}><Icon size={20} /></div>
      <div>
        <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
        <div className="text-2xl font-semibold text-white">{typeof value === 'number' ? value.toLocaleString() : value}</div>
        {sub && <div className="text-xs text-slate-500">{sub}</div>}
      </div>
    </div>
  )
}

export const Spinner = () => <div className="flex items-center gap-2 p-6 text-slate-400"><Loader2 className="animate-spin" size={18} /> Loading…</div>
export const ErrorBox = ({ error }) => error ? <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-300">{String(error)}</div> : null
export const Empty = ({ children }) => <div className="p-6 text-center text-sm text-slate-500">{children}</div>

export const when = (iso) => iso ? new Date(iso).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''
export const pct = (x) => (x === null || x === undefined) ? 'n/a' : `${(x * 100).toFixed(1)}%`

export const CodeChip = ({ code }) => <span className="rounded bg-ink-700 px-1.5 py-0.5 font-mono text-[10px] text-sky-300">{code}</span>

// Renders narrative text with [REASON_CODE] tags as chips so each claim points at a ledger line.
export function Narrative({ text }) {
  const parts = (text || '').split(/(\[[A-Z][A-Z0-9_]+\])/g)
  return <p className="text-sm leading-relaxed text-slate-300">{parts.map((p, i) => /^\[[A-Z]/.test(p) ? <CodeChip key={i} code={p.slice(1, -1)} /> : <span key={i}>{p}</span>)}</p>
}

export function useLoad(fn, deps = []) {
  const [state, set] = React.useState({ data: null, error: null, loading: true })
  const run = React.useCallback(() => {
    set((s) => ({ ...s, loading: true }))
    return fn().then((r) => set({ data: r.data, error: null, loading: false })).catch((e) => set({ data: null, error: e?.response?.data?.detail || e.message, loading: false }))
  }, deps) // eslint-disable-line
  React.useEffect(() => { run() }, [run])
  return { ...state, reload: run }
}
