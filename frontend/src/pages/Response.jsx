import React from 'react'
import { Link, useParams } from 'react-router-dom'
import { Check, Lock, RotateCcw, ShieldAlert, X } from 'lucide-react'
import api, { errText, getRole } from '../api.js'
import { Band, Card, Chip, Empty, ErrorBox, Spinner, useLoad, when } from '../ui.jsx'
import { CaseList } from './Investigation.jsx'
import CampaignModal from '../components/CampaignModal.jsx'

export default function Response() {
  const { id } = useParams()
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-white">Incident Response</h1>
        <p className="text-sm text-slate-400">Reversible steps run on their own. Anything that blocks a domain or locks a user out waits for an analyst, in the right order.</p>
      </div>
      <div className="grid gap-5 lg:grid-cols-4">
        <div className="lg:col-span-1"><CaseList base="response" /></div>
        <div className="space-y-5 lg:col-span-3">{id ? <Workflow id={id} /> : <Card><Empty>Pick a case to manage its response.</Empty></Card>}</div>
      </div>
    </div>
  )
}

const STATUS = { proposed: ['Waiting', 'amber'], approved: ['Approved', 'emerald'], rejected: ['Rejected', 'rose'], auto_done: ['Ran automatically', 'sky'] }

function Workflow({ id }) {
  const { data: d, error, loading, reload } = useLoad(() => api.get(`/cases/${id}`), [id])
  const [msg, setMsg] = React.useState('')
  const [busy, setBusy] = React.useState(false)
  const [campaignModalKey, setCampaignModalKey] = React.useState(null)

  if (loading && !d) return <Spinner />
  if (error) return <ErrorBox error={error} />
  const byCode = Object.fromEntries(d.actions.map((a) => [a.code, a]))
  const act = async (fn) => { setBusy(true); setMsg(''); try { await fn(); await reload() } catch (e) { setMsg(errText(e)) } finally { setBusy(false) } }
  const decide = (a, decision) => act(() => api.post(`/cases/${id}/actions/${a.id}`, { decision }))
  const undoAction = (a) => act(() => api.post(`/cases/${id}/actions/${a.id}/undo`, { note: 'Undone by analyst in response console' }))
  const status = (s) => act(() => api.post(`/cases/${id}/status`, { status: s }))
  const verdict = (v) => act(() => api.post(`/cases/${id}/verdict`, { verdict: v }))
  const c = d.case

  return (
    <>
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-xs text-slate-500">Incident #{c.id}</div>
            <h2 className="text-lg font-semibold text-white">{d.user.name}: {d.narrative.headline}</h2>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-400">
              <Chip tone={c.status === 'resolved' ? 'emerald' : c.status === 'investigating' ? 'sky' : 'amber'}>{c.status.replace('_', ' ')}</Chip>
              {c.assignee && <span>assigned to {c.assignee}</span>}
              {c.campaign_key && c.campaign_size > 1 ? (
                <button
                  type="button"
                  onClick={() => setCampaignModalKey(c.campaign_key)}
                  className="btn btn-ghost !py-0.5 !px-2 text-xs text-rose-300 border-rose-500/40 hover:bg-rose-500/20"
                >
                  <ShieldAlert size={12} />
                  Act on Campaign ({c.campaign_size} recipients)
                </button>
              ) : (
                c.campaign_size > 1 && <Chip tone="rose">same message reached {c.campaign_size} people</Chip>
              )}
              {c.verdict && <Chip tone={c.verdict === 'true_positive' ? 'rose' : 'emerald'}>{c.verdict.replace('_', ' ')}</Chip>}
            </div>
          </div>
          <div className="flex items-center gap-2"><Band band={c.band} score={c.score} /><Link className="btn btn-ghost" to={`/investigate/${c.id}`}>See evidence</Link></div>
        </div>
      </Card>

      <ErrorBox error={msg} />

      <Card title="Recommended actions" right={<span className="text-xs text-slate-500">{getRole() === 'user' ? '' : 'Approvals are logged with your name'}</span>}>
        <ol className="space-y-2">
          {d.actions.map((a) => {
            const [label, tone] = STATUS[a.status]
            const dep = a.depends_on && byCode[a.depends_on]
            const blocked = a.status === 'proposed' && dep && !['approved', 'auto_done'].includes(dep.status)
            return (
              <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-ink-600/60 bg-ink-900 p-3">
                <div className="flex min-w-0 items-start gap-3">
                  <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-ink-700 text-xs text-slate-300">{a.order}</span>
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-slate-200">{a.label}</div>
                    <div className="text-xs text-slate-500">{a.detail}</div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      <Chip tone={tone}>{label}</Chip>
                      <Chip>{a.reversible ? 'reversible' : 'not reversible'}</Chip>
                      <Chip>{a.connector}</Chip>
                      {a.decided_by && <Chip>{a.decided_by}, {when(a.decided_at)}</Chip>}
                    </div>
                    {blocked && <div className="mt-1 flex items-center gap-1 text-xs text-amber-300"><Lock size={12} /> Waits for “{dep.label}”: a live token survives a password reset.</div>}
                  </div>
                </div>
                {a.status === 'proposed' && (
                  <div className="flex gap-2">
                    <button className="btn btn-ok" disabled={busy || blocked} onClick={() => decide(a, 'approve')}><Check size={14} /> Approve</button>
                    <button className="btn btn-ghost" disabled={busy} onClick={() => decide(a, 'reject')}><X size={14} /> Reject</button>
                  </div>
                )}
                {a.status === 'approved' && a.reversible && (
                  <div className="flex gap-2">
                    <button
                      className="btn btn-ghost text-xs text-amber-300 hover:text-amber-200"
                      disabled={busy}
                      onClick={() => undoAction(a)}
                    >
                      <RotateCcw size={13} /> Undo action
                    </button>
                  </div>
                )}
              </li>
            )
          })}
        </ol>
      </Card>

      <div className="grid gap-5 xl:grid-cols-2">
        <Card title="Case status and feedback">
          <div className="flex flex-wrap gap-2">
            <button className="btn btn-ghost" disabled={busy} onClick={() => status('investigating')}>Mark investigating</button>
            <button className="btn btn-ghost" disabled={busy} onClick={() => status('resolved')}>Mark resolved</button>
            <button className="btn btn-ghost" disabled={busy} onClick={() => status('open')}><RotateCcw size={14} /> Reopen</button>
          </div>
          <div className="mt-4 text-sm text-slate-400">Was this a real threat? Your answer feeds the false-positive report on the Reports page.</div>
          <div className="mt-2 flex gap-2">
            <button className="btn btn-bad" disabled={busy} onClick={() => verdict('true_positive')}>Real threat</button>
            <button className="btn btn-ok" disabled={busy} onClick={() => verdict('false_positive')}>False alarm</button>
          </div>
        </Card>
        <Card title="Message to the user (drafted from the evidence)">
          <pre className="whitespace-pre-wrap rounded-lg bg-ink-900 p-3 text-xs leading-relaxed text-slate-300">{d.user_alert}</pre>
        </Card>
      </div>

      <Card title="Audit trail">
        {d.audit.length === 0 ? <Empty>No entries.</Empty> : (
          <table className="w-full">
            <tbody className="divide-y divide-ink-600/40">
              {d.audit.map((a, i) => (
                <tr key={i}><td className="td text-xs text-slate-500">{when(a.ts)}</td><td className="td text-xs text-slate-300">{a.actor} <span className="text-slate-500">({a.role})</span></td><td className="td text-xs text-slate-200">{a.event.replaceAll('_', ' ')}</td><td className="td break-all text-xs text-slate-500">{a.detail}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {campaignModalKey && (
        <CampaignModal
          campaignKey={campaignModalKey}
          onClose={() => setCampaignModalKey(null)}
          onSuccess={reload}
        />
      )}
    </>
  )
}

