import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  Clock,
  KeyRound,
  MailWarning,
  RefreshCw,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import api from '../api.js'
import {
  Band,
  Card,
  DateRangePicker,
  Empty,
  ErrorBox,
  PageHeader,
  Spinner,
  StatCard,
  StatusBadge,
  when,
} from '../ui.jsx'
import { useChartTheme, SERIES } from '../theme.jsx'
import { useAutoRefresh } from '../hooks/useAutoRefresh.js'
import { useApi } from '../hooks/useApi.js'
import { BANDS } from '../utils/riskUtils.js'
import { formatDate } from '../utils/formatters.js'

const BAND_ORDER = ['critical', 'high', 'medium', 'low']

// One figure in the triage strip: value, then what it counts.
const Figure = ({ value, label, tone = 'text-slate-100' }) => (
  <div className="min-w-0 px-5 py-3.5">
    <div className={`num text-xl ${tone}`}>{value}</div>
    <div className="mt-0.5 text-xs text-slate-400">{label}</div>
  </div>
)

export default function Dashboard() {
  const [days, setDays] = useState(14)
  const navigate = useNavigate()
  const ct = useChartTheme()

  const { data: o, error, loading, reload } = useApi(
    (signal) => api.get('/overview', { params: { days }, signal }),
    [days]
  )

  const { lastUpdated, isRefreshing, refresh } = useAutoRefresh(reload, 30000, true)

  if (loading && !o) return <Spinner message="Loading security overview…" />
  if (error && !o) return <ErrorBox error={error} onRetry={reload} />
  if (!o) return <Empty>No dashboard data available.</Empty>

  const k = o?.kpis || {}
  const t = o?.triage || {}
  const openByBand = o?.open_by_band || {}
  const activity = o.activity || []
  const emailMix = o.email_mix || { flagged: 0, clean: 0 }
  const emailTotal = (emailMix.flagged || 0) + (emailMix.clean || 0)
  const openTotal = BAND_ORDER.reduce((n, b) => n + (openByBand[b] || 0), 0)
  const hasActivity = activity.some((d) => d.phishing_emails || d.suspicious_logins)
  const pct = (n, d, dec = 1) => (d ? `${((n / d) * 100).toFixed(dec)}%` : '0%')

  return (
    <div className="space-y-6">
      <PageHeader
        title="Security Overview"
        description="Phishing emails and suspicious sign-ins, correlated into ranked incidents for analyst review."
        right={
          <>
            <DateRangePicker
              days={days}
              onChangeDays={(d) => setDays(d)}
              presets={[
                { label: '7d', value: 7 },
                { label: '14d', value: 14 },
                { label: '30d', value: 30 },
                { label: '90d', value: 90 },
              ]}
            />
            <div className="flex h-8 items-center gap-2 rounded-lg border border-ink-600 bg-ink-800 px-2.5 text-xs text-slate-400">
              <Clock size={13} className="text-slate-500" />
              <span>Updated {formatDate(lastUpdated, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
              <button
                type="button"
                onClick={refresh}
                disabled={isRefreshing}
                className="rounded text-slate-400 transition hover:text-sky-300 disabled:opacity-50"
                title="Refresh now"
                aria-label="Refresh dashboard"
              >
                <RefreshCw size={13} className={isRefreshing ? 'animate-spin text-sky-400' : ''} />
              </button>
            </div>
          </>
        }
      />

      {/* Headline metrics: open cases first, then the two detection feeds */}
      <section aria-label="Key metrics" className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatCard
          icon={AlertOctagon}
          label="Critical incidents"
          value={k.critical_incidents ?? 0}
          sub="Open, need investigation now"
          tone="rose"
          size="lg"
          onClick={() => navigate('/response')}
        />
        <StatCard
          icon={AlertTriangle}
          label="High-risk incidents"
          value={openByBand.high ?? 0}
          sub="Open, potential compromise"
          tone="orange"
          size="lg"
          onClick={() => navigate('/response')}
        />
        <StatCard
          icon={MailWarning}
          label="Phishing emails"
          value={k.phishing_emails ?? 0}
          sub={`of ${(k.emails_analyzed ?? 0).toLocaleString()} analyzed · medium risk or above`}
          tone="amber"
          size="lg"
          onClick={() => navigate('/mailbox')}
        />
        <StatCard
          icon={KeyRound}
          label="Suspicious logins"
          value={k.suspicious_logins ?? 0}
          sub={`of ${(k.logins_scored ?? 0).toLocaleString()} scored · medium risk or above`}
          tone="violet"
          size="lg"
          onClick={() => navigate('/logins')}
        />
      </section>

      {/* Triage: one integrated strip instead of four more cards */}
      <section aria-label="Triage summary" className="card grid grid-cols-2 divide-ink-600/50 sm:grid-cols-4 sm:divide-x [&>*:nth-child(-n+2)]:border-b [&>*:nth-child(-n+2)]:border-ink-600/50 sm:[&>*:nth-child(-n+2)]:border-b-0 [&>*:nth-child(2)]:border-l [&>*:nth-child(2)]:border-ink-600/50 sm:[&>*:nth-child(2)]:border-l-0">
        <Figure value={(t.events_scored ?? 0).toLocaleString()} label="Events scored (emails + logins)" />
        <Figure
          value={(t.needs_review ?? 0).toLocaleString()}
          label={`Cases above low risk · ${((t.review_share ?? 0) * 100).toFixed(1)}% of events`}
          tone="text-amber-300"
        />
        <Figure value={(t.auto_closed ?? 0).toLocaleString()} label="Low-risk cases auto-closed" tone="text-emerald-400" />
        <Figure value={(k.open_cases ?? 0).toLocaleString()} label="Open or investigating cases" tone="text-sky-300" />
      </section>

      {/* Trend + risk distribution */}
      <div className="grid gap-5 lg:grid-cols-3">
        <Card
          title="Flagged Events Per Day"
          subtitle={`Last ${days} days · emails and logins scored medium risk or above`}
          className="lg:col-span-2"
        >
          {hasActivity ? (
            <div className="h-72 w-full" role="img" aria-label="Area chart of flagged phishing emails and suspicious logins per day">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={activity} margin={{ top: 10, right: 10, left: -18, bottom: 0 }}>
                  <defs>
                    <linearGradient id="gEmail" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={SERIES.email} stopOpacity={0.28} />
                      <stop offset="95%" stopColor={SERIES.email} stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="gLogin" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={SERIES.login} stopOpacity={0.28} />
                      <stop offset="95%" stopColor={SERIES.login} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke={ct.grid} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="day" {...ct.axis} minTickGap={24} />
                  <YAxis {...ct.axis} allowDecimals={false} />
                  <Tooltip {...ct.tooltip} />
                  <Legend {...ct.legend} />
                  <Area type="monotone" dataKey="phishing_emails" name="Phishing emails" stroke={SERIES.email} strokeWidth={2} fill="url(#gEmail)" />
                  <Area type="monotone" dataKey="suspicious_logins" name="Suspicious logins" stroke={SERIES.login} strokeWidth={2} fill="url(#gLogin)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Empty>No flagged emails or logins in the last {days} days.</Empty>
          )}
        </Card>

        <Card title="Open Cases by Risk Band" subtitle={`${openTotal.toLocaleString()} open or investigating`}>
          <ul className="space-y-3.5">
            {BAND_ORDER.map((b) => {
              const n = openByBand[b] || 0
              return (
                <li key={b}>
                  <div className="mb-1.5 flex items-center justify-between text-xs">
                    <span className="flex items-center gap-2 font-medium text-slate-200">
                      <span className="h-2 w-2 rounded-full" style={{ background: BANDS[b].dot }} />
                      {BANDS[b].label}
                    </span>
                    <span className="num text-sm">
                      {n.toLocaleString()}
                      <span className="ml-1.5 text-xs font-normal text-slate-500">{pct(n, openTotal, 0)}</span>
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-ink-700" role="presentation">
                    <div className="h-full rounded-full" style={{ width: pct(n, openTotal, 1), background: BANDS[b].dot }} />
                  </div>
                </li>
              )
            })}
          </ul>

          <div className="mt-6 border-t border-ink-600/50 pt-4">
            <div className="flex items-baseline justify-between">
              <span className="eyebrow">Email screening</span>
              <span className="text-xs text-slate-400">{emailTotal.toLocaleString()} analyzed</span>
            </div>
            <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-emerald-500/30" role="img" aria-label={`${emailMix.flagged} of ${emailTotal} emails flagged`}>
              <div className="h-full bg-orange-500" style={{ width: `${emailTotal ? Math.max((emailMix.flagged / emailTotal) * 100, emailMix.flagged ? 1.5 : 0) : 0}%` }} />
            </div>
            <div className="mt-2 flex justify-between text-xs">
              <span className="text-orange-300">
                <b className="font-semibold">{(emailMix.flagged || 0).toLocaleString()}</b> flagged · {pct(emailMix.flagged || 0, emailTotal)}
              </span>
              <span className="text-emerald-400">
                <b className="font-semibold">{(emailMix.clean || 0).toLocaleString()}</b> clean
              </span>
            </div>
          </div>
        </Card>
      </div>

      {/* Analyst work queues */}
      <div className="grid gap-5 lg:grid-cols-2">
        <Card
          title="Action Queue"
          subtitle="High and critical, by score"
          right={
            <Link to="/response" className="inline-flex items-center gap-1 text-xs font-medium text-sky-400 transition hover:text-sky-300">
              Open queue <ArrowRight size={12} />
            </Link>
          }
          bodyClassName="p-2 sm:p-3"
        >
          {!o.action_needed || o.action_needed.length === 0 ? (
            <Empty>No high-risk incidents pending action.</Empty>
          ) : (
            <ul className="max-h-72 space-y-0.5 overflow-y-auto">
              {o.action_needed.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => navigate(`/response/${c.id}`)}
                    className="flex w-full items-center justify-between gap-3 rounded-lg px-2.5 py-2.5 text-left transition hover:bg-ink-700/50"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-1.5 truncate text-sm font-medium text-slate-200">
                        {c.user}
                        {c.campaign_size > 1 && (
                          <span className="rounded border border-rose-500/30 bg-rose-500/10 px-1 text-[10px] font-normal text-rose-300">
                            campaign of {c.campaign_size}
                          </span>
                        )}
                      </span>
                      <span className="mt-0.5 block truncate text-xs text-slate-400">{c.headline}</span>
                    </span>
                    <span className="flex shrink-0 flex-col items-end gap-1">
                      <Band band={c.band} score={c.score} />
                      {c.pending_approvals > 0 && (
                        <span className="text-[10px] font-semibold text-amber-300">{c.pending_approvals} awaiting approval</span>
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title="Top Suspicious Users"
          subtitle="Open cases with the highest score"
          right={
            <Link to="/investigate" className="inline-flex items-center gap-1 text-xs font-medium text-sky-400 transition hover:text-sky-300">
              View all <ArrowRight size={12} />
            </Link>
          }
          bodyClassName="p-2 sm:p-3"
        >
          {!o.top_users || o.top_users.length === 0 ? (
            <Empty>No flagged user activity.</Empty>
          ) : (
            <ul className="max-h-72 space-y-0.5 overflow-y-auto">
              {o.top_users.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => navigate(`/investigate/${c.id}`)}
                    className="flex w-full items-center justify-between gap-3 rounded-lg px-2.5 py-2.5 text-left transition hover:bg-ink-700/50"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-slate-200">{c.user}</span>
                      <span className="mt-0.5 block truncate text-xs text-slate-500">
                        Case #{c.id} · {c.headline}
                      </span>
                    </span>
                    <Band band={c.band} score={c.score} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* Recent security alerts */}
      <Card
        title="Recent Security Alerts"
        subtitle="Latest cases above low risk"
        right={<span className="text-xs text-slate-400">{o.recent_alerts?.length || 0} cases</span>}
        bodyClassName="p-0"
      >
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="border-b border-ink-600/50 bg-ink-900/50">
              <tr>
                <th className="th">User</th>
                <th className="th">Finding</th>
                <th className="th">Risk</th>
                <th className="th">Status</th>
                <th className="th text-right">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-600/40">
              {!o.recent_alerts || o.recent_alerts.length === 0 ? (
                <tr>
                  <td colSpan={5} className="td py-8 text-center text-slate-500">No recent security alerts.</td>
                </tr>
              ) : (
                o.recent_alerts.map((c) => (
                  <tr key={c.id} className="transition-colors hover:bg-ink-700/40">
                    <td className="td whitespace-nowrap font-medium">
                      <Link to={`/investigate/${c.id}`} className="text-sky-300 hover:underline">{c.user}</Link>
                    </td>
                    <td className="td max-w-md truncate text-slate-300">
                      {c.headline}
                      {c.campaign_size > 1 && <span className="ml-1.5 text-xs text-slate-500">(campaign of {c.campaign_size})</span>}
                    </td>
                    <td className="td"><Band band={c.band} score={c.score} /></td>
                    <td className="td"><StatusBadge status={c.status} /></td>
                    <td className="td whitespace-nowrap text-right text-xs text-slate-500">{when(c.updated_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
