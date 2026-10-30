import React, { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Download,
  Filter,
  Globe,
  Info,
  KeyRound,
  Laptop,
  Lock,
  RotateCcw,
  Search,
  ShieldAlert,
  User,
  X,
  FlaskConical,
} from 'lucide-react'
import api from '../api.js'
import SimulateLogins from '../components/SimulateLogins.jsx'
import {
  Band,
  Card,
  Chip,
  DataTable,
  Empty,
  ErrorBox,
  PageHeader,
  Pagination,
  RiskBadge,
  Spinner,
  when,
} from '../ui.jsx'
import { useApi } from '../hooks/useApi.js'
import { exportToCsv } from '../utils/exportUtils.js'
import { formatLocation, formatDate } from '../utils/formatters.js'

export default function Logins() {
  const [filters, setFilters] = useState({
    q: '',
    country: '',
    device: '',
    risk: '',
    success: '',
    start: '',
    end: '',
    unusual_only: false,
  })
  const [page, setPage] = useState(0)
  const [selectedLogin, setSelectedLogin] = useState(null)
  // Keeps the last selection mounted while the pane slides closed, so content does not vanish mid-animation.
  const [panelRow, setPanelRow] = useState(null)
  useEffect(() => { if (selectedLogin) setPanelRow(selectedLogin) }, [selectedLogin])
  const [clientSort, setClientSort] = useState({ key: 'ts', dir: 'desc' })
  const [isExporting, setIsExporting] = useState(false)

  // Fetch facets (distinct countries and devices)
  const { data: facets } = useApi(() => api.get('/facets'))
  const { data: health } = useApi(() => api.get('/health'))

  // Build API query params
  const queryParams = {
    ...filters,
    limit: 25,
    offset: page * 25,
  }
  Object.keys(queryParams).forEach((k) => {
    if (queryParams[k] === '' || queryParams[k] === false || queryParams[k] === null) {
      delete queryParams[k]
    }
  })

  // Fetch login list
  const { data, error, loading, reload } = useApi(
    (signal) => api.get('/logins', { params: queryParams, signal }),
    [JSON.stringify(queryParams)]
  )

  const updateFilter = (key, val) => {
    setPage(0)
    setFilters((prev) => ({ ...prev, [key]: val }))
  }

  const resetFilters = () => {
    setPage(0)
    setFilters({
      q: '',
      country: '',
      device: '',
      risk: '',
      success: '',
      start: '',
      end: '',
      unusual_only: false,
    })
  }

  const hasActiveFilters = Object.values(filters).some((v) => v !== '' && v !== false)

  // Export current filtered list as CSV
  const handleExportCsv = async () => {
    setIsExporting(true)
    try {
      // Fetch up to 200 matching records for export
      const exportParams = { ...queryParams, limit: 200, offset: 0 }
      const res = await api.get('/logins', { params: exportParams })
      const rows = res.data?.items || []

      const columns = [
        { key: 'id', label: 'Login ID' },
        { key: 'user_name', label: 'User Name', formatter: (_, r) => r.user?.name || '' },
        { key: 'user_id', label: 'User ID', formatter: (_, r) => r.user?.id || '' },
        { key: 'ts', label: 'Timestamp (UTC)' },
        { key: 'ip', label: 'IP Address' },
        { key: 'country', label: 'Country' },
        { key: 'city', label: 'City' },
        { key: 'device', label: 'Device' },
        { key: 'success', label: 'Result', formatter: (v) => (v ? 'Success' : 'Failed') },
        { key: 'risk', label: 'Risk Score' },
        { key: 'band', label: 'Risk Band' },
        { key: 'flags', label: 'Risk Flags', formatter: (v) => (v || []).join('; ') },
        { key: 'attack_ip', label: 'Known Threat IP', formatter: (v) => (v ? 'Yes' : 'No') },
      ]

      exportToCsv(rows, `traceguard-logins-${new Date().toISOString().slice(0, 10)}.csv`, columns)
    } catch (err) {
      alert('Failed to export logins: ' + err.message)
    } finally {
      setIsExporting(false)
    }
  }

  // Handle client-side sorting of the current page
  const sortedItems = React.useMemo(() => {
    if (!data?.items) return []
    const items = [...data.items]
    if (!clientSort.key) return items

    return items.sort((a, b) => {
      let va = a[clientSort.key]
      let vb = b[clientSort.key]

      if (clientSort.key === 'user') {
        va = a.user?.name || ''
        vb = b.user?.name || ''
      }

      if (va === vb) return 0
      if (va === null || va === undefined) return 1
      if (vb === null || vb === undefined) return -1

      if (typeof va === 'string') {
        const cmp = va.localeCompare(vb)
        return clientSort.dir === 'asc' ? cmp : -cmp
      }
      return clientSort.dir === 'asc' ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1)
    })
  }, [data?.items, clientSort])

  const toggleSort = (key) => {
    if (clientSort.key === key) {
      setClientSort({ key, dir: clientSort.dir === 'asc' ? 'desc' : 'asc' })
    } else {
      setClientSort({ key, dir: 'desc' })
    }
  }

  return (
    <div className="flex items-start">
    <div className="min-w-0 flex-1 space-y-6">
      <PageHeader
        title="Suspicious Login Monitoring"
        description="Every sign-in is evaluated dynamically against the user's historical behavioral baseline: typical countries, cities, devices, active hours, and rapid failure sequences."
        right={
          <>
          <SimulateLogins onDone={() => reload()} />
          <button
            type="button"
            onClick={handleExportCsv}
            disabled={isExporting || !data?.total}
            className="btn btn-ghost text-xs"
            title="Export filtered records to spreadsheet CSV"
          >
            <Download size={14} className={isExporting ? 'animate-spin' : ''} />
            <span>{isExporting ? 'Exporting…' : 'Export CSV'}</span>
          </button>
          </>
        }
      />

      {health?.login_source === 'simulated' && (
        <div className="flex gap-2.5 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-200">
          <FlaskConical size={16} className="mt-0.5 shrink-0" />
          <p><b className="font-semibold">Simulated sign-ins.</b> No identity provider is connected, so these logs are generated for your real mailbox with the Simulate logins button. The email side of every case is real.</p>
        </div>
      )}

      {/* Filter Toolbar */}
      <Card>
        <div className="space-y-3">
          <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(140px,1fr))]">
            <div className="col-span-2 relative">
              <input
                type="text"
                className="input !pr-7"
                placeholder="Search user, name, email, IP…"
                value={filters.q}
                onChange={(e) => updateFilter('q', e.target.value)}
              />
              {filters.q && (
                <button
                  onClick={() => updateFilter('q', '')}
                  className="absolute right-2.5 top-2.5 text-slate-500 hover:text-slate-300"
                >
                  <X size={13} />
                </button>
              )}
            </div>

            <select
              className="input font-medium"
              value={filters.country}
              onChange={(e) => updateFilter('country', e.target.value)}
            >
              <option value="">Any Country</option>
              {facets?.countries?.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>

            <select
              className="input font-medium"
              value={filters.device}
              onChange={(e) => updateFilter('device', e.target.value)}
            >
              <option value="">Any Device</option>
              {facets?.devices?.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>

            <select
              className="input font-medium"
              value={filters.risk}
              onChange={(e) => updateFilter('risk', e.target.value)}
            >
              <option value="">Any Risk Band</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>

            <select
              className="input font-medium"
              value={filters.success}
              onChange={(e) => updateFilter('success', e.target.value)}
            >
              <option value="">Any Result</option>
              <option value="true">Successful only</option>
              <option value="false">Failed only</option>
            </select>

            <input
              type="date"
              className="input text-xs"
              value={filters.start}
              onChange={(e) => updateFilter('start', e.target.value)}
              title="Start date"
            />

            <input
              type="date"
              className="input text-xs"
              value={filters.end}
              onChange={(e) => updateFilter('end', e.target.value)}
              title="End date"
            />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-1 border-t border-ink-600/40 text-xs">
            <label className="flex items-center gap-2 text-slate-300 cursor-pointer select-none">
              <input
                type="checkbox"
                className="rounded border-ink-600 bg-ink-900 text-sky-600 focus:ring-sky-500"
                checked={filters.unusual_only}
                onChange={(e) => updateFilter('unusual_only', e.target.checked)}
              />
              <span>Only highlight successful sign-ins from unusual places or devices</span>
            </label>

            {hasActiveFilters && (
              <button
                type="button"
                onClick={resetFilters}
                className="inline-flex items-center gap-1 text-slate-400 hover:text-sky-300 transition"
              >
                <RotateCcw size={12} />
                <span>Reset all filters</span>
              </button>
            )}
          </div>
        </div>
      </Card>

      {/* Main Grid: Login List + Side Detail Panel */}
      <div className="grid gap-6">
        {/* Table Column */}
        <div className="space-y-4">
          <Card
            title={
              <div className="flex items-center gap-2">
                <span>Sign-In Records</span>
                {data && (
                  <span className="rounded-full bg-ink-700 px-2 py-0.5 text-xs font-semibold text-slate-300">
                    {data.total.toLocaleString()}
                  </span>
                )}
              </div>
            }
          >
            <ErrorBox error={error} />
            {loading && !data ? (
              <Spinner message="Loading login records…" />
            ) : !data || data.items.length === 0 ? (
              <Empty>No login records match the specified filters.</Empty>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className={`w-full text-left ${selectedLogin ? '[&_.td]:px-2 [&_.th]:px-2' : ''}`}>
                    <thead className="border-b border-ink-600/60 bg-ink-900/50">
                      <tr>
                        <th
                          onClick={() => toggleSort('user')}
                          className="th cursor-pointer hover:text-slate-100"
                        >
                          <div className="flex items-center gap-1">
                            <span>User</span>
                            {clientSort.key === 'user' ? (
                              clientSort.dir === 'asc' ? <ArrowUp size={12} className="text-sky-400" /> : <ArrowDown size={12} className="text-sky-400" />
                            ) : (
                              <ArrowUpDown size={11} className="opacity-40" />
                            )}
                          </div>
                        </th>
                        <th
                          onClick={() => toggleSort('country')}
                          className="th cursor-pointer hover:text-slate-100"
                        >
                          <div className="flex items-center gap-1">
                            <span>Location & IP</span>
                            {clientSort.key === 'country' ? (
                              clientSort.dir === 'asc' ? <ArrowUp size={12} className="text-sky-400" /> : <ArrowDown size={12} className="text-sky-400" />
                            ) : (
                              <ArrowUpDown size={11} className="opacity-40" />
                            )}
                          </div>
                        </th>
                        <th className={`th ${selectedLogin ? 'xl:hidden' : ''}`}>Device / Client</th>
                        <th
                          onClick={() => toggleSort('success')}
                          className="th cursor-pointer hover:text-slate-100"
                        >
                          <div className="flex items-center gap-1">
                            <span>Result</span>
                            {clientSort.key === 'success' ? (
                              clientSort.dir === 'asc' ? <ArrowUp size={12} className="text-sky-400" /> : <ArrowDown size={12} className="text-sky-400" />
                            ) : (
                              <ArrowUpDown size={11} className="opacity-40" />
                            )}
                          </div>
                        </th>
                        <th
                          onClick={() => toggleSort('risk')}
                          className="th cursor-pointer hover:text-slate-100"
                        >
                          <div className="flex items-center gap-1">
                            <span>Risk Score</span>
                            {clientSort.key === 'risk' ? (
                              clientSort.dir === 'asc' ? <ArrowUp size={12} className="text-sky-400" /> : <ArrowDown size={12} className="text-sky-400" />
                            ) : (
                              <ArrowUpDown size={11} className="opacity-40" />
                            )}
                          </div>
                        </th>
                        <th
                          onClick={() => toggleSort('ts')}
                          className="th text-right cursor-pointer hover:text-slate-100"
                        >
                          <div className="flex items-center justify-end gap-1">
                            <span>Time (UTC)</span>
                            {clientSort.key === 'ts' ? (
                              clientSort.dir === 'asc' ? <ArrowUp size={12} className="text-sky-400" /> : <ArrowDown size={12} className="text-sky-400" />
                            ) : (
                              <ArrowUpDown size={11} className="opacity-40" />
                            )}
                          </div>
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-600/40">
                      {sortedItems.map((r) => {
                        const isSelected = selectedLogin?.id === r.id
                        const hasImpossibleTravel =
                          r.flags && r.flags.some((f) => f.includes('IMPOSSIBLE_TRAVEL'))

                        return (
                          <tr
                            key={r.id}
                            onClick={() => setSelectedLogin(r)}
                            className={`cursor-pointer transition-colors duration-100 hover:bg-ink-700/50 ${
                              isSelected ? 'bg-ink-700/80 border-l-2 border-l-sky-500' : ''
                            }`}
                          >
                            <td className="td whitespace-nowrap">
                              <div className="font-semibold text-slate-200">
                                {r.user.name}
                              </div>
                              <div className="text-[11px] text-slate-500 font-mono">
                                {r.user.id}
                              </div>
                            </td>
                            <td className="td">
                              <div className="text-slate-300 font-medium">
                                {formatLocation(r)}
                              </div>
                              <div className="text-[11px] font-mono text-slate-500">
                                {r.ip}
                                {r.attack_ip && (
                                  <span className="ml-1 text-[10px] text-rose-400 font-bold">
                                    [ATTACK IP]
                                  </span>
                                )}
                              </div>
                            </td>
                            <td className={`td text-slate-400 text-xs ${selectedLogin ? 'xl:hidden' : ''}`}>
                              {r.device || 'Unknown Client'}
                            </td>
                            <td className="td">
                              {r.success ? (
                                <Chip tone="emerald">Success</Chip>
                              ) : (
                                <Chip tone="rose">Failed</Chip>
                              )}
                            </td>
                            <td className="td">
                              <div className="flex flex-col items-start gap-1">
                                <Band band={r.band} score={r.risk} />
                                {hasImpossibleTravel && (
                                  <span className="rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 px-1.5 py-0.2 text-[9px] font-bold">
                                    Impossible Travel
                                  </span>
                                )}
                              </div>
                            </td>
                            <td className="td whitespace-nowrap text-right text-xs text-slate-400 font-mono">
                              {when(r.ts)}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="mt-4 pt-3 border-t border-ink-600/50">
                  <Pagination
                    page={page}
                    pageSize={25}
                    total={data.total}
                    onPageChange={(newPage) => setPage(newPage)}
                  />
                </div>
              </>
            )}
          </Card>
        </div>

      </div>
    </div>

    {/* Detail pane: a real column beside the page (no backdrop), so the table stays visible and clickable */}
    <LoginDetailPanel row={panelRow} open={!!selectedLogin} onClose={() => setSelectedLogin(null)} />
    </div>
  )
}
const Row = ({ label, children }) => (
  <div className="grid grid-cols-[84px_minmax(0,1fr)] items-baseline gap-3 py-1.5">
    <dt className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{label}</dt>
    <dd className="min-w-0 break-words font-mono text-xs text-slate-200">{children}</dd>
  </div>
)

const SectionLabel = ({ children, right }) => (
  <div className="mb-2 flex items-center justify-between gap-2">
    <h4 className="eyebrow">{children}</h4>
    {right}
  </div>
)

// Non-modal detail pane. At xl+ it is a flex column that animates its width and pushes the page left;
// below xl it slides in from the right over the page (still no backdrop or blur).
function LoginDetailPanel({ row, open, onClose }) {
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') onCloseRef.current() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  if (!row) return null
  return (
    <aside className="detail-pane no-print" data-open={open} aria-label={`Login details for ${row.user.name}`} aria-hidden={!open}>
      <div className="detail-inner">
        <LoginDetailContent row={row} onClose={onClose} />
      </div>
    </aside>
  )
}

function LoginDetailContent({ row, onClose }) {
  const { data, loading } = useApi(
    () => api.get(`/users/${row.user.id}/logins`),
    [row.user.id]
  )
  const baseline = data?.baseline
  const isThin = baseline?.thin
  const hasImpossibleTravel = row.flags && row.flags.some((f) => f.includes('IMPOSSIBLE_TRAVEL'))

  return (
    <div className="flex h-full flex-col overflow-hidden border-ink-600/70 bg-ink-800 max-xl:border-l max-xl:shadow-pop xl:rounded-xl xl:border xl:shadow-card">
        {/* Header */}
        <header className="flex items-start justify-between gap-3 border-b border-ink-600/50 px-5 py-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <User size={16} className="shrink-0 text-sky-400" />
              <h3 className="truncate text-base font-semibold text-slate-100">{row.user.name}</h3>
            </div>
            <p className="mt-1 truncate font-mono text-xs text-slate-400" title={row.user.email || row.user.id}>
              {row.user.email || row.user.id}
            </p>
            <p className="mt-0.5 text-[11px] capitalize text-slate-500">Role: {row.user.role || 'Staff / Student'}</p>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            <RiskBadge band={row.band} score={row.risk} aligned />
            <button
              type="button"
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-ink-600 text-slate-400 transition-colors hover:bg-ink-700 hover:text-slate-100"
              aria-label="Close details"
            >
              <X size={16} />
            </button>
          </div>
        </header>

        {/* Scrollable body */}
        <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
          {/* Selected event */}
          <section>
            <SectionLabel right={<Chip tone={row.success ? 'emerald' : 'rose'}>{row.success ? 'Success' : 'Failed'}</Chip>}>
              Selected sign-in event
            </SectionLabel>
            <div className="panel px-4 py-2">
              <dl className="divide-y divide-ink-600/40">
                <Row label="Location">{formatLocation(row)}</Row>
                <Row label="IP address">
                  {row.ip}
                  {row.attack_ip && <span className="ml-2 text-[10px] font-bold text-rose-400">[ATTACK IP]</span>}
                </Row>
                <Row label="Device">{row.device || 'Unknown'}</Row>
                <Row label="Time (UTC)">{when(row.ts)}</Row>
              </dl>
            </div>

            {hasImpossibleTravel && (
              <div className="mt-3 rounded-lg border border-rose-500/50 bg-rose-500/10 p-3 text-rose-300">
                <div className="flex items-center gap-1.5 text-xs font-semibold">
                  <AlertTriangle size={14} className="shrink-0" />
                  Impossible travel condition detected
                </div>
                <p className="mt-1 text-xs leading-relaxed text-rose-200/90">
                  Physical transit speed between successive sign-in locations exceeds reasonable commercial flight limits.
                </p>
              </div>
            )}
          </section>

          {/* Risk flags */}
          <section>
            <SectionLabel>Triggered risk flags</SectionLabel>
            {row.flags && row.flags.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {row.flags.map((flag) => (
                  <Chip key={flag} tone="amber">{flag.replace(/^L_/, '').toLowerCase().replaceAll('_', ' ')}</Chip>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-500">No anomaly flags triggered for this event.</p>
            )}
          </section>

          {loading || !data ? (
            <Spinner message="Fetching user history & baseline…" />
          ) : (
            <>
              {isThin && (
                <div className="rounded-lg border border-amber-400/40 bg-amber-400/10 p-3 text-amber-200">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-300">
                    <Info size={14} className="shrink-0" />
                    Low confidence: thin history
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-amber-200/90">
                    This user has only {baseline.n_success} recorded sign-ins. Normal patterns (locations, devices, and hours) are not yet firmly established.
                  </p>
                </div>
              )}

              {/* Usual pattern */}
              <section>
                <SectionLabel right={<span className="text-[11px] text-slate-500">{baseline?.n_success || 0} successful logins</span>}>
                  Usual pattern for this user
                </SectionLabel>
                <div className="panel divide-y divide-ink-600/40 px-4">
                  <div className="py-3">
                    <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Countries</div>
                    <div className="flex flex-wrap gap-1.5">
                      {baseline?.countries?.length > 0
                        ? baseline.countries.map((c) => <Chip key={c} tone="sky">{c}</Chip>)
                        : <span className="text-xs text-slate-500">None established</span>}
                    </div>
                  </div>
                  <div className="py-3">
                    <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Devices</div>
                    <div className="flex flex-wrap gap-1.5">
                      {baseline?.devices?.length > 0
                        ? baseline.devices.map((d) => <Chip key={d} tone="violet">{d}</Chip>)
                        : <span className="text-xs text-slate-500">None established</span>}
                    </div>
                  </div>
                  {baseline?.usual_hours?.length > 0 && (
                    <div className="py-3">
                      <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Typical hours (UTC)</div>
                      <div className="font-mono text-xs leading-relaxed text-slate-300">
                        {baseline.usual_hours.map((h) => `${h}:00`).join(', ')}
                      </div>
                    </div>
                  )}
                </div>
              </section>

              {data.case_id && (
                <Link to={`/investigate/${data.case_id}`} className="btn btn-primary w-full !py-2.5 text-sm">
                  <ShieldAlert size={15} />
                  Open linked case #{data.case_id}
                </Link>
              )}

              {/* Recent history: fixed layout, so it fits the drawer with no sideways scroll */}
              <section>
                <SectionLabel right={<span className="text-[11px] text-slate-500">Most recent first</span>}>
                  Recent sign-in history ({data.items?.length || 0})
                </SectionLabel>
                <div className="panel max-h-72 overflow-y-auto">
                  <table className="w-full table-fixed text-left text-xs">
                    <thead className="sticky top-0 border-b border-ink-600/50 bg-ink-900">
                      <tr>
                        <th className="w-[112px] px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Time</th>
                        <th className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Location</th>
                        <th className="w-[56px] px-2 py-2 text-center text-[10px] font-semibold uppercase tracking-wider text-slate-500">Result</th>
                        <th className="w-[120px] px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-slate-500">Risk</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-600/40">
                      {data.items?.map((item) => (
                        <tr key={item.id} className="hover:bg-ink-700/30">
                          <td className="whitespace-nowrap px-3 py-2 font-mono text-[11px] text-slate-400">{when(item.ts)}</td>
                          <td className="truncate px-3 py-2 text-slate-200" title={formatLocation(item)}>{formatLocation(item)}</td>
                          <td className="px-2 py-2 text-center">
                            {item.success
                              ? <span className="text-emerald-400">ok</span>
                              : <span className="font-semibold text-rose-400">failed</span>}
                          </td>
                          <td className="px-3 py-2 text-right"><RiskBadge band={item.band} score={item.risk} aligned className="!w-[104px]" /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
        </div>
    </div>
  )
}