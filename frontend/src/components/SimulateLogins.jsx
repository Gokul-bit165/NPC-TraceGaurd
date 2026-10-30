import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { FlaskConical, Loader2, X } from 'lucide-react'
import api, { errText } from '../api.js'
import RiskBadge from './RiskBadge.jsx'

const HINT = {
  normal: 'Only the user\'s usual sign-ins. Shows a healthy baseline: nothing should be flagged.',
  takeover: 'A failed-then-successful sign-in from Lagos shortly after the chosen real email (or the riskiest one). Shows email-then-login correlation.',
  travel: 'Coimbatore, then Frankfurt 43 minutes later. Shows impossible-travel detection.',
  stuffing: 'Twelve failures from one address, then a success from Amsterdam. Shows brute-force detection.',
}

// Opens a panel that generates simulated sign-ins for a real mailbox. No identity provider is connected, so these are the only login logs.
export default function SimulateLogins({ mailbox, emailId, onDone, label = 'Simulate logins', className = 'btn btn-ghost text-xs' }) {
  const [open, setOpen] = useState(false)
  const [opts, setOpts] = useState(null)
  const [box, setBox] = useState(mailbox || '')
  const [scenario, setScenario] = useState('takeover')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  useEffect(() => {
    if (!open || opts) return
    api.get('/simulate/options').then((r) => {
      setOpts(r.data)
      setBox((b) => b || r.data.mailboxes[0]?.email || '')
    }).catch((e) => setError(errText(e)))
  }, [open, opts])

  const run = async () => {
    setBusy(true); setError(''); setResult(null)
    try {
      const r = await api.post('/simulate/logins', { mailbox: box, scenario, email_id: emailId || '' })
      setResult(r.data)
      onDone?.(r.data)
    } catch (e) {
      setError(errText(e))
    } finally {
      setBusy(false)
    }
  }

  const clear = async () => {
    if (!window.confirm(`Remove all simulated sign-ins for ${box}? Their cases are re-scored.`)) return
    setBusy(true); setError(''); setResult(null)
    try {
      const r = await api.delete('/simulate/logins', { params: { mailbox: box } })
      setResult({ events: 0, cases: [], cleared: r.data.removed })
      onDone?.(r.data)
    } catch (e) {
      setError(errText(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button type="button" className={className} onClick={() => { setOpen(true); setResult(null) }}>
        <FlaskConical size={14} /> {label}
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-label="Simulate login activity">
          <div className="card w-full max-w-lg space-y-4 p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-100">Simulate login activity</h2>
                <p className="text-sm text-slate-400">No identity provider is connected, so there are no real sign-in logs. This generates believable ones for a real mailbox and scores them like real events.</p>
              </div>
              <button type="button" onClick={() => setOpen(false)} className="rounded-md p-1 text-slate-400 hover:text-slate-100" aria-label="Close"><X size={18} /></button>
            </div>

            <label className="block space-y-1 text-sm">
              <span className="text-slate-300">Mailbox</span>
              <select className="input" value={box} onChange={(e) => setBox(e.target.value)} disabled={!!mailbox}>
                {mailbox && <option value={mailbox}>{mailbox}</option>}
                {(opts?.mailboxes || []).filter((m) => m.email !== mailbox).map((m) => <option key={m.id} value={m.email}>{m.email}</option>)}
              </select>
            </label>

            <fieldset className="space-y-2">
              <legend className="mb-1 text-sm text-slate-300">Scenario</legend>
              {(opts?.scenarios || []).map((s) => (
                <label key={s.id} className={`block cursor-pointer rounded-lg border p-3 text-sm ${scenario === s.id ? 'border-sky-500/60 bg-sky-500/10' : 'border-ink-600 hover:bg-ink-700/40'}`}>
                  <input type="radio" name="scenario" className="mr-2" checked={scenario === s.id} onChange={() => setScenario(s.id)} />
                  <b className="font-medium text-slate-100">{s.label.split(':')[0]}</b>
                  <p className="ml-5 mt-0.5 text-xs text-slate-400">{HINT[s.id]}</p>
                </label>
              ))}
            </fieldset>

            {error && <p className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-2.5 text-sm text-rose-300">{error}</p>}

            {result && (
              <div className="space-y-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-slate-200">
                {result.cleared !== undefined && <p>Removed {result.cleared} simulated sign-ins.</p>}
                {result.cleared === undefined && <p>Added {result.events} sign-ins{result.baseline_added ? ' (including a 4-week baseline)' : ''}.</p>}
                {result.cleared === undefined && result.cases.length === 0 && <p className="text-slate-400">No case was opened: the activity looks normal.</p>}
                {result.cases.map((c) => (
                  <div key={c.case_id} className="flex items-center justify-between gap-3">
                    <RiskBadge band={c.band} score={c.score} size="sm" />
                    <Link to={`/investigate/${c.case_id}`} className="font-medium text-sky-300 hover:underline" onClick={() => setOpen(false)}>Open case #{c.case_id} and decision →</Link>
                  </div>
                ))}
              </div>
            )}

            <div className="flex items-center justify-between gap-2">
              <button type="button" className="text-xs text-slate-400 underline hover:text-rose-300" onClick={clear} disabled={busy || !box}>Clear simulated logins</button>
              <div className="flex gap-2">
              <button type="button" className="btn btn-ghost text-sm" onClick={() => setOpen(false)}>Close</button>
              <button type="button" className="btn btn-primary text-sm" onClick={run} disabled={busy || !box}>
                {busy ? <><Loader2 size={14} className="animate-spin" /> Working…</> : 'Generate'}
              </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
