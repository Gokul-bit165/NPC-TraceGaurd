import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  BarChart3,
  Calendar,
  CheckCircle2,
  ChevronRight,
  Download,
  ExternalLink,
  FileSpreadsheet,
  Info,
  Mail,
  Shield,
  ThumbsDown,
  ThumbsUp,
  Users,
  X,
} from 'lucide-react'
import {
  Bar,
  BarChart,
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
  Chip,
  DateRangePicker,
  Empty,
  ErrorBox,
  PageHeader,
  RiskBadge,
  Spinner,
  when,
} from '../ui.jsx'
import { useApi } from '../hooks/useApi.js'
import { useChartTheme } from '../theme.jsx'
import { exportToCsv } from '../utils/exportUtils.js'

export default function Reports() {
  const ct = useChartTheme()
  const [days, setDays] = useState(30)
  const [selectedCampaign, setSelectedCampaign] = useState(null)
  const [campaignCases, setCampaignCases] = useState([])
  const [loadingCampaignCases, setLoadingCampaignCases] = useState(false)

  // Fetch reports data
  const { data: r, error, loading, reload } = useApi(
    (signal) => api.get('/reports', { params: { days }, signal }),
    [days]
  )

  // Fetch campaigns data
  const { data: camps } = useApi(() => api.get('/campaigns'))

  // Open Campaign Detail View modal
  const openCampaignDetail = async (camp) => {
    setSelectedCampaign(camp)
    setLoadingCampaignCases(true)
    try {
      // Find cases matching this campaign
      const res = await api.get('/cases', { params: { limit: 100 } })
      const matching = (res.data?.items || []).filter(
        (c) => c.scenario === camp.key || (camp.subject && c.headline?.includes(camp.subject))
      )
      setCampaignCases(matching)
    } catch {
      setCampaignCases([])
    } finally {
      setLoadingCampaignCases(false)
    }
  }

  // Export handlers
  const exportTrend = () => {
    if (!r?.trend?.length) return
    const cols = [
      { key: 'day', label: 'Day' },
      { key: 'critical', label: 'Critical' },
      { key: 'high', label: 'High' },
      { key: 'medium', label: 'Medium' },
      { key: 'low', label: 'Low' },
    ]
    exportToCsv(r.trend, `traceguard-risk-trend-${days}d.csv`, cols)
  }

  const exportCampaigns = () => {
    if (!camps?.length) return
    const cols = [
      { key: 'key', label: 'Campaign Key' },
      { key: 'subject', label: 'Email Subject' },
      { key: 'sender', label: 'Sender' },
      { key: 'recipients', label: 'Recipients Count' },
      { key: 'open_cases', label: 'Open Cases' },
      { key: 'max_email_score', label: 'Max Email Risk Score' },
      { key: 'first_seen', label: 'First Detected' },
      { key: 'last_seen', label: 'Last Detected' },
    ]
    exportToCsv(camps, `traceguard-phishing-campaigns.csv`, cols)
  }

  const exportSignals = () => {
    if (!r?.signals?.length) return
    const cols = [
      { key: 'code', label: 'Signal Code' },
      { key: 'label', label: 'Description' },
      { key: 'cases', label: 'Total Triggered Cases' },
      { key: 'false_positive_cases', label: 'False Alarms Count' },
      {
        key: 'fp_rate',
        label: 'False Alarm Rate',
        formatter: (_, row) =>
          row.cases < 10
            ? 'Insufficient Sample Size'
            : `${((row.false_positive_cases / row.cases) * 100).toFixed(1)}%`,
      },
    ]
    exportToCsv(r.signals, `traceguard-signal-frequency.csv`, cols)
  }

  const exportUsers = () => {
    if (!r?.risky_users?.length) return
    const cols = [
      { key: 'user', label: 'User Name' },
      { key: 'user_id', label: 'User ID' },
      { key: 'dept', label: 'Department' },
      { key: 'max_score', label: 'Highest Risk Score' },
      { key: 'cases', label: 'Total Incidents' },
    ]
    exportToCsv(r.risky_users, `traceguard-risky-users.csv`, cols)
  }

  const exportDepartments = () => {
    if (!r?.departments?.length) return
    const cols = [
      { key: 'dept', label: 'Department' },
      { key: 'cases', label: 'Total Cases' },
      { key: 'high_or_critical', label: 'High or Critical Cases' },
    ]
    exportToCsv(r.departments, `traceguard-department-risk.csv`, cols)
  }

  const exportHistory = () => {
    if (!r?.history?.length) return
    const cols = [
      { key: 'ts', label: 'Timestamp (UTC)' },
      { key: 'actor', label: 'Actor' },
      { key: 'role', label: 'Role' },
      { key: 'event', label: 'Event' },
      { key: 'case_id', label: 'Case ID' },
      { key: 'detail', label: 'Details', formatter: (v) => (typeof v === 'object' ? JSON.stringify(v) : v) },
    ]
    exportToCsv(r.history, `traceguard-audit-history.csv`, cols)
  }

  if (loading && !r) return <Spinner message="Generating security analytics report…" />
  if (error && !r) return <ErrorBox error={error} onRetry={reload} />
  if (!r) return <Empty>No report data available.</Empty>

  const fp = r?.verdicts || { true_positive: 0, false_positive: 0 }
  const totalVerdicts = fp.true_positive + fp.false_positive

  // Sort signals by false alarm rate
  const signalsSortedByFp = [...(r?.signals || [])].sort((a, b) => {
    const rateA = a.cases > 0 ? a.false_positive_cases / a.cases : 0
    const rateB = b.cases > 0 ? b.false_positive_cases / b.cases : 0
    return rateB - rateA
  })

  return (
    <div className="space-y-6">
      <PageHeader
        title="Reports & Threat Analytics"
        description="Comprehensive intelligence on organizational risk posture, phishing campaign propagation, signal accuracy validation, and historical audit entries."
        right={
          <DateRangePicker
            days={days}
            onChangeDays={(d) => setDays(d)}
            presets={[
              { label: '7d', value: 7 },
              { label: '14d', value: 14 },
              { label: '30d', value: 30 },
              { label: '90d', value: 90 },
              { label: '365d', value: 365 },
            ]}
          />
        }
      />

      {/* Row 1: New cases by band & Analyst feedback */}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card
          title={`New Incidents by Risk Band (${days} Days)`}
          right={
            <button
              onClick={exportTrend}
              className="text-xs text-sky-400 hover:underline inline-flex items-center gap-1"
            >
              <Download size={13} />
              <span>Export</span>
            </button>
          }
          className="lg:col-span-2"
        >
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={r.trend || []} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid stroke={ct.grid} strokeDasharray="3 3" />
                <XAxis dataKey="day" {...ct.axis} />
                <YAxis {...ct.axis} allowDecimals={false} />
                <Tooltip {...ct.tooltip} />
                <Legend {...ct.legend} />
                <Bar dataKey="critical" name="Critical" stackId="a" fill="#f43f5e" />
                <Bar dataKey="high" name="High" stackId="a" fill="#f97316" />
                <Bar dataKey="medium" name="Medium" stackId="a" fill="#fbbf24" />
                <Bar dataKey="low" name="Low" stackId="a" fill="#34d399" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Analyst Triage Feedback">
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 text-center">
              <div className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-3.5">
                <div className="flex justify-center text-rose-400 mb-1">
                  <ThumbsDown size={18} />
                </div>
                <div className="text-3xl font-bold text-rose-300">{fp.true_positive}</div>
                <div className="text-[11px] uppercase font-semibold text-slate-400 mt-1">
                  Real Threats
                </div>
              </div>

              <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-3.5">
                <div className="flex justify-center text-emerald-400 mb-1">
                  <ThumbsUp size={18} />
                </div>
                <div className="text-3xl font-bold text-emerald-300">{fp.false_positive}</div>
                <div className="text-[11px] uppercase font-semibold text-slate-400 mt-1">
                  False Alarms
                </div>
              </div>
            </div>

            <div className="rounded-lg bg-ink-900/70 p-3 text-xs text-slate-400 leading-relaxed border border-ink-600/40">
              {totalVerdicts > 0 ? (
                <>
                  <span className="text-slate-200 font-semibold">{totalVerdicts}</span> incidents have been verified by security analysts. True positive confirmation rate is{' '}
                  <span className="text-rose-300 font-semibold">
                    {((fp.true_positive / totalVerdicts) * 100).toFixed(1)}%
                  </span>.
                </>
              ) : (
                'Mark cases on the Incident Response page to calibrate model false-alarm distributions.'
              )}
            </div>
          </div>
        </Card>
      </div>

      {/* Row 2: Phishing Campaigns & Signals Frequency */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Phishing campaigns */}
        <Card
          title="Phishing Campaigns (Identical Message Multi-Target)"
          right={
            <button
              onClick={exportCampaigns}
              className="text-xs text-sky-400 hover:underline inline-flex items-center gap-1"
            >
              <Download size={13} />
              <span>Export</span>
            </button>
          }
        >
          {!camps?.length ? (
            <Empty>No active phishing campaigns identified.</Empty>
          ) : (
            <div className="overflow-x-auto max-h-80 overflow-y-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-ink-600/60 bg-ink-900/50 sticky top-0">
                  <tr>
                    <th className="th">Campaign Subject & Sender</th>
                    <th className="th text-center">Recipients</th>
                    <th className="th text-right">Max Risk</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-600/40">
                  {camps.map((c) => (
                    <tr
                      key={c.key}
                      onClick={() => openCampaignDetail(c)}
                      className="hover:bg-ink-700/40 cursor-pointer transition"
                    >
                      <td className="td">
                        <div className="font-semibold text-slate-200 hover:text-sky-300 flex items-center gap-1">
                          <span>{c.subject}</span>
                          <ChevronRight size={13} className="text-slate-500" />
                        </div>
                        <div className="text-[11px] text-slate-400 font-mono mt-0.5">
                          {c.sender} · {when(c.first_seen)}
                        </div>
                      </td>
                      <td className="td text-center">
                        <span className="font-bold text-slate-100 text-sm">
                          {c.recipients}
                        </span>
                        <div className="text-[10px] text-amber-300">
                          {c.open_cases} open
                        </div>
                      </td>
                      <td className="td text-right">
                        <RiskBadge score={c.max_email_score} size="xs" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Signals Most Often Wrong */}
        <Card
          title="Signals Evaluated & False Alarm Frequency"
          right={
            <button
              onClick={exportSignals}
              className="text-xs text-sky-400 hover:underline inline-flex items-center gap-1"
            >
              <Download size={13} />
              <span>Export</span>
            </button>
          }
        >
          <div className="overflow-x-auto max-h-80 overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-ink-600/60 bg-ink-900/50 sticky top-0">
                <tr>
                  <th className="th">Signal Code</th>
                  <th className="th text-center">Total Cases</th>
                  <th className="th text-center">In False Alarms</th>
                  <th className="th text-right">False Alarm Rate</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-600/40">
                {signalsSortedByFp.map((s) => {
                  const hasSufficientSample = s.cases >= 10
                  const rate = s.cases > 0 ? (s.false_positive_cases / s.cases) * 100 : 0

                  return (
                    <tr key={s.code} className="hover:bg-ink-700/20">
                      <td className="td">
                        <div className="font-medium text-slate-200">{s.label}</div>
                        <div className="font-mono text-[10px] text-sky-300">{s.code}</div>
                      </td>
                      <td className="td text-center font-semibold text-slate-100">
                        {s.cases}
                      </td>
                      <td className="td text-center text-slate-300">
                        {s.false_positive_cases}
                      </td>
                      <td className="td text-right">
                        {hasSufficientSample ? (
                          <span
                            className={`font-semibold font-mono ${
                              rate > 25 ? 'text-amber-400' : 'text-slate-300'
                            }`}
                          >
                            {rate.toFixed(1)}%
                          </span>
                        ) : (
                          <span
                            className="rounded bg-ink-700/80 px-1.5 py-0.5 text-[10px] text-slate-400 italic"
                            title={`Sample size is only ${s.cases} (requires ≥ 10 for statistical significance)`}
                          >
                            Insufficient sample size
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[10px] text-slate-500 italic">
            * Note: Percentages require a minimum sample of 10 cases to prevent premature rule tuning on small cohorts.
          </p>
        </Card>
      </div>

      {/* Row 3: User Risk & Department Risk */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card
          title="User Risk Posture"
          right={
            <button
              onClick={exportUsers}
              className="text-xs text-sky-400 hover:underline inline-flex items-center gap-1"
            >
              <Download size={13} />
              <span>Export</span>
            </button>
          }
        >
          <div className="overflow-x-auto max-h-72 overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-ink-600/60 bg-ink-900/50 sticky top-0">
                <tr>
                  <th className="th">User</th>
                  <th className="th">Department</th>
                  <th className="th text-right">Max Score</th>
                  <th className="th text-center">Incidents</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-600/40">
                {r.risky_users?.map((u) => (
                  <tr key={u.user_id} className="hover:bg-ink-700/30">
                    <td className="td font-semibold text-slate-200">
                      {u.user}
                    </td>
                    <td className="td text-slate-400">
                      {u.dept || 'Unknown'}
                    </td>
                    <td className="td text-right">
                      <RiskBadge score={u.max_score} size="xs" />
                    </td>
                    <td className="td text-center text-slate-300 font-semibold">
                      {u.cases}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card
          title="Department-Level Risk Distribution"
          right={
            <button
              onClick={exportDepartments}
              className="text-xs text-sky-400 hover:underline inline-flex items-center gap-1"
            >
              <Download size={13} />
              <span>Export</span>
            </button>
          }
        >
          <div className="overflow-x-auto max-h-72 overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-ink-600/60 bg-ink-900/50 sticky top-0">
                <tr>
                  <th className="th">Department</th>
                  <th className="th text-center">Total Cases</th>
                  <th className="th text-right">High / Critical</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-600/40">
                {r.departments?.map((d) => (
                  <tr key={d.dept} className="hover:bg-ink-700/30">
                    <td className="td font-semibold text-slate-200">
                      {d.dept}
                    </td>
                    <td className="td text-center text-slate-300 font-semibold">
                      {d.cases}
                    </td>
                    <td className="td text-right">
                      <span
                        className={`font-bold ${
                          d.high_or_critical > 0 ? 'text-rose-400' : 'text-slate-400'
                        }`}
                      >
                        {d.high_or_critical}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {/* Row 4: Historical Investigation Audit Log */}
      <Card
        title="Historical Investigation Activity Log"
        right={
          <button
            onClick={exportHistory}
            className="text-xs text-sky-400 hover:underline inline-flex items-center gap-1"
          >
            <Download size={13} />
            <span>Export CSV</span>
          </button>
        }
      >
        <div className="overflow-x-auto max-h-80 overflow-y-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-ink-600/60 bg-ink-900/50 sticky top-0">
              <tr>
                <th className="th w-40">Timestamp (UTC)</th>
                <th className="th w-44">Actor</th>
                <th className="th w-36">Action</th>
                <th className="th w-24">Incident</th>
                <th className="th">Telemetry Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-600/40">
              {r.history?.map((h, i) => (
                <tr key={i} className="hover:bg-ink-700/30">
                  <td className="td font-mono text-slate-400">
                    {when(h.ts)}
                  </td>
                  <td className="td">
                    <span className="text-slate-200 font-medium">{h.actor}</span>
                    <span className="text-[10px] text-slate-500 font-mono ml-1">
                      ({h.role})
                    </span>
                  </td>
                  <td className="td">
                    <span className="rounded bg-ink-700 px-1.5 py-0.5 text-[11px] capitalize text-slate-300">
                      {h.event.replaceAll('_', ' ')}
                    </span>
                  </td>
                  <td className="td">
                    {h.case_id ? (
                      <Link
                        to={`/investigate/${h.case_id}`}
                        className="text-sky-400 hover:underline font-mono"
                      >
                        #{h.case_id}
                      </Link>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                  <td className="td font-mono text-[11px] text-slate-400 truncate max-w-xs">
                    {typeof h.detail === 'object' ? JSON.stringify(h.detail) : h.detail}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Campaign Detail Modal */}
      {selectedCampaign && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="card w-full max-w-2xl border border-ink-600 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
            <header className="flex items-center justify-between border-b border-ink-600/60 px-5 py-4">
              <div className="flex items-center gap-2">
                <Mail className="text-sky-400" size={18} />
                <h3 className="text-base font-bold text-slate-100">
                  Phishing Campaign Detail
                </h3>
              </div>
              <button
                onClick={() => setSelectedCampaign(null)}
                className="text-slate-400 hover:text-slate-100 transition"
              >
                <X size={18} />
              </button>
            </header>

            <div className="p-5 space-y-4">
              <div className="rounded-xl border border-ink-600/70 bg-ink-900 p-4 space-y-2">
                <div className="text-xs uppercase font-semibold text-slate-500">
                  Campaign Subject
                </div>
                <div className="text-base font-semibold text-slate-100">
                  {selectedCampaign.subject}
                </div>
                <div className="text-xs text-slate-400 font-mono">
                  Sender: {selectedCampaign.sender}
                </div>
                <div className="flex flex-wrap gap-2 pt-1 text-xs">
                  <Chip tone="rose">
                    {selectedCampaign.recipients} Known Recipients
                  </Chip>
                  <RiskBadge score={selectedCampaign.max_email_score} size="xs" />
                  <span className="text-slate-400 self-center">
                    First seen: {when(selectedCampaign.first_seen)}
                  </span>
                </div>
              </div>

              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                  Correlated User Cases & Status
                </h4>
                {loadingCampaignCases ? (
                  <Spinner message="Retrieving campaign cases…" />
                ) : campaignCases.length === 0 ? (
                  <p className="text-xs text-slate-500 p-4 text-center rounded-lg border border-ink-600/40 bg-ink-900/40">
                    No individual cases opened yet for this campaign cluster.
                  </p>
                ) : (
                  <div className="max-h-56 overflow-y-auto rounded-lg border border-ink-600/60 bg-ink-900/40">
                    <table className="w-full text-left text-xs">
                      <tbody className="divide-y divide-ink-600/40">
                        {campaignCases.map((cc) => (
                          <tr key={cc.id} className="hover:bg-ink-700/30">
                            <td className="td font-medium text-slate-200">
                              <Link
                                to={`/investigate/${cc.id}`}
                                className="text-sky-300 hover:underline"
                              >
                                {cc.user.name}
                              </Link>
                            </td>
                            <td className="td text-slate-400 capitalize">
                              {cc.status.replace('_', ' ')}
                            </td>
                            <td className="td text-right">
                              <RiskBadge band={cc.band} score={cc.score} size="xs" />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>

            <footer className="flex items-center justify-end border-t border-ink-600/60 bg-ink-900/50 px-5 py-3 rounded-b-xl">
              <button
                type="button"
                className="btn btn-ghost text-xs"
                onClick={() => setSelectedCampaign(null)}
              >
                Close
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  )
}
