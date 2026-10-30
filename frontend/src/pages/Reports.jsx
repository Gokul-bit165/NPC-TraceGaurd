import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  BarChart3,
  Bell,
  Calendar,
  CheckCircle2,
  ChevronRight,
  Download,
  ExternalLink,
  FileSpreadsheet,
  Info,
  Mail,
  Shield,
  ShieldAlert,
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
import { useChartTheme, SERIES } from '../theme.jsx'
import { exportToCsv } from '../utils/exportUtils.js'
import CampaignModal from '../components/CampaignModal.jsx'
import DailySummaryModal from '../components/DailySummaryModal.jsx'

const DEFAULT_SERIES = {
  critical: '#E11D48',
  high: '#F97316',
  medium: '#F59E0B',
  low: '#10B981',
}

export default function Reports() {
  const ct = useChartTheme()
  const [days, setDays] = useState(30)
  const [selectedCampaign, setSelectedCampaign] = useState(null)
  const [campaignCases, setCampaignCases] = useState([])
  const [loadingCampaignCases, setLoadingCampaignCases] = useState(false)
  const [activeCampaignKey, setActiveCampaignKey] = useState(null)
  const [showDailySummary, setShowDailySummary] = useState(false)

  // Safe color resolution with fallbacks for critical, high, medium, low
  const chartColors = {
    critical: ct?.colors?.critical || SERIES?.critical || DEFAULT_SERIES.critical,
    high: ct?.colors?.high || SERIES?.high || DEFAULT_SERIES.high,
    medium: ct?.colors?.medium || SERIES?.medium || DEFAULT_SERIES.medium,
    low: ct?.colors?.low || SERIES?.low || DEFAULT_SERIES.low,
  }

  // Fetch reports data
  const { data: r, error, loading, reload } = useApi(
    (signal) => api.get('/reports', { params: { days }, signal }),
    [days]
  )

  // Fetch campaigns data
  const { data: camps, reload: reloadCampaigns } = useApi(() => api.get('/campaigns'))

  // Safe normalization of datasets
  const campsList = camps || []

  const trendData = (r?.trend || []).map((item) => ({
    day: item?.day || '',
    critical: Number(item?.critical) || 0,
    high: Number(item?.high) || 0,
    medium: Number(item?.medium) || 0,
    low: Number(item?.low) || 0,
  }))

  const topUsers = (r?.top_users || r?.risky_users || []).map((u) => ({
    email:
      u?.email ||
      (u?.user_id
        ? u.user_id.includes('@')
          ? u.user_id
          : `${u.user_id}@traceguard.internal`
        : 'unknown@traceguard.internal'),
    name: u?.name || u?.user || u?.user_id || 'Unknown User',
    department: u?.department || u?.dept || 'General Campus',
    open_cases: u?.open_cases ?? u?.cases ?? 0,
    max_score: u?.max_score ?? 0,
  }))

  const signals = (r?.signals || []).map((s) => ({
    signal: s?.signal || s?.label || s?.code || 'Unknown Signal',
    count: s?.count ?? s?.cases ?? 0,
    cases: s?.cases ?? s?.count ?? 0,
  }))

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
    if (!trendData.length) return
    const cols = [
      { key: 'day', label: 'Day' },
      { key: 'critical', label: 'Critical' },
      { key: 'high', label: 'High' },
      { key: 'medium', label: 'Medium' },
      { key: 'low', label: 'Low' },
    ]
    exportToCsv(trendData, `traceguard-risk-trend-${days}d.csv`, cols)
  }

  const exportCampaigns = () => {
    if (!campsList.length) return
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
    exportToCsv(campsList, `traceguard-phishing-campaigns.csv`, cols)
  }

  const exportSignals = () => {
    if (!signals.length) return
    const cols = [
      { key: 'signal', label: 'Risk Signal' },
      { key: 'count', label: 'Trigger Frequency' },
      { key: 'cases', label: 'Incident Cases Involved' },
    ]
    exportToCsv(signals, `traceguard-signal-frequencies.csv`, cols)
  }

  const exportHighRiskUsers = () => {
    if (!topUsers.length) return
    const cols = [
      { key: 'email', label: 'User Email' },
      { key: 'name', label: 'User Full Name' },
      { key: 'department', label: 'Department' },
      { key: 'open_cases', label: 'Active Incidents' },
      { key: 'max_score', label: 'Max Observed Score' },
    ]
    exportToCsv(topUsers, `traceguard-highest-risk-users.csv`, cols)
  }

  if (loading && !r) return <Spinner message="Aggregating telemetry & audit metrics…" />
  if (error && !r) return <ErrorBox error={error} onRetry={reload} />
  if (!r) return null

  const fp = r.verdicts || { true_positive: 0, false_positive: 0 }
  const totalVerdicts = (fp.true_positive || 0) + (fp.false_positive || 0)
  const fpRate = totalVerdicts > 0 ? Math.round((fp.false_positive / totalVerdicts) * 100) : 0

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="Reports and Analytics"
        subtitle="Institutional threat metrics, telemetry trends, phishing campaigns, user risk distributions, and analyst feedback calibrations."
        breadcrumbs={[
          { label: 'Overview', to: '/' },
          { label: 'Reports & Analytics' },
        ]}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <DateRangePicker
              value={days}
              onChange={setDays}
              options={[
                { value: 7, label: 'Past 7 Days' },
                { value: 14, label: 'Past 14 Days' },
                { value: 30, label: 'Past 30 Days' },
                { value: 90, label: 'Past Quarter' },
              ]}
            />
            <button
              type="button"
              onClick={() => setShowDailySummary(true)}
              className="btn btn-ghost text-sky-400 hover:text-white"
              title="View daily analyst summaries and notification alerts"
            >
              <Bell size={15} />
              <span>Analyst Digest</span>
            </button>
            <button
              type="button"
              onClick={exportTrend}
              className="btn btn-ghost text-xs"
              title="Export trend series to CSV"
            >
              <Download size={14} />
              <span>Export Trend</span>
            </button>
          </div>
        }
      />

      {/* Row 1: Trend and Analyst Feedback */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Risk Trend Chart */}
        <Card
          title={`Incident Detection Trend (${days} Days)`}
          className="lg:col-span-2"
          right={
            <span className="text-xs text-slate-400">
              Aggregated by risk band classification
            </span>
          }
        >
          {trendData.length === 0 ? (
            <Empty>No historical incident records in selected timeframe.</Empty>
          ) : (
            <div className="pt-2">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={trendData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid stroke={ct.grid} strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="day"
                    stroke={ct.text}
                    fontSize={11}
                    tickLine={false}
                  />
                  <YAxis
                    stroke={ct.text}
                    fontSize={11}
                    allowDecimals={false}
                    tickLine={false}
                    axisLine={false}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: ct.tooltipBg,
                      borderColor: ct.tooltipBorder,
                      borderRadius: 8,
                      fontSize: 12,
                      color: ct.tooltipText,
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
                  <Bar
                    dataKey="critical"
                    name="Critical"
                    stackId="a"
                    fill={chartColors.critical}
                    radius={[0, 0, 0, 0]}
                  />
                  <Bar
                    dataKey="high"
                    name="High"
                    stackId="a"
                    fill={chartColors.high}
                  />
                  <Bar
                    dataKey="medium"
                    name="Medium"
                    stackId="a"
                    fill={chartColors.medium}
                  />
                  <Bar
                    dataKey="low"
                    name="Low"
                    stackId="a"
                    fill={chartColors.low}
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        {/* Analyst Precision & Feedback Calibration */}
        <Card
          title="Analyst Calibration"
          right={<span className="text-xs text-slate-400">Signal accuracy</span>}
        >
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 text-center">
              <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3.5">
                <div className="flex items-center justify-center gap-1.5 text-rose-400 mb-1">
                  <ThumbsDown size={14} />
                  <span className="text-xs font-semibold uppercase">Real Threats</span>
                </div>
                <div className="text-3xl font-extrabold text-rose-300">
                  {fp.true_positive}
                </div>
                <div className="text-[11px] text-slate-400 mt-1">Confirmed True Positives</div>
              </div>

              <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3.5">
                <div className="flex items-center justify-center gap-1.5 text-emerald-400 mb-1">
                  <ThumbsUp size={14} />
                  <span className="text-xs font-semibold uppercase">False Alarms</span>
                </div>
                <div className="text-3xl font-extrabold text-emerald-300">
                  {fp.false_positive}
                </div>
                <div className="text-[11px] text-slate-400 mt-1">Analyst Reclassified</div>
              </div>
            </div>

            {/* Rate gauge bar */}
            <div className="rounded-xl border border-ink-600/60 bg-ink-900/60 p-4 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400 font-medium">Model Precision Rate</span>
                <span className="font-mono font-bold text-slate-200">
                  {totalVerdicts > 0 ? `${100 - fpRate}%` : 'N/A'}
                </span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-ink-700">
                <div
                  className="h-full bg-gradient-to-r from-emerald-500 to-teal-400 transition-all duration-500"
                  style={{ width: `${totalVerdicts > 0 ? 100 - fpRate : 0}%` }}
                />
              </div>
              <div className="flex justify-between text-[11px] text-slate-400">
                <span>{fp.true_positive} Confirmed</span>
                <span className="text-amber-400/90">{fpRate}% False Alarm Rate</span>
              </div>
            </div>

            <div className="text-xs text-slate-400 leading-relaxed">
              {totalVerdicts > 0 ? (
                <>
                  Analysts reviewed <span className="text-slate-200 font-semibold">{totalVerdicts}</span> closed incidents. Feedback fine-tunes risk signal weights and suppresses noisy patterns.
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
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">Click to view details or batch act</span>
              <button
                onClick={exportCampaigns}
                className="text-xs text-sky-400 hover:underline inline-flex items-center gap-1"
              >
                <Download size={13} />
                <span>Export</span>
              </button>
            </div>
          }
        >
          {!campsList.length ? (
            <Empty>No active phishing campaigns identified.</Empty>
          ) : (
            <div className="overflow-x-auto max-h-80 overflow-y-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-ink-600/60 bg-ink-900/50 sticky top-0">
                  <tr>
                    <th className="th !whitespace-normal">Campaign Subject & Sender</th>
                    <th className="th w-[96px] text-center">Recipients</th>
                    <th className="th w-[148px] text-right">Max Risk</th>
                    <th className="th text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-600/40">
                  {campsList.map((c) => (
                    <tr
                      key={c.key}
                      onClick={() => openCampaignDetail(c)}
                      className="hover:bg-ink-700/40 cursor-pointer transition"
                    >
                      <td className="td w-full max-w-0">
                        <div className="font-semibold text-slate-200 hover:text-sky-300 flex items-center gap-1 min-w-0">
                          <span className="truncate" title={c.subject}>{c.subject}</span>
                          <ChevronRight size={13} className="shrink-0 text-slate-500" />
                        </div>
                        <div className="text-[11px] text-slate-400 font-mono mt-0.5 truncate">
                          {c.sender} · {when(c.first_seen)}
                        </div>
                      </td>
                      <td className="td w-[96px] whitespace-nowrap text-center">
                        <span className="font-bold text-slate-100 text-sm">
                          {c.recipients}
                        </span>
                        <div className="text-[10px] text-amber-300">
                          {c.open_cases} open
                        </div>
                      </td>
                      <td className="td w-[148px] whitespace-nowrap text-right">
                        <RiskBadge score={c.max_email_score} aligned />
                      </td>
                      <td className="td text-right">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            setActiveCampaignKey(c.key)
                          }}
                          className="btn btn-ghost !px-2.5 !py-1 text-xs text-sky-400 hover:text-white"
                          title="Trigger batch campaign actions"
                        >
                          <ShieldAlert size={13} />
                          Act
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Signals Frequency */}
        <Card
          title="Risk Signals Trigger Frequency"
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
          {!signals.length ? (
            <Empty>No signal triggers logged in this window.</Empty>
          ) : (
            <div className="overflow-x-auto max-h-80 overflow-y-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-ink-600/60 bg-ink-900/50 sticky top-0">
                  <tr>
                    <th className="th">Engine Signal Name</th>
                    <th className="th text-center">Trigger Count</th>
                    <th className="th text-right">Incident Cases</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-600/40">
                  {signals.map((s, idx) => (
                    <tr key={idx} className="hover:bg-ink-700/20">
                      <td className="td font-mono font-medium text-slate-200">
                        {s.signal}
                      </td>
                      <td className="td text-center">
                        <span className="rounded bg-sky-500/10 px-2 py-0.5 font-mono text-sky-300 font-bold">
                          {s.count}
                        </span>
                      </td>
                      <td className="td text-right text-slate-400 font-mono">
                        {s.cases}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {/* Row 3: Highest-Risk User Accounts */}
      <Card
        title="Institutional High-Risk User Accounts"
        right={
          <button
            onClick={exportHighRiskUsers}
            className="text-xs text-sky-400 hover:underline inline-flex items-center gap-1"
          >
            <Download size={13} />
            <span>Export</span>
          </button>
        }
      >
        {!topUsers.length ? (
          <Empty>No elevated user accounts detected.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-ink-600/60 bg-ink-900/50">
                <tr>
                  <th className="th">User Account & Identity</th>
                  <th className="th">Department / Unit</th>
                  <th className="th text-center">Open Incidents</th>
                  <th className="th text-right">Max Risk Level</th>
                  <th className="th text-right">Investigation Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-600/40">
                {topUsers.map((u, idx) => (
                  <tr key={u.email || idx} className="hover:bg-ink-700/30">
                    <td className="td">
                      <div className="font-semibold text-slate-100">{u.name}</div>
                      <div className="text-[11px] font-mono text-slate-400">{u.email}</div>
                    </td>
                    <td className="td text-slate-300">
                      {u.department || 'General Campus'}
                    </td>
                    <td className="td text-center">
                      <span className="rounded-full bg-rose-500/10 px-2.5 py-0.5 font-mono font-bold text-rose-300">
                        {u.open_cases}
                      </span>
                    </td>
                    <td className="td text-right">
                      <RiskBadge score={u.max_score} size="xs" />
                    </td>
                    <td className="td text-right">
                      <Link
                        to={`/investigate?user=${encodeURIComponent(u.email)}`}
                        className="btn btn-ghost text-xs text-sky-400 hover:text-white"
                      >
                        <span>Investigate</span>
                        <ChevronRight size={13} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Row 4: Recent Analyst Investigation Audits */}
      <Card
        title="Analyst Workflow Audit Activity"
        right={<span className="text-xs text-slate-400">Last 20 operational actions</span>}
      >
        {!r.history?.length ? (
          <Empty>No investigation audit logs recorded yet.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-ink-600/60 bg-ink-900/50">
                <tr>
                  <th className="th w-40">Timestamp (UTC)</th>
                  <th className="th w-44">Analyst Actor</th>
                  <th className="th w-36">Action Event</th>
                  <th className="th w-28">Case Reference</th>
                  <th className="th">Event Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-600/40">
                {r.history.map((h, idx) => (
                  <tr key={idx} className="hover:bg-ink-700/30">
                    <td className="td font-mono text-slate-400">{when(h.ts)}</td>
                    <td className="td">
                      <div className="font-semibold text-slate-200">{h.actor}</div>
                      <div className="text-[10px] text-slate-500 capitalize">{h.role}</div>
                    </td>
                    <td className="td">
                      <span className="rounded bg-ink-700/80 px-2 py-0.5 text-[11px] font-medium text-slate-300 capitalize">
                        {h.event?.replaceAll('_', ' ')}
                      </span>
                    </td>
                    <td className="td">
                      {h.case_id ? (
                        <Link
                          to={`/investigate/${h.case_id}`}
                          className="font-mono text-sky-400 hover:underline"
                        >
                          #{h.case_id}
                        </Link>
                      ) : (
                        <span className="text-slate-500">—</span>
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
        )}
      </Card>

      {/* Campaign action modal */}
      {activeCampaignKey && (
        <CampaignModal
          campaignKey={activeCampaignKey}
          onClose={() => setActiveCampaignKey(null)}
          onSuccess={() => {
            reloadCampaigns()
            reload()
          }}
        />
      )}

      {/* Daily Summary Modal */}
      {showDailySummary && (
        <DailySummaryModal
          onClose={() => setShowDailySummary(false)}
        />
      )}

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

            <footer className="flex items-center justify-between border-t border-ink-600/60 bg-ink-900/50 px-5 py-3 rounded-b-xl">
              <button
                type="button"
                className="btn btn-primary text-xs"
                onClick={() => {
                  const key = selectedCampaign.key
                  setSelectedCampaign(null)
                  setActiveCampaignKey(key)
                }}
              >
                <ShieldAlert size={14} />
                <span>Batch Remediate Campaign</span>
              </button>
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
