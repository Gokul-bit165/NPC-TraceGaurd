import React from 'react'
import { AlertTriangle, CheckCircle2, HelpCircle, Lock, ShieldAlert, ShieldCheck, Sparkles } from 'lucide-react'
import api from '../api.js'
import { useApi } from '../hooks/useApi.js'
import { Card, Chip } from '../ui.jsx'

const TONE = {
  rose: { box: 'border-rose-500/40 bg-rose-500/10', text: 'text-rose-300', bar: 'bg-rose-500', Icon: ShieldAlert },
  orange: { box: 'border-orange-500/40 bg-orange-500/10', text: 'text-orange-300', bar: 'bg-orange-500', Icon: AlertTriangle },
  amber: { box: 'border-amber-500/40 bg-amber-500/10', text: 'text-amber-300', bar: 'bg-amber-500', Icon: HelpCircle },
  emerald: { box: 'border-emerald-500/40 bg-emerald-500/10', text: 'text-emerald-300', bar: 'bg-emerald-500', Icon: ShieldCheck },
}

const STATUS_TONE = { proposed: 'amber', approved: 'sky', auto_done: 'emerald', done: 'emerald', rejected: 'slate', failed: 'rose' }

// Decision support for one case: the call, how sure we are, why, the options, and what would change the answer.
export default function DecisionPanel({ caseId }) {
  const { data, loading, error } = useApi(() => api.get(`/cases/${caseId}/decision`), [caseId])
  if (loading && !data) return <Card title="Recommended decision"><p className="text-sm text-slate-400">Working out a recommendation…</p></Card>
  if (error || !data) return null

  const { decision, reasons, options, steps, would_change: wc, ai } = data
  const t = TONE[decision.tone] || TONE.amber
  return (
    <Card
      title="Recommended decision"
      right={<Chip tone={ai.source === 'llm' ? 'violet' : 'slate'}><Sparkles size={11} className="mr-1 inline" />{ai.source === 'llm' ? 'AI-assisted' : 'Rule-based'} · you decide</Chip>}
    >
      <div className="space-y-5">
        <div className={`flex flex-wrap items-center justify-between gap-4 rounded-xl border p-4 ${t.box}`}>
          <div className="flex min-w-0 items-start gap-3">
            <t.Icon size={26} className={`mt-0.5 shrink-0 ${t.text}`} />
            <div className="min-w-0">
              <div className={`text-lg font-semibold ${t.text}`}>{decision.label}</div>
              <p className="text-sm text-slate-300">{decision.summary}</p>
            </div>
          </div>
          <div className="w-40 shrink-0">
            <div className="flex justify-between text-xs text-slate-400"><span>Confidence</span><span className="tabular-nums text-slate-200">{decision.confidence}%</span></div>
            <div className="mt-1 h-2 overflow-hidden rounded-full bg-ink-700" role="meter" aria-valuenow={decision.confidence} aria-valuemin={0} aria-valuemax={100} aria-label="Decision confidence">
              <div className={`h-full ${t.bar}`} style={{ width: `${decision.confidence}%` }} />
            </div>
          </div>
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          <section>
            <div className="section-title mb-2">Why (strongest evidence)</div>
            {reasons.length === 0 ? <p className="text-sm text-slate-400">No suspicious evidence was found.</p> : (
              <ul className="space-y-2">
                {reasons.map((r) => (
                  <li key={r.code} className="rounded-lg border border-ink-600 bg-ink-900 p-2.5 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-slate-200">{r.label}</span>
                      <span className="shrink-0 rounded bg-ink-700 px-1.5 py-0.5 text-xs tabular-nums text-slate-300">+{r.points}</span>
                    </div>
                    <p className="mt-0.5 break-words text-xs text-slate-400">{r.detail}</p>
                    <span className="mt-1 inline-block text-[10px] uppercase tracking-wide text-slate-500">{r.side}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <div className="section-title mb-2">Your options</div>
            <ul className="space-y-2">
              {options.map((o) => (
                <li key={o.id} className={`rounded-lg border p-2.5 text-sm ${o.recommended ? 'border-sky-500/50 bg-sky-500/10' : 'border-ink-600 bg-ink-900'}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-slate-100">{o.label}</span>
                    {o.recommended && <Chip tone="sky">Recommended</Chip>}
                  </div>
                  <p className="mt-0.5 text-xs text-slate-300">{o.effect}</p>
                  <p className="text-xs text-slate-500">Risk: {o.risk}</p>
                </li>
              ))}
            </ul>
          </section>
        </div>

        {steps.length > 0 && (
          <section>
            <div className="section-title mb-2">Suggested steps, in order</div>
            <ol className="space-y-2">
              {steps.map((s) => (
                <li key={s.code} className="flex gap-3 rounded-lg border border-ink-600 bg-ink-900 p-2.5 text-sm">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-ink-700 text-xs font-semibold text-slate-200">{s.order}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-slate-100">{s.label}</span>
                      <Chip tone={STATUS_TONE[s.status] || 'slate'}>{s.status.replace('_', ' ')}</Chip>
                      {s.requires_approval && <span className="inline-flex items-center gap-1 text-xs text-slate-400"><Lock size={11} /> needs approval</span>}
                      {!s.reversible && <span className="text-xs text-rose-300">not reversible</span>}
                    </div>
                    <p className="mt-0.5 text-xs text-slate-400">{s.why}</p>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        )}

        {wc.length > 0 && (
          <section>
            <div className="section-title mb-2">What would change this</div>
            <ul className="space-y-1.5 text-sm text-slate-300">
              {wc.map((w) => <li key={w} className="flex gap-2"><CheckCircle2 size={14} className="mt-0.5 shrink-0 text-slate-500" />{w}</li>)}
            </ul>
          </section>
        )}
      </div>
    </Card>
  )
}
