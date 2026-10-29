import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle,
  Clock,
  Eye,
  KeyRound,
  Mail,
  MailWarning,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  TrendingUp,
  Users,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import api from '../api.js'
import {
  Band,
  Card,
  Chip,
  DateRangePicker,
  Empty,
  ErrorBox,
  PageHeader,
  RiskBadge,
  Spinner,
  StatCard,
  when,
} from '../ui.jsx'
import { useChartTheme, SERIES } from '../theme.jsx'
import { useAutoRefresh } from '../hooks/useAutoRefresh.js'
import { useApi } from '../hooks/useApi.js'
import { formatDate } from '../utils/formatters.js'

export default function Dashboard() {
  const [days, setDays] = useState(14)
  const navigate = useNavigate()
  const ct = useChartTheme()

  const { data: o, error, loading, reload } = useApi(
    (signal) => api.get('/overview', { params: { days }, signal }),
    [days]
  )

  const { lastUpdated, isRefreshing, refresh, autoRefreshEnabled, setAutoRefreshEnabled } =
    useAutoRefresh(reload, 30000, true)

  if (loading && !o) return <Spinner message="Loading security overview dashboard…" />
  if (error && !o) return <ErrorBox error={error} onRetry={reload} />
  if (!o) return <Empty>No dashboard data available.</Empty>

  const k = o?.kpis || {}
  const t = o?.triage || {}
  const openByBand = o?.open_by_band || {}

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="Security Dashboard"
        description="Unified security command center correlating phishing emails and suspicious sign-in events into ranked, actionable incidents."
        right={
          <div className="flex flex-wrap items-center gap-3">
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
            <div className="flex items-center gap-2 rounded-lg border border-ink-600/60 bg-ink-900 px-2.5 py-1 text-xs text-slate-400">
              <span className="flex items-center gap-1 text-slate-400">
                <Clock size={13} className="text-slate-500" />
                Updated {formatDate(lastUpdated, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
              <button
                type="button"
                onClick={refresh}
                disabled={isRefreshing}
                className="text-slate-400 hover:text-sky-300 transition disabled:opacity-50"
                title="Refresh now"
              >
                <RefreshCw size={13} className={isRefreshing ? 'animate-spin text-sky-400' : ''} />
              </button>
            </div>
          </div>
        }
      />

      {/* Key Number Metric Cards */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatCard
          icon={AlertOctagon}
          label="Critical Threats"
          value={k.critical_incidents ?? 0}
          sub="Requires immediate response"
          tone="rose"
          onClick={() => navigate('/response')}
        />
        <StatCard
          icon={AlertTriangle}
          label="High-Risk Incidents"
          value={openByBand.high ?? 0}
          sub="Potential compromise"
          tone="amber"
          onClick={() => navigate('/response')}
        />
        <StatCard
          icon={MailWarning}
          label="Phishing Emails"
          value={k.phishing_emails ?? 0}
          sub={`Out of ${k.emails_analyzed?.toLocaleString() || 0} analyzed`}
          tone="amber"
          onClick={() => navigate('/email')}
        />
        <StatCard
          icon={KeyRound}
          label="Suspicious Logins"
          value={k.suspicious_logins ?? 0}
          sub={`Out of ${k.logins_scored?.toLocaleString() || 0} scored`}
          tone="violet"
          onClick={() => navigate('/logins')}
        />
      </div>

      {/* Triage Summary Ribbon */}
      <div className="card flex flex-wrap items-center justify-between gap-4 px-5 py-3.5 text-xs sm:text-sm bg-gradient-to-r from-ink-900 to-ink-800 border-ink-600/70">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <span className="flex items-center gap-1.5 font-bold text-slate-100">
            <ShieldCheck size={16} className="text-sky-400" />
            Triage Summary
          </span>
          <span className="text-slate-300">
            <b className="text-slate-100 font-semibold">{t.events_scored?.toLocaleString() ?? 0}</b>{' '}
            <span className="text-slate-400">events scored</span>
          </span>
          <span className="text-slate-300">
            <b className="text-amber-300 font-semibold">{t.needs_review ?? 0}</b>{' '}
            <span className="text-slate-400">
              require human review ({((t.review_share ?? 0) * 100).toFixed(1)}% of events)
            </span>
          </span>
          <span className="text-slate-300">
            <b className="text-emerald-400 font-semibold">{t.auto_closed ?? 0}</b>{' '}
            <span className="text-slate-400">low-risk cases auto-closed</span>
          </span>
          <span className="text-slate-300">
            <b className="text-sky-400 font-semibold">{k.open_cases ?? 0}</b>{' '}
            <span className="text-slate-400">active open cases</span>
          </span>
        </div>
        <div className="text-[11px] text-slate-500 font-medium">
          Automated baseline filtering saves ~{Math.max(0, 100 - Math.round((t.review_share ?? 0) * 100))}% analyst triage workload
        </div>
      </div>

      {/* Threat Activity & Email Mix Charts */}
      <div className="grid gap-5 lg:grid-cols-3">
        <Card
          title={`Threat Activity Over Time (${days} Days)`}
          right={<span className="text-xs text-slate-400">Flagged events per day</span>}
          className="lg:col-span-2"
        >
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={o.activity || []} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorPhishing" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#fbbf24" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#fbbf24" stopOpacity={0.0} />
                  </linearGradient>
                  <linearGradient id="colorLogins" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#a78bfa" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#a78bfa" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={ct.grid} strokeDasharray="3 3" />
                <XAxis dataKey="day" {...ct.axis} />
                <YAxis {...ct.axis} allowDecimals={false} />
                <Tooltip {...ct.tooltip} />
                <Legend {...ct.legend} />
                <Area
                  type="monotone"
                  dataKey="phishing_emails"
                  name="Phishing Emails"
                  stroke="#fbbf24"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#colorPhishing)"
                />
                <Area
                  type="monotone"
                  dataKey="suspicious_logins"
                  name="Suspicious Logins"
                  stroke="#a78bfa"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#colorLogins)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card
          title="Phishing vs Clean Emails"
          right={<span className="text-xs text-slate-400">Total: {k.emails_analyzed?.toLocaleString() || 0}</span>}
        >
          <div className="h-64 w-full flex items-center justify-center">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={[
                    { name: 'Flagged (Phishing)', value: o.email_mix?.flagged || 0 },
                    { name: 'Clean (Legitimate)', value: o.email_mix?.clean || 0 },
                  ]}
                  dataKey="value"
                  innerRadius={60}
                  outerRadius={88}
                  paddingAngle={3}
                  stroke={ct.cellStroke}
                  strokeWidth={2}
                >
                  <Cell fill="#f97316" />
                  <Cell fill="#34d399" />
                </Pie>
                <Tooltip {...ct.tooltip} />
                <Legend {...ct.legend} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {/* Logins by Location, High-Risk Queue & Top Suspicious Users */}
      <div className="grid gap-5 lg:grid-cols-3">
        {/* Login activity by country */}
        <Card
          title={`Login Activity by Country (${days} Days)`}
          right={<span className="text-xs text-slate-400">Top 10 Sources</span>}
        >
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={o.countries || []}
                layout="vertical"
                margin={{ top: 5, right: 15, left: 5, bottom: 5 }}
              >
                <CartesianGrid stroke={ct.grid} strokeDasharray="3 3" />
                <XAxis type="number" {...ct.axis} />
                <YAxis
                  type="category"
                  dataKey="country"
                  {...ct.axis} width={34}
                />
                <Tooltip {...ct.tooltip} />
                <Legend {...ct.legend} />
                <Bar dataKey="flagged" name="Flagged" stackId="a" fill="#f97316" radius={[0, 0, 0, 0]} />
                <Bar dataKey="failed" name="Failed" stackId="a" fill={ct.neutral} radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* High-risk incidents requiring action */}
        <Card
          title="High-Risk Incidents"
          right={
            <Link
              to="/response"
              className="text-xs font-medium text-sky-400 hover:text-sky-300 transition inline-flex items-center gap-1"
            >
              Open queue →
            </Link>
          }
        >
          {!o.action_needed || o.action_needed.length === 0 ? (
            <Empty>No high-risk incidents pending action.</Empty>
          ) : (
            <ul className="divide-y divide-ink-600/50 max-h-72 overflow-y-auto pr-1">
              {o.action_needed.map((c) => (
                <li
                  key={c.id}
                  onClick={() => navigate(`/response/${c.id}`)}
                  className="flex items-center justify-between py-2.5 px-1 hover:bg-ink-700/40 rounded-lg cursor-pointer transition"
                >
                  <div className="min-w-0 flex-1 pr-2">
                    <div className="flex items-center gap-1.5 truncate text-sm font-medium text-slate-200">
                      <span>{c.user}</span>
                      {c.campaign_size > 1 && (
                        <span className="text-[10px] text-rose-300 bg-rose-500/15 border border-rose-500/30 px-1 rounded">
                          campaign of {c.campaign_size}
                        </span>
                      )}
                    </div>
                    <div className="truncate text-xs text-slate-400 mt-0.5">{c.headline}</div>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <Band band={c.band} score={c.score} />
                    {c.pending_approvals > 0 && (
                      <span className="text-[10px] font-semibold text-amber-300 bg-amber-400/10 px-1.5 py-0.5 rounded border border-amber-400/30">
                        {c.pending_approvals} to approve
                      </span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* Top Suspicious Users */}
        <Card
          title="Top Suspicious Users"
          right={
            <Link
              to="/investigate"
              className="text-xs font-medium text-sky-400 hover:text-sky-300 transition"
            >
              View all →
            </Link>
          }
        >
          {!o.top_users || o.top_users.length === 0 ? (
            <Empty>No flagged user activity.</Empty>
          ) : (
            <ul className="divide-y divide-ink-600/50 max-h-72 overflow-y-auto pr-1">
              {o.top_users.map((c) => (
                <li
                  key={c.id}
                  onClick={() => navigate(`/investigate/${c.id}`)}
                  className="flex items-center justify-between py-2.5 px-1 hover:bg-ink-700/40 rounded-lg cursor-pointer transition"
                >
                  <div className="min-w-0 pr-2">
                    <div className="truncate text-sm font-medium text-slate-200 hover:text-sky-300">
                      {c.user}
                    </div>
                    <div className="truncate text-xs text-slate-500 mt-0.5">
                      Case #{c.id} · {c.headline}
                    </div>
                  </div>
                  <Band band={c.band} score={c.score} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* Recent Security Alerts Table */}
      <Card
        title="Recent Security Alerts"
        right={
          <span className="text-xs text-slate-400">
            {o.recent_alerts?.length || 0} latest cases
          </span>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="border-b border-ink-600/60 bg-ink-900/40">
              <tr>
                <th className="th">User</th>
                <th className="th">What We Found</th>
                <th className="th">Risk Band</th>
                <th className="th">Status</th>
                <th className="th text-right">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-600/40">
              {o.recent_alerts?.length === 0 ? (
                <tr>
                  <td colSpan={5} className="td text-center text-slate-500 py-6">
                    No recent security alerts.
                  </td>
                </tr>
              ) : (
                o.recent_alerts.map((c) => (
                  <tr
                    key={c.id}
                    onClick={() => navigate(`/investigate/${c.id}`)}
                    className="hover:bg-ink-700/40 cursor-pointer transition"
                  >
                    <td className="td font-medium text-sky-300 hover:underline">
                      {c.user}
                    </td>
                    <td className="td text-slate-300 max-w-md truncate">
                      {c.headline}
                      {c.campaign_size > 1 && (
                        <span className="ml-1.5 text-xs text-slate-500">
                          (campaign of {c.campaign_size})
                        </span>
                      )}
                    </td>
                    <td className="td">
                      <Band band={c.band} score={c.score} />
                    </td>
                    <td className="td">
                      <span className="capitalize text-slate-400 text-xs">
                        {c.status.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="td text-right text-xs text-slate-500">
                      {when(c.updated_at)}
                    </td>
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
