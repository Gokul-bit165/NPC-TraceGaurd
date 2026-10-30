import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  AlertCircle,
  Download,
  FileSearch,
  Info,
  KeyRound,
  Mail,
  Printer,
  ShieldAlert,
  Sparkles,
} from 'lucide-react'
import DecisionPanel from '../components/DecisionPanel.jsx'
import api, { errText } from '../api.js'
import {
  Card,
  Chip,
  CodeChip,
  EmptyState,
  ErrorState,
  LoadingState,
  Narrative,
  NotificationToast,
  PageHeader,
  RiskBadge,
  StatusBadge,
  when,
} from '../ui.jsx'
import { useApi } from '../hooks/useApi.js'

const SIDE = {
  email: { label: 'Email', short: 'E', tone: 'amber', bar: 'bg-amber-500' },
  login: { label: 'Login', short: 'L', tone: 'violet', bar: 'bg-violet-500' },
  correlation: { label: 'Correlation', short: 'X', tone: 'sky', bar: 'bg-sky-500' },
  cap: { label: 'Cap / adjustment', short: '•', tone: 'slate', bar: 'bg-slate-500' },
}
const sideOf = (s) => SIDE[s] || SIDE.cap
const asArray = (v) => (Array.isArray(v) ? v : [])
const signed = (n) => (n > 0 ? `+${n}` : String(n))

