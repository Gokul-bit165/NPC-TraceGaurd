import React from 'react'
import { AlertTriangle, Cpu, Database, FlaskConical, Gauge, Info, ListChecks, Server } from 'lucide-react'
import api from '../api.js'
import {
  Card,
  Chip,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  RiskBadge,
  StatCard,
  pct,
  when,
} from '../ui.jsx'
import { useApi } from '../hooks/useApi.js'

const asArray = (v) => (Array.isArray(v) ? v : [])
const has = (v) => v !== undefined && v !== null && v !== ''
const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v.toLocaleString() : null)

// Derived from the scenario's own scores; the API has no explicit "type" field.
function scenarioType(s) {
  const e = Number(s.email_score) > 0
  const l = Number(s.login_score) > 0
  if (s.correlated || (e && l)) return 'Email + login'
  if (e) return 'Email only'
  if (l) return 'Login only'
  return 'Benign baseline'
}

export default function Evaluation() {
  const { data, error, loading, reload } = useApi(() => api.get('/evaluation'))

  const header = (
    <PageHeader
      icon={FlaskConical}
      title="Model Evaluation"
      description="Evaluate security detection performance using available scenarios, datasets, and execution results."
    />
  )

  if (loading && !data) {
    return <div className="space-y-6">{header}<LoadingState variant="page" message="Loading evaluation results…" /></div>
  }
  if (error && !data) {
    return <div className="space-y-6">{header}<ErrorState error={error} title="Unable to load evaluation results." onRetry={reload} /></div>
  }

  const e = data && typeof data === 'object' ? data : {}
  const scenarios = asArray(e.scenarios)
  const tm = e.text_model && typeof e.text_model === 'object' ? e.text_model : null
  const rba = e.rba && typeof e.rba === 'object' ? e.rba : null
  const bm = e.benchmark && typeof e.benchmark === 'object' ? e.benchmark : null
  const notes = asArray(e.notes)
  const nothing = scenarios.length === 0 && !tm && !rba && !bm

  const syntheticModel = tm && /synthetic|template/i.test(String(tm.source || ''))

  return (
    <div className="space-y-6">
      {header}

      {/* Transparency: always shown, including when there is no data. */}
      <div className="flex gap-3 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4" role="note">
        <Info size={18} className="mt-0.5 shrink-0 text-amber-400" />
        <div className="space-y-1 text-sm">
          <p className="font-semibold text-amber-300">Team-written scenarios, not accuracy.</p>
          <p className="leading-relaxed text-slate-300">
            The scenarios check that scoring and band boundaries behave as designed. They are a regression suite written by the team and say
            nothing about detection rates on real attacks.
          </p>
        </div>
      </div>

      {nothing ? (
        <Card><EmptyState icon={FlaskConical} title="No evaluation results available." message="The API returned no scenarios, model details, real-data results or benchmarks." action={reload} actionLabel="Reload" /></Card>
      ) : (
        <>
          {/* Summary: only metrics that exist */}
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            {scenarios.length > 0 && <StatCard icon={ListChecks} tone="sky" label="Scenarios" value={scenarios.length} sub="Team-written test cases" />}
            {has(bm?.when) && <StatCard icon={Gauge} tone="emerald" label="Benchmark run" value={when(bm.when)} sub="Speed measurement date" />}
            {num(bm?.case_analysis?.cases_per_second) && <StatCard icon={Gauge} tone="violet" label="Case analysis speed" value={`${num(bm.case_analysis.cases_per_second)}/s`} sub="Email + login + correlation" />}
            {num(rba?.input?.rows_scored) && <StatCard icon={Database} tone="amber" label="Real-data rows scored" value={rba.input.rows_scored} sub={rba.input.file} />}
          </div>

          {/* Scenarios */}
          <Card title="Scenarios" bodyClassName="p-0" right={<Chip tone="amber">Team-written · synthetic</Chip>}>
            {scenarios.length === 0 ? (
              <EmptyState icon={ListChecks} title="No scenarios returned" message="The API did not return any scripted scenarios." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[48rem] text-left">
                  <thead className="border-b border-ink-600/70 bg-ink-900">
                    <tr>
                      <th className="th">ID</th><th className="th">Scenario</th><th className="th">Type</th>
                      <th className="th text-center">Email / Login</th><th className="th">Expected</th><th className="th">Actual</th><th className="th text-right">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-ink-600/50">
                    {scenarios.map((s, i) => (
                      <tr key={s.key ?? i} className="hover:bg-ink-700/40">
                        <td className="td align-top font-mono text-xs text-slate-400">{s.key ?? `#${i + 1}`}</td>
                        <td className="td max-w-md align-top">
                          <div className="font-medium text-slate-100">{s.title}</div>
                          {s.blurb && <div className="mt-0.5 text-xs leading-relaxed text-slate-400">{s.blurb}</div>}
                        </td>
                        <td className="td whitespace-nowrap align-top text-xs text-slate-300">{scenarioType(s)}</td>
                        <td className="td whitespace-nowrap text-center align-top font-mono text-xs tabular-nums text-slate-300">{s.email_score ?? '—'} / {s.login_score ?? '—'}</td>
                        <td className="td align-top">{has(s.expected) ? <RiskBadge band={s.expected} size="xs" /> : '—'}</td>
                        <td className="td align-top">{has(s.actual) ? <RiskBadge band={s.actual} score={s.score} size="xs" /> : '—'}</td>
                        <td className="td text-right align-top">
                          {s.ok ? <Chip tone="emerald">Match</Chip> : <Chip tone="rose">Mismatch</Chip>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {scenarios.length > 0 && <p className="border-t border-ink-600/70 px-5 py-3 text-xs text-slate-500">Scenarios are re-scored live against the current weights with a fixed clock, so results are reproducible. “Type” is derived from each scenario’s email and login scores.</p>}
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            {/* Model card */}
            <Card title="Model card" right={<Cpu size={16} className="text-slate-500" />}>
              {!tm ? (
                <EmptyState icon={Cpu} title="No model details available" message="The API did not return text-model metadata." className="!py-6" />
              ) : (
                <div className="space-y-4">
                  {syntheticModel && (
                    <div className="flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm font-medium text-amber-300">
                      <AlertTriangle size={15} className="shrink-0" /> Model trained on synthetic data.
                    </div>
                  )}
                  <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
                    <Fact label="Model" value="Phishing wording classifier" />
                    <Fact label="Model type" value="TF-IDF text features + logistic regression" />
                    {has(tm.source) && <Fact label="Training data source" value={tm.source} wide />}
                    {has(tm.n_train) && <Fact label="Training examples" value={num(tm.n_train)} />}
                    {has(tm.holdout) && <Fact label="Evaluation data" value={`Hold-out: ${tm.holdout}`} />}
                    {has(tm.trained_at) && <Fact label="Trained" value={String(tm.trained_at)} />}
                    {has(bm?.when) && <Fact label="Evaluation date" value={when(bm.when)} />}
                  </dl>
                  <p className="text-xs text-slate-500">The API publishes no model name or version, so none is shown.</p>

                  {tm.metrics && typeof tm.metrics === 'object' && (
                    <div>
                      <div className="section-title mb-2">Hold-out results on synthetic text (not real-world accuracy)</div>
                      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                        {['precision', 'recall', 'false_positive_rate', 'roc_auc'].filter((k) => has(tm.metrics[k])).map((k) => (
                          <div key={k} className="rounded-lg border border-ink-600 bg-ink-900 p-2.5 text-center">
                            <div className="text-lg font-semibold tabular-nums text-slate-100">{tm.metrics[k]}</div>
                            <div className="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">{k.replaceAll('_', ' ')}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {has(tm.warning) && <p className="rounded-lg border border-ink-600 bg-ink-900 p-3 text-xs italic leading-relaxed text-slate-400">{tm.warning}</p>}
                </div>
              )}
            </Card>

            {/* Speed */}
            <Card title="Execution speed" right={<Server size={16} className="text-slate-500" />}>
              {!bm ? (
                <EmptyState icon={Gauge} title="No speed results yet" message="Run scripts/benchmark.py on the deployment host to produce them." className="!py-6" />
              ) : (
                <div className="space-y-3 text-sm">
                  <SpeedRow label="Login risk scoring" value={num(bm.login_scoring?.rows_per_second)} unit="rows/s" note={bm.login_scoring && `${num(bm.login_scoring.rows)} ${bm.login_scoring.source || 'rows'}`} />
                  <SpeedRow label="Email analysis incl. text model" value={num(bm.email_analysis?.emails_per_second)} unit="emails/s" note={bm.email_analysis?.note} />
                  <SpeedRow label="Full correlated case analysis" value={num(bm.case_analysis?.cases_per_second)} unit="cases/s" note={bm.case_analysis?.note} />
                  <div className="space-y-1 border-t border-ink-600/70 pt-3 text-xs text-slate-400">
                    {has(bm.when) && <div>Run on: <b className="font-medium text-slate-300">{when(bm.when)}</b></div>}
                    {bm.machine && <div>Host: <b className="font-medium text-slate-300">{[bm.machine.cpus && `${bm.machine.cpus} CPUs`, bm.machine.python && `Python ${bm.machine.python}`].filter(Boolean).join(' · ')}</b></div>}
                  </div>
                </div>
              )}
            </Card>
          </div>

          {/* Real data */}
          <Card title="Real login data (RBA data set)" bodyClassName="p-0" right={rba && <Chip tone="amber">Source values are artificial</Chip>}>
            {!rba ? (
              <EmptyState icon={Database} title="No real-data results yet" message="Run scripts/evaluate_rba.py to score the RBA data set." />
            ) : (
              <div className="space-y-4 p-4 sm:p-5">
                <p className="text-sm leading-relaxed text-slate-300">
                  {num(rba.input?.rows_scored) ? <>Scored <b className="tabular-nums text-slate-100">{num(rba.input.rows_scored)}</b> rows</> : 'Scored rows'}
                  {has(rba.input?.file) && <> from <span className="font-mono text-sky-400">{rba.input.file}</span></>}
                  {has(rba.input?.from) && has(rba.input?.to) && <> ({String(rba.input.from).slice(0, 10)} to {String(rba.input.to).slice(0, 10)})</>}.
                  {has(rba.input?.sampling) && <> {rba.input.sampling}.</>}
                </p>
                <p className="text-xs text-slate-500">Data source: {rba.behavioural_only?.source || rba.with_threat_feed_signal?.source || 'RBA data set'}</p>

                <div className="overflow-x-auto rounded-lg border border-ink-600">
                  <table className="w-full min-w-[36rem] text-left">
                    <thead className="border-b border-ink-600/70 bg-ink-900">
                      <tr><th className="th">Configuration</th><th className="th text-center">Account-takeover rows</th><th className="th text-center">Recall at medium</th><th className="th text-center">AUC</th><th className="th text-right">Failed-login rule AUC</th></tr>
                    </thead>
                    <tbody className="divide-y divide-ink-600/50">
                      {[['Behavioural signals only', rba.behavioural_only], ['Behavioural + known threat-feed IP', rba.with_threat_feed_signal]].map(([name, b]) => b?.all_rows && (
                        <tr key={name}>
                          <td className="td font-medium text-slate-100">{name}</td>
                          <td className="td text-center font-mono tabular-nums">{b.all_rows.account_takeover_rows ?? '—'}</td>
                          <td className="td text-center font-mono tabular-nums">{has(b.all_rows.account_takeover_at_medium?.recall) ? pct(b.all_rows.account_takeover_at_medium.recall) : '—'}</td>
                          <td className="td text-center font-mono tabular-nums">{b.all_rows.auc_account_takeover ?? '—'}</td>
                          <td className="td text-right font-mono tabular-nums text-slate-400">{b.all_rows.auc_account_takeover_failed_login_rule ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {has(rba.behavioural_only?.account_takeover_rows_with_no_or_thin_history) && has(rba.behavioural_only?.all_rows?.account_takeover_rows) && (
                  <div className="flex gap-2.5 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3.5 text-sm text-slate-300">
                    <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-400" />
                    <p className="leading-relaxed">
                      <b className="text-amber-300">{rba.behavioural_only.account_takeover_rows_with_no_or_thin_history} of {rba.behavioural_only.all_rows.account_takeover_rows}</b> account-takeover rows hit accounts with no or thin history, where a behavioural baseline has nothing to compare against.
                      These figures show the pipeline runs correctly on real-format data; they are not detection rates.
                    </p>
                  </div>
                )}
              </div>
            )}
          </Card>

          {notes.length > 0 && (
            <Card title="Methodology notes">
              <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed text-slate-400">{notes.map((n, i) => <li key={i}>{String(n)}</li>)}</ul>
            </Card>
          )}
        </>
      )}
    </div>
  )
}

function Fact({ label, value, wide }) {
  return (
    <div className={`min-w-0 ${wide ? 'sm:col-span-2' : ''}`}>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="mt-0.5 break-words font-medium text-slate-100">{value}</dd>
    </div>
  )
}

function SpeedRow({ label, value, unit, note }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg bg-ink-900 px-3.5 py-3">
      <div className="min-w-0">
        <div className="text-slate-200">{label}</div>
        {note && <div className="mt-0.5 text-xs text-slate-500">{note}</div>}
      </div>
      <div className="shrink-0 text-right font-mono font-semibold tabular-nums text-slate-100">{value ?? '—'} <span className="text-xs font-normal text-slate-500">{value ? unit : ''}</span></div>
    </div>
  )
}
