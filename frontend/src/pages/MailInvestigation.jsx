import React from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, CheckCircle2, FileSearch, Link2, MailWarning, ShieldAlert, ShieldCheck, XCircle } from 'lucide-react'
import api from '../api.js'
import SimulateLogins from '../components/SimulateLogins.jsx'
import { Card, ErrorBox, PageHeader, RiskBadge, Spinner, when } from '../ui.jsx'
import { useApi } from '../hooks/useApi.js'

const AUTH_TONE = {
  pass: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  fail: 'border-rose-500/30 bg-rose-500/10 text-rose-300',
}

function AuthChip({ name, value }) {
  const v = String(value || 'not present').toLowerCase()
  const tone = AUTH_TONE[v] || (v === 'not present' ? 'border-ink-600 bg-ink-700 text-slate-400' : 'border-amber-500/30 bg-amber-500/10 text-amber-300')
  return (
    <span className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-semibold ${tone}`}>
      {name.toUpperCase()} <span className="font-normal opacity-90">{v}</span>
    </span>
  )
}

export default function MailInvestigation() {
  const { id } = useParams()
  const { data, error, loading, reload } = useApi(() => api.get(`/emails/${id}/investigation`), [id])

  if (loading && !data) return <Spinner message="Investigating this email…" />
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />

  const { email, verdict, analysis, context, case: kase, recommendations } = data
  const evidence = analysis.ledger.filter((e) => e.points > 0 || e.raw_points > 0)
  const prob = analysis.probability

  return (
    <div className="space-y-6 pb-12">
      <Link to="/mailbox" className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-sky-300"><ArrowLeft size={14} /> Back to Mailbox</Link>
      <PageHeader
        icon={FileSearch}
        title={email.subject || '(no subject)'}
        description={`From ${email.sender || 'unknown'} to ${email.mailbox.email || email.mailbox.id} · ${when(email.received_at)}`}
        right={<><SimulateLogins mailbox={email.mailbox.email} emailId={email.id} label="Simulate a follow-up login" onDone={reload} /><RiskBadge band={verdict.band} score={verdict.score} size="lg" /></>}
      />

      <Card>
        <div className="flex items-start gap-3">
          {verdict.band === 'low' ? <ShieldCheck className="mt-0.5 text-emerald-400" size={22} /> : <ShieldAlert className="mt-0.5 text-rose-400" size={22} />}
          <div className="space-y-1">
            <h2 className="text-lg font-semibold text-slate-100">{verdict.headline}</h2>
            {verdict.reasons.length > 0 && <ul className="list-disc space-y-0.5 pl-5 text-sm text-slate-300">{verdict.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>}
            {kase && (
              <p className="pt-1 text-sm text-slate-400">
                Part of case <Link className="text-sky-300 hover:underline" to={`/investigate/${kase.id}`}>#{kase.id}</Link> ({kase.status}) · <Link className="text-sky-300 hover:underline" to={`/response/${kase.id}`}>respond</Link>{kase.correlated ? ' · correlated with login activity' : ''}.
              </p>
            )}
          </div>
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Why it scored this way">
          {evidence.length === 0 ? <p className="text-sm text-slate-400">No scoring signals fired.</p> : (
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-400"><tr><th className="pb-2">Signal</th><th className="pb-2 text-right">Points</th></tr></thead>
              <tbody className="divide-y divide-ink-600/40">
                {evidence.map((e, i) => (
                  <tr key={i}>
                    <td className="py-2 pr-3"><div className="font-medium text-slate-100">{e.label}</div><div className="text-xs text-slate-400">{e.detail}</div></td>
                    <td className="py-2 text-right tabular-nums text-slate-200">+{e.points}{e.raw_points !== e.points && <span className="text-xs text-slate-500"> (capped from {e.raw_points})</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="mt-3 text-xs text-slate-500">Every point comes from a visible signal. Nothing is hidden inside the model.</p>
        </Card>

        <div className="space-y-6">
          <Card title="Sender authentication">
            {email.has_headers ? (
              <div className="flex flex-wrap gap-2">{['spf', 'dkim', 'dmarc'].map((k) => <AuthChip key={k} name={k} value={analysis.auth[k]} />)}</div>
            ) : <p className="text-sm text-amber-300">No authentication headers were available, so SPF, DKIM and DMARC could not be checked.</p>}
            {email.reply_to && email.reply_to !== email.sender && <p className="mt-3 text-sm text-slate-300">Replies go to <span className="font-mono">{email.reply_to}</span>, which differs from the sender.</p>}
          </Card>

          <Card title="Wording check (text model)">
            {prob == null ? <p className="text-sm text-slate-400">Not evaluated.</p> : (
              <>
                <div className="flex items-baseline gap-2"><span className="text-3xl font-semibold tabular-nums text-slate-100">{Math.round(prob * 100)}%</span><span className="text-sm text-slate-400">phishing-like wording</span></div>
                {analysis.terms.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {analysis.terms.slice(0, 8).map((t, i) => <span key={i} className="rounded-md border border-ink-600 bg-ink-700 px-2 py-0.5 text-xs text-slate-200">{t.term ?? t.word ?? String(t)}</span>)}
                  </div>
                )}
              </>
            )}
          </Card>
        </div>
      </div>

      <Card title={`Links in this email (${email.links.length})`}>
        {email.links.length === 0 ? <p className="text-sm text-slate-400">No links.</p> : (
          <ul className="divide-y divide-ink-600/40 text-sm">
            {email.links.map((l, i) => (
              <li key={i} className="flex items-start gap-3 py-2">
                {l.flag ? <XCircle size={16} className="mt-0.5 shrink-0 text-rose-400" /> : <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-400" />}
                <div className="min-w-0">
                  <div className="break-all font-mono text-xs text-slate-200" title={l.href}>{l.href.length > 120 ? `${l.href.slice(0, 120)}…` : l.href}</div>
                  {l.text && l.text !== l.href && <div className="text-xs text-slate-400">shown as “{l.text}”</div>}
                  {l.flag && <div className="text-xs text-rose-300">{l.flag}</div>}
                </div>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-xs text-slate-500">Links are shown as text and are never opened by TraceGuard.</p>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Context">
          <ul className="space-y-1.5 text-sm text-slate-300">
            <li><MailWarning size={14} className="mr-2 inline text-slate-500" />{context.campaign.emails > 1 ? `${context.campaign.emails} similar emails reached ${context.campaign.mailboxes} mailbox(es) — possible campaign.` : 'No similar emails seen elsewhere.'}</li>
            <li><Link2 size={14} className="mr-2 inline text-slate-500" />{context.sender.other_emails > 0 ? `${context.sender.other_emails} other email(s) from this sender; highest score ${context.sender.highest_score}.` : 'First email from this sender.'}</li>
            {email.hidden_text_found && <li className="text-amber-300">Hidden text was found in the message body.</li>}
          </ul>
        </Card>
        <Card title="Recommended steps">
          <ol className="list-decimal space-y-1.5 pl-5 text-sm text-slate-300">{recommendations.map((r, i) => <li key={i}>{r}</li>)}</ol>
          <p className="mt-3 text-xs text-slate-500">TraceGuard never deletes or blocks mail by itself. These steps are for an analyst to approve.</p>
        </Card>
      </div>

      <Card title="Message preview (plain text)">
        <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words text-sm text-slate-300">{email.preview || '(empty body)'}</pre>
      </Card>
    </div>
  )
}
