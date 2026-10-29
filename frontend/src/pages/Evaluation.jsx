import React from 'react'
import { Check, X } from 'lucide-react'
import api from '../api.js'
import { Band, Card, ErrorBox, Spinner, pct, useLoad } from '../ui.jsx'

export default function Evaluation() {
  const { data: e, error, loading } = useLoad(() => api.get('/evaluation'))
  if (loading) return <Spinner />
  if (error) return <ErrorBox error={error} />
  const tm = e.text_model, rba = e.rba, bm = e.benchmark
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-white">Evaluation</h1>
        <p className="text-sm text-slate-400">What was measured, on what data, and what it does not show.</p>
      </div>
      <Card title="Scripted scenarios: expected band vs actual">
        <table className="w-full">
          <thead><tr><th className="th">Scenario</th><th className="th">Email</th><th className="th">Login</th><th className="th">Expected</th><th className="th">Actual</th><th className="th"></th></tr></thead>
          <tbody className="divide-y divide-ink-600/40">{e.scenarios.map((s) => (
            <tr key={s.key}><td className="td"><div className="text-slate-200">{s.title}</div><div className="max-w-xl text-xs text-slate-500">{s.blurb}</div></td>
              <td className="td text-slate-300">{s.email_score}</td><td className="td text-slate-300">{s.login_score}</td>
              <td className="td"><Band band={s.expected} /></td><td className="td"><Band band={s.actual} score={s.score} /></td>
              <td className="td">{s.ok ? <Check className="text-emerald-400" size={16} /> : <X className="text-rose-400" size={16} />}</td></tr>
          ))}</tbody>
        </table>
        <p className="mt-3 text-xs text-slate-500">The team wrote these scenarios. Passing them keeps the weights honest; it does not measure accuracy on real attacks.</p>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Text model">
          <div className="text-sm text-slate-300">{tm.source}</div>
          <div className="mt-2 grid grid-cols-4 gap-2 text-center text-xs">
            {['precision', 'recall', 'false_positive_rate', 'roc_auc'].map((k) => <div key={k} className="rounded bg-ink-900 p-2"><div className="text-lg font-semibold text-white">{tm.metrics?.[k]}</div><div className="text-slate-500">{k.replaceAll('_', ' ')}</div></div>)}
          </div>
          <p className="mt-3 text-xs text-amber-300">{tm.warning}</p>
        </Card>
        <Card title="Throughput (one process)">
          {!bm ? <p className="text-sm text-slate-500">Run scripts/benchmark.py.</p> : (
            <ul className="space-y-1.5 text-sm text-slate-300">
              {bm.login_scoring && <li><b className="text-white">{bm.login_scoring.rows_per_second.toLocaleString()}</b> logins/second on {bm.login_scoring.rows.toLocaleString()} real RBA rows</li>}
              <li><b className="text-white">{bm.email_analysis.emails_per_second}</b> emails/second including the text model</li>
              <li><b className="text-white">{bm.case_analysis.cases_per_second}</b> full cases/second (email + login + correlation)</li>
              <li className="text-xs text-slate-500">{bm.machine.cpus} CPUs, Python {bm.machine.python}. Scale out by sharding on user id.</li>
            </ul>
          )}
        </Card>
      </div>

      <Card title="Real login data: RBA data set">
        {!rba ? <p className="text-sm text-slate-500">Run scripts/evaluate_rba.py.</p> : (
          <>
            <p className="text-sm text-slate-300">{rba.input.rows_scored.toLocaleString()} rows from {rba.input.file} ({rba.input.from?.slice(0, 10)} to {rba.input.to?.slice(0, 10)}). {rba.input.sampling}.</p>
            <table className="mt-3 w-full">
              <thead><tr><th className="th">Configuration</th><th className="th">Account takeovers</th><th className="th">Caught at Medium</th><th className="th">AUC</th><th className="th">Failed-login rule AUC</th></tr></thead>
              <tbody className="divide-y divide-ink-600/40">
                {[['Behavioural signals only', rba.behavioural_only], ['Plus threat-feed (attack IP) signal', rba.with_threat_feed_signal]].map(([n, b]) => (
                  <tr key={n}><td className="td text-slate-200">{n}</td><td className="td text-slate-300">{b.all_rows.account_takeover_rows}</td><td className="td text-white">{pct(b.all_rows.account_takeover_at_medium.recall)}</td><td className="td text-slate-300">{b.all_rows.auc_account_takeover}</td><td className="td text-slate-400">{b.all_rows.auc_account_takeover_failed_login_rule}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 rounded-lg border border-amber-400/40 bg-amber-400/10 p-3 text-sm text-amber-200">
              {rba.behavioural_only.account_takeover_rows_with_no_or_thin_history} of {rba.behavioural_only.all_rows.account_takeover_rows} account takeovers hit accounts with no or very little earlier history, so a baseline-based method cannot see them. The RBA authors state the feature values are artificial. We do not claim detection rates from this data; it proves the loader, the scoring path and the throughput, and shows where the method is blind.
            </p>
          </>
        )}
      </Card>
      <ul className="list-disc space-y-1 pl-5 text-xs text-slate-500">{e.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
    </div>
  )
}