export function CaseList({ base }) {
  const { id } = useParams()
  const { data, loading, error, reload } = useApi(() => api.get('/cases', { params: { status: 'active', limit: 60 } }))
  const items = asArray(data?.items)

  return (
    <div className="card flex max-h-72 flex-col overflow-hidden lg:max-h-[calc(100vh-11rem)] lg:sticky lg:top-24">
      <div className="flex shrink-0 items-center justify-between border-b border-ink-600/70 bg-ink-900 px-4 py-3">
        <span className="section-title">Active incidents</span>
        <span className="rounded-full bg-ink-700 px-2 py-0.5 text-xs font-semibold tabular-nums text-slate-300">{data?.total ?? 0}</span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading && !data ? (
          <div className="space-y-2 p-3">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-14 w-full" />)}</div>
        ) : error && !data ? (
          <div className="p-3"><ErrorState error={error} title="Unable to load incidents" onRetry={reload} /></div>
        ) : items.length === 0 ? (
          <EmptyState icon={FileSearch} title="No active incidents" message="New incidents appear here as the engine scores email and login evidence." />
        ) : (
          <ul className="divide-y divide-ink-600/50">
            {items.map((c) => {
              const selected = String(c.id) === String(id)
              return (
                <li key={c.id}>
                  <Link
                    to={`/${base}/${c.id}`}
                    aria-current={selected ? 'true' : undefined}
                    className={`block px-4 py-3 transition-colors hover:bg-ink-700/50 ${selected ? 'bg-sky-500/10 shadow-[inset_3px_0_0_rgb(var(--sky-500))]' : ''}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-semibold text-slate-100">{c.user?.name || c.user?.id}</span>
                      <RiskBadge band={c.band} score={c.score} size="xs" />
                    </div>
                    <div className="mt-1 truncate text-xs text-slate-400">
                      {c.headline}
                      {c.campaign_size > 1 && <span className="ml-1 text-rose-400">· campaign of {c.campaign_size}</span>}
                    </div>
                    <div className="mt-1.5 flex items-center justify-between text-[11px] text-slate-500">
                      <span>Case #{c.id}</span>
                      <span>{when(c.updated_at)}</span>
                    </div>
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}

export default function Investigation() {
  const { id } = useParams()
  const navigate = useNavigate()

  // With no case in the URL, open the highest-ranked active case.
  const { data: first, loading: firstLoading, error: firstError, reload: reloadFirst } = useApi(
    () => (id ? Promise.resolve({ data: null }) : api.get('/cases', { params: { status: 'active', limit: 1 } })),
    [id],
  )

  useEffect(() => {
    const target = first?.items?.[0]
    if (!id && target) navigate(`/investigate/${target.id}`, { replace: true })
  }, [id, first, navigate])

  let body
  if (id) {
    body = <CaseView key={id} id={id} />
  } else if (firstLoading) {
    body = <LoadingState variant="page" message="Opening the highest-risk case…" />
  } else if (firstError) {
    body = <ErrorState error={firstError} title="Unable to load investigation." onRetry={reloadFirst} />
  } else {
    body = (
      <Card>
        <EmptyState icon={FileSearch} title="No investigation to show" message="There are no active incidents. Select a case from the list when one is available." />
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={FileSearch}
        title="AI Investigation"
        description="Every claim in the explanation points at a line in the evidence ledger, and the score is the sum of that ledger."
      />
      <div className="grid gap-6 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <CaseList base="investigate" />
        <div className="min-w-0 space-y-6">{body}</div>
      </div>
    </div>
  )
}

function CaseView({ id }) {
  const { data: d, error, status, loading, reload } = useApi(() => api.get(`/cases/${id}`), [id])
  const [downloading, setDownloading] = useState(false)
  const [toast, setToast] = useState(null)
  const [highlightedCode, setHighlightedCode] = useState(null)
  const clearTimer = useRef(null)

  useEffect(() => () => clearTimeout(clearTimer.current), [])

  const jumpToEvidence = useCallback((code) => {
    setHighlightedCode(code)
    requestAnimationFrame(() => {
      document.getElementById(`evidence-${code}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
    clearTimeout(clearTimer.current)
    clearTimer.current = setTimeout(() => setHighlightedCode(null), 6000)
  }, [])

  const downloadReport = async () => {
    setDownloading(true)
    try {
      const res = await api.get(`/cases/${id}/report`, { responseType: 'blob' })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `traceguard-case-${id}.md`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      setToast({ type: 'error', message: `Could not download the report: ${errText(e)}` })
    } finally {
      setDownloading(false)
    }
  }

  if (loading && !d) return <LoadingState variant="page" message="Compiling investigation evidence…" />

  if (error && !d) {
    if (status === 404) {
      return (
        <Card>
          <EmptyState icon={FileSearch} title="Investigation not found." message={`There is no case with ID ${id}. It may have been removed, or the link is wrong.`} action={reload} actionLabel="Check again" />
          <div className="pb-6 text-center"><Link to="/investigate" className="text-sm font-medium text-sky-400 hover:underline">Open the highest-risk case</Link></div>
        </Card>
      )
    }
    return <ErrorState error={error} title="Unable to load investigation." onRetry={reload} />
  }

  if (!d?.case) {
    return (
      <Card>
        <EmptyState icon={FileSearch} title="Investigation not found." message="The server returned no case data for this ID." action={reload} actionLabel="Retry" />
      </Card>
    )
  }

  const c = d.case
  const user = d.user || c.user || {}
  const ex = d.extras || {}
  const nar = d.narrative || {}
  const ledger = asArray(d.ledger)
  const timeline = asArray(d.timeline)
  const logins = asArray(d.recent_logins)
  const formula = d.formula || ex.formula || ''
  const uplift = ex.uplift ?? 0
  // A "cap" row is itself the adjustment (negative points, no raw value); every other row was clamped from raw_points.
  const isAdjustment = (e) => e.side === 'cap'
  const capped = ledger.filter((e) => isAdjustment(e) || (e.raw_points !== undefined && e.raw_points !== e.points))
  const maxPts = Math.max(1, ...ledger.map((e) => Math.abs(e.points || 0)))
  const findingFor = (code) => asArray(nar.findings).find((f) => f.code === code)
  const active = highlightedCode ? ledger.find((e) => e.code === highlightedCode) : null

  return (
    <div className="space-y-6">
      <NotificationToast show={!!toast} message={toast?.message} type={toast?.type} onClose={() => setToast(null)} />

      {/* Header */}
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-400">
              <span className="font-mono font-medium text-slate-300">Case #{c.id}</span>
              <span aria-hidden="true">·</span>
              <StatusBadge status={c.status} />
              {c.verdict && <Chip tone={c.verdict === 'true_positive' ? 'rose' : 'emerald'}>{c.verdict === 'true_positive' ? 'Confirmed threat' : 'False alarm'}</Chip>}
            </div>
            <h2 className="text-xl font-semibold tracking-tight text-slate-100">{nar.headline || c.headline}</h2>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-400">
              <span>User: <b className="font-medium text-slate-200">{user.name || user.id}</b>{user.email ? <span className="text-slate-500"> ({user.email})</span> : null}</span>
              {user.dept && <span>Dept: <b className="font-medium text-slate-200">{user.dept}</b></span>}
              <span>Updated: <b className="font-medium text-slate-200">{when(c.updated_at) || 'n/a'}</b></span>
            </div>
            {c.campaign_size > 1 && <p className="text-sm font-medium text-rose-400">Part of a phishing campaign reaching {c.campaign_size} recipients.</p>}
          </div>

          <div className="no-print flex flex-wrap items-center gap-2">
            <RiskBadge band={c.band} score={c.score} size="lg" />
            <Link to={`/response/${c.id}`} className="btn btn-primary text-xs"><ShieldAlert size={14} /> Respond</Link>
            <button type="button" onClick={downloadReport} disabled={downloading} className="btn btn-ghost text-xs" title="Download the investigation report (Markdown)">
              <Download size={14} /> {downloading ? 'Preparing…' : 'Report'}
            </button>
            <button type="button" onClick={() => window.print()} className="btn btn-ghost hidden text-xs sm:inline-flex"><Printer size={14} /> Print</button>
          </div>
        </div>

        {d.low_confidence_reason && (
          <div className="mt-4 flex gap-2.5 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-300">
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
            <div><b className="font-semibold">Low confidence.</b> <span className="text-slate-300">{d.low_confidence_reason}</span></div>
          </div>
        )}
      </Card>

      <DecisionPanel caseId={c.id} />

      {/* Risk score + breakdown */}
      <Card title="Risk score and breakdown" right={<span className="text-xs text-slate-400">Computed by the backend; shown unchanged</span>}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <ScoreTile icon={Mail} tone="amber" label="Email evidence" value={c.email_score} note="Email-only cases are capped below critical" />
          <ScoreTile icon={KeyRound} tone="violet" label="Login evidence" value={c.login_score} note="Sign-in behaviour vs baseline" />
          <ScoreTile icon={Sparkles} tone="sky" label="Correlation uplift" value={uplift ? `+${uplift}` : '0'} note={c.correlated ? 'Email followed by suspicious login' : 'No correlation found'} />
          <div className="rounded-xl border border-ink-600 bg-ink-900 p-3.5 ring-1 ring-inset ring-sky-500/20">
            <div className="text-xs font-medium text-slate-400">Case score</div>
            <div className="mt-1 text-3xl font-semibold tabular-nums text-slate-100">{c.score}<span className="text-base font-normal text-slate-500"> / 100</span></div>
            <div className="mt-1"><RiskBadge band={c.band} size="xs" /></div>
          </div>
        </div>

        {formula && (
          <div className="mt-4 rounded-lg border border-ink-600 bg-ink-900 p-3.5">
            <div className="section-title mb-1">Scoring formula (from backend)</div>
            <code className="block break-words font-mono text-[13px] leading-relaxed text-sky-300">{formula}</code>
          </div>
        )}

        {capped.length > 0 && (
          <div className="mt-4 rounded-lg border border-ink-600 bg-ink-900 p-3.5">
            <div className="section-title mb-2">Caps and adjustments applied</div>
            <ul className="space-y-1.5 text-sm text-slate-300">
              {capped.map((e, i) => (
                <li key={`${e.code}-${i}`} className="flex flex-wrap items-center gap-x-2">
                  <CodeChip code={e.code} />
                  {isAdjustment(e)
                    ? <span>{e.label}: adjusts the score by <b className="tabular-nums">{signed(e.points)}</b></span>
                    : <span>{e.label}: raw <b className="tabular-nums">{e.raw_points}</b> → applied <b className="tabular-nums">{e.points}</b></span>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      {/* Explanation */}
      <Card
        title="AI explanation"
        right={<Chip tone={nar.source === 'llm' ? 'violet' : 'slate'}>{nar.source === 'llm' ? 'Language model, validated against evidence' : 'Deterministic template from evidence'}</Chip>}
      >
        {nar.summary ? (
          <div className="space-y-3">
            <Narrative text={nar.summary} onReasonCodeClick={jumpToEvidence} />
            <p className="flex items-center gap-1.5 text-xs text-slate-500"><Info size={12} /> Select a reason code to jump to the evidence behind it.</p>
            {active && (
              <div className="flex flex-wrap items-start justify-between gap-2 rounded-lg border border-sky-500/40 bg-sky-500/10 p-3 text-sm" role="status">
                <div className="min-w-0">
                  <CodeChip code={active.code} />
                  <p className="mt-1.5 text-slate-300">{findingFor(active.code)?.text || [active.label, active.detail].filter(Boolean).join(': ')}</p>
                  <p className="mt-1 text-xs text-slate-400">Contributes <b className="tabular-nums text-slate-200">{signed(active.points)}</b> points to the {sideOf(active.side).label.toLowerCase()} score.</p>
                </div>
                <button type="button" onClick={() => setHighlightedCode(null)} className="text-xs font-medium text-sky-400 hover:underline">Clear</button>
              </div>
            )}
            {nar.rejected_reason && (
              <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-300">
                <b>Language-model text was rejected:</b> {nar.rejected_reason}. The verified template is shown instead.
              </div>
            )}
          </div>
        ) : (
          <EmptyState icon={Sparkles} title="No explanation recorded" message="This case has no narrative stored. The evidence ledger below is still authoritative." />
        )}
      </Card>

      {/* Evidence + timeline */}
      <div className="grid gap-6 xl:grid-cols-5">
        <Card title="Evidence ledger" className="xl:col-span-3" bodyClassName="p-0" right={<span className="text-xs text-slate-400">{ledger.length} {ledger.length === 1 ? 'item' : 'items'}</span>}>
          {ledger.length === 0 ? (
            <EmptyState icon={FileSearch} title="No evidence recorded" message="No scoring signals fired for this case." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[34rem] text-left">
                <thead className="border-b border-ink-600/70 bg-ink-900">
                  <tr><th className="th">Evidence</th><th className="th">Type</th><th className="th">Source</th><th className="th text-right">Points</th></tr>
                </thead>
                <tbody className="divide-y divide-ink-600/50">
                  {ledger.map((e, i) => {
                    const s = sideOf(e.side)
                    const hit = highlightedCode === e.code
                    const wasCapped = !isAdjustment(e) && e.raw_points !== undefined && e.raw_points !== e.points
                    return (
                      <tr key={`${e.code}-${i}`} id={`evidence-${e.code}`} className={`scroll-mt-28 transition-colors duration-300 ${hit ? 'bg-sky-500/15 shadow-[inset_3px_0_0_rgb(var(--sky-500))]' : 'hover:bg-ink-700/40'} ${e.points === 0 ? 'opacity-60' : ''}`}>
                        <td className="td align-top">
                          <CodeChip code={e.code} />
                          <div className="mt-1 font-medium text-slate-100">{e.label}</div>
                          {e.detail && <div className="mt-0.5 text-xs leading-relaxed text-slate-400">{e.detail}</div>}
                        </td>
                        <td className="td align-top"><Chip tone={s.tone}>{s.label}</Chip>{e.group && <div className="mt-1 text-[11px] text-slate-500">{e.group}</div>}</td>
                        <td className="td align-top font-mono text-xs text-slate-400">{e.ref || '—'}</td>
                        <td className="td align-top text-right">
                          <span className={`font-mono text-sm font-semibold tabular-nums ${e.points > 0 ? 'text-amber-400' : 'text-slate-500'}`}>{signed(e.points ?? 0)}</span>
                          <div className="ml-auto mt-1.5 h-1 w-14 overflow-hidden rounded-full bg-ink-700"><div className={`h-full ${s.bar}`} style={{ width: `${(Math.abs(e.points || 0) / maxPts) * 100}%` }} /></div>
                          {wasCapped && <div className="mt-1 text-[10px] text-slate-500">cap hit, was {e.raw_points}</div>}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <div className="space-y-6 xl:col-span-2">
          <Card title="Timeline" right={<span className="text-xs text-slate-400">Chronological</span>}>
            {timeline.length === 0 ? (
              <EmptyState icon={FileSearch} title="No events" message="No timeline events were recorded for this case." className="!py-6" />
            ) : (
              <ol className="relative ml-2 space-y-4 border-l border-ink-600 pl-5">
                {[...timeline].sort((a, b) => String(a.ts).localeCompare(String(b.ts))).map((t, i) => (
                  <li key={i} className="relative">
                    <span className={`absolute -left-[27px] top-1 h-3 w-3 rounded-full border-2 border-ink-800 ${t.kind === 'email' ? 'bg-amber-500' : t.severity === 'high' || t.severity === 'critical' ? 'bg-rose-500' : 'bg-slate-500'}`} />
                    <div className="font-mono text-[11px] text-slate-500">{when(t.ts)}</div>
                    <div className="mt-0.5 text-sm leading-relaxed text-slate-200">{t.text}</div>
                  </li>
                ))}
              </ol>
            )}
          </Card>

          {asArray(d.not_evaluated).length > 0 && (
            <Card title="Checks not performed">
              <ul className="list-disc space-y-1.5 pl-4 text-xs leading-relaxed text-amber-300">
                {d.not_evaluated.map((x, i) => <li key={i}><span className="text-slate-300">{x}</span></li>)}
              </ul>
            </Card>
          )}
        </div>
      </div>

      {/* Email + login */}
      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Related email">
          {!d.email ? (
            <EmptyState icon={Mail} title="No email linked" message="No phishing email is attached to this case." className="!py-6" />
          ) : (
            <div className="space-y-4 text-sm">
              <dl className="grid gap-x-4 gap-y-2 rounded-lg bg-ink-900 p-3.5 text-xs sm:grid-cols-2">
                <div className="min-w-0"><dt className="text-slate-500">Sender</dt><dd className="break-all font-mono text-slate-200">{d.email.sender}</dd></div>
                <div><dt className="text-slate-500">Received</dt><dd className="text-slate-200">{when(d.email.received_at)}</dd></div>
                {d.email.reply_to && <div className="min-w-0 sm:col-span-2"><dt className="text-slate-500">Reply-To</dt><dd className="break-all font-mono text-slate-200">{d.email.reply_to}</dd></div>}
                <div className="min-w-0 sm:col-span-2"><dt className="text-slate-500">Subject</dt><dd className="break-words font-semibold text-slate-100">{d.email.subject}</dd></div>
              </dl>

              <div className="flex flex-wrap items-center gap-1.5">
                <span className="mr-1 text-xs font-medium text-slate-400">Authentication</span>
                {Object.entries(d.email.auth || {}).filter(([k]) => ['spf', 'dkim', 'dmarc'].includes(k)).map(([k, v]) => (
                  <Chip key={k} tone={v === 'pass' ? 'emerald' : 'rose'}>{k.toUpperCase()} {String(v)}</Chip>
                ))}
                {!d.email.has_headers && <Chip tone="amber">No headers to verify</Chip>}
              </div>

              {d.email.hidden_text_found && (
                <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-300"><b>Hidden text found.</b> It was stripped before analysis and recorded as evidence.</div>
              )}

              <div>
                <div className="section-title mb-1.5">Message preview (plain text, never executed)</div>
                {/* Rendered as a React text node: attacker markup stays inert text. */}
                <pre className="max-h-44 overflow-y-auto whitespace-pre-wrap break-words rounded-lg border border-ink-600 bg-ink-900 p-3 font-mono text-xs leading-relaxed text-slate-300">{d.email.preview || '(empty)'}</pre>
              </div>

              {asArray(ex.flagged_links).length > 0 && (
                <div>
                  <div className="section-title mb-1.5 !text-rose-400">Flagged link targets (shown as text, not clickable)</div>
                  <ul className="space-y-1.5">
                    {ex.flagged_links.map((l, i) => (
                      <li key={i} className="rounded-lg border border-rose-500/30 bg-rose-500/5 p-2.5">
                        <div className="break-all font-mono text-xs text-rose-300">{l.href}</div>
                        <div className="mt-0.5 text-xs text-slate-400">{l.reason}</div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {asArray(d.text_terms).length > 0 && (
                <div>
                  <div className="section-title mb-1.5">Terms raising the text-model score</div>
                  <div className="flex flex-wrap gap-1.5">{d.text_terms.map((t) => <Chip key={t.term} tone="amber">{t.term}</Chip>)}</div>
                </div>
              )}
            </div>
          )}
        </Card>

        <Card title="Related login activity" bodyClassName="p-0">
          {d.suspicious_login && (
            <div className="border-b border-ink-600/70 p-4 sm:px-5">
              <div className="section-title mb-1.5">Suspicious sign-in</div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-200">
                <b>{[d.suspicious_login.city, d.suspicious_login.country].filter(Boolean).join(', ') || 'Unknown location'}</b>
                <span className="font-mono text-xs text-slate-400">{d.suspicious_login.ip}</span>
                <span className="text-xs text-slate-400">{d.suspicious_login.device || 'Unknown device'}</span>
                <span className="text-xs text-slate-500">{when(d.suspicious_login.ts)}</span>
              </div>
            </div>
          )}
          {logins.length === 0 ? (
            <EmptyState icon={KeyRound} title="No login events" message="No sign-ins were recorded for this user before the case time." className="!py-8" />
          ) : (
            <div className="max-h-80 overflow-auto">
              <table className="w-full min-w-[30rem] text-left text-xs">
                <thead className="sticky top-0 border-b border-ink-600/70 bg-ink-900"><tr><th className="th">Time</th><th className="th">Location / IP</th><th className="th">Device</th><th className="th">Result</th><th className="th text-right">Risk</th></tr></thead>
                <tbody className="divide-y divide-ink-600/50">
                  {logins.map((r, i) => (
                    <tr key={i} className={r.flagged ? 'bg-amber-500/10' : 'hover:bg-ink-700/40'}>
                      <td className="td whitespace-nowrap font-mono text-slate-400">{when(r.ts)}</td>
                      <td className="td"><div className="text-slate-200">{[r.city, r.country].filter(Boolean).join(', ') || 'Unknown'}</div><div className="font-mono text-[11px] text-slate-500">{r.ip}</div></td>
                      <td className="td text-slate-400">{r.device || 'Unknown'}</td>
                      <td className="td">{r.success ? <span className="text-emerald-400">Success</span> : <span className="font-semibold text-rose-400">Failed</span>}</td>
                      <td className="td text-right"><RiskBadge score={r.risk} size="xs" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

function ScoreTile({ icon: Icon, tone, label, value, note }) {
  const color = { amber: 'text-amber-400', violet: 'text-violet-400', sky: 'text-sky-400' }[tone]
  return (
    <div className="rounded-xl border border-ink-600 bg-ink-900 p-3.5">
      <div className="flex items-center gap-1.5 text-xs font-medium text-slate-400"><Icon size={14} className={color} />{label}</div>
      <div className="mt-1 text-3xl font-semibold tabular-nums text-slate-100">{value ?? '—'}</div>
      <div className="mt-1 text-[11px] leading-snug text-slate-500">{note}</div>
    </div>
  )
}
