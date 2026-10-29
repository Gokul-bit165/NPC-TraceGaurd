import React, { useState } from 'react'
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
} from 'lucide-react'
import api from '../api.js'
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
  const [clientSort, setClientSort] = useState({ key: 'ts', dir: 'desc' })
  const [isExporting, setIsExporting] = useState(false)

  // Fetch facets (distinct countries and devices)
  const { data: facets } = useApi(() => api.get('/facets'))

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
    <div className="space-y-6">
      <PageHeader
        title="Suspicious Login Monitoring"
        description="Every sign-in is evaluated dynamically against the user's historical behavioral baseline: typical countries, cities, devices, active hours, and rapid failure sequences."
        right={
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
        }
      />

      {/* Filter Toolbar */}
      <Card>
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-4 lg:grid-cols-8">
            <div className="sm:col-span-2 lg:col-span-2 relative">
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
      <div className="grid gap-6 xl:grid-cols-3">
        {/* Table Column */}
        <div className="space-y-4 xl:col-span-2">
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
                  <table className="w-full text-left">
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
                        <th className="th">Device / Client</th>
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
                            <td className="td">
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
                            <td className="td text-slate-400 text-xs">
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
                            <td className="td text-right text-xs text-slate-400 font-mono">
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

        {/* User Detail Side Panel */}
        <div>
          <LoginDetailPanel
            row={selectedLogin}
            onClose={() => setSelectedLogin(null)}
          />
        </div>
      </div>
    </div>
  )
}

function LoginDetailPanel({ row, onClose }) {
  const { data, loading } = useApi(
    () => (row ? api.get(`/users/${row.user.id}/logins`) : Promise.resolve({ data: null })),
    [row?.user.id]
  )

  if (!row) {
    return (
      <Card title="Login Details">
        <div className="py-16 text-center text-slate-500 space-y-2">
          <KeyRound className="mx-auto text-slate-600" size={32} />
          <h4 className="text-sm font-semibold text-slate-300">
            No Login Selected
          </h4>
          <p className="text-xs text-slate-500 max-w-xs mx-auto">
            Click on any login record in the table to inspect risk evidence, unusual flags, and comparison against normal user baseline.
          </p>
        </div>
      </Card>
    )
  }

  const baseline = data?.baseline
  const isThin = baseline?.thin
  const hasImpossibleTravel =
    row.flags && row.flags.some((f) => f.includes('IMPOSSIBLE_TRAVEL'))

  return (
    <Card
      title={
        <div className="flex items-center gap-2">
          <User size={16} className="text-sky-400" />
          <span className="font-semibold text-slate-200">{row.user.name}</span>
        </div>
      }
      right={
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-slate-100 transition"
          aria-label="Close details"
        >
          <X size={16} />
        </button>
      }
    >
      <div className="space-y-4 text-xs">
        {/* User headline */}
        <div className="flex items-center justify-between border-b border-ink-600/40 pb-3">
          <div>
            <div className="font-mono text-slate-300">{row.user.email || row.user.id}</div>
            <div className="text-[11px] text-slate-500 capitalize">Role: {row.user.role || 'Staff / Student'}</div>
          </div>
          <RiskBadge band={row.band} score={row.risk} size="md" />
        </div>

        {/* Selected Login Details Box */}
        <div className="rounded-xl border border-ink-600/70 bg-ink-900 p-3.5 space-y-2">
          <div className="font-semibold uppercase tracking-wider text-[10px] text-slate-400">
            Selected Sign-In Event
          </div>
          <div className="text-sm font-medium text-slate-100 flex items-center justify-between">
            <span>{formatLocation(row)}</span>
            <Chip tone={row.success ? 'emerald' : 'rose'}>
              {row.success ? 'Success' : 'Failed'}
            </Chip>
          </div>
          <div className="text-slate-400 font-mono text-[11px] space-y-0.5">
            <div>IP Address: <span className="text-slate-200">{row.ip}</span></div>
            <div>Device: <span className="text-slate-200">{row.device || 'Unknown'}</span></div>
            <div>Time (UTC): <span className="text-slate-200">{when(row.ts)}</span></div>
          </div>

          {/* Impossible travel callout */}
          {hasImpossibleTravel && (
            <div className="mt-2 rounded-lg border border-rose-500/50 bg-rose-950/40 p-2 text-rose-300 text-xs space-y-0.5">
              <div className="flex items-center gap-1 font-bold">
                <AlertTriangle size={13} />
                <span>Impossible Travel Condition Detected</span>
              </div>
              <p className="text-[11px] text-rose-200">
                Physical transit speed between successive sign-in locations exceeds reasonable commercial flight limits.
              </p>
            </div>
          )}

          {/* Risk evidence flags */}
          <div className="pt-1">
            <div className="text-[10px] uppercase font-semibold text-slate-500 mb-1">
              Triggered Risk Flags
            </div>
            {row.flags && row.flags.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {row.flags.map((flag) => (
                  <Chip key={flag} tone="amber">
                    {flag.replace(/^L_/, '').toLowerCase().replaceAll('_', ' ')}
                  </Chip>
                ))}
              </div>
            ) : (
              <span className="text-slate-500 text-[11px]">
                No anomaly flags triggered for this event.
              </span>
            )}
          </div>
        </div>

        {/* Baseline Comparison */}
        {loading || !data ? (
          <Spinner message="Fetching user history & baseline…" />
        ) : (
          <>
            {/* Low-confidence warning if baseline is thin */}
            {isThin && (
              <div className="rounded-lg border border-amber-400/40 bg-amber-400/10 p-2.5 text-amber-200">
                <div className="flex items-center gap-1 font-semibold text-amber-300">
                  <Info size={13} />
                  <span>Low Confidence: Thin History</span>
                </div>
                <p className="mt-0.5 text-[11px] text-amber-200/90 leading-relaxed">
                  This user has only {baseline.n_success} recorded sign-ins. Normal patterns (locations, devices, and hours) are not yet firmly established.
                </p>
              </div>
            )}

            {/* Usual Pattern */}
            <div className="rounded-lg border border-ink-600/40 bg-ink-900/50 p-3 space-y-2">
              <div className="font-semibold text-slate-300">
                Usual Pattern for this User ({baseline?.n_success || 0} Successful Logins)
              </div>
              <div>
                <div className="text-[10px] uppercase text-slate-500 mb-1">Usual Countries</div>
                <div className="flex flex-wrap gap-1">
                  {baseline?.countries?.length > 0 ? (
                    baseline.countries.map((c) => (
                      <Chip key={c} tone="sky">{c}</Chip>
                    ))
                  ) : (
                    <span className="text-slate-500">None established</span>
                  )}
                </div>
              </div>

              <div>
                <div className="text-[10px] uppercase text-slate-500 mb-1">Usual Devices</div>
                <div className="flex flex-wrap gap-1">
                  {baseline?.devices?.length > 0 ? (
                    baseline.devices.map((d) => (
                      <Chip key={d} tone="violet">{d}</Chip>
                    ))
                  ) : (
                    <span className="text-slate-500">None established</span>
                  )}
                </div>
              </div>

              {baseline?.usual_hours?.length > 0 && (
                <div>
                  <div className="text-[10px] uppercase text-slate-500 mb-0.5">Typical Hours (UTC)</div>
                  <div className="font-mono text-slate-300 text-[11px]">
                    {baseline.usual_hours.map((h) => `${h}:00`).join(', ')}
                  </div>
                </div>
              )}
            </div>

            {/* Case Navigation Button if linked to a case */}
            {data.case_id && (
              <Link
                to={`/investigate/${data.case_id}`}
                className="btn btn-primary w-full justify-center !py-2 text-xs"
              >
                <ShieldAlert size={14} />
                <span>Open Linked Case #{data.case_id}</span>
              </Link>
            )}

            {/* History Table */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="font-semibold text-slate-300">
                  Recent Sign-In History ({data.items?.length || 0})
                </span>
                <span className="text-[10px] text-slate-500">Most recent first</span>
              </div>
              <div className="max-h-56 overflow-y-auto rounded-lg border border-ink-600/60 bg-ink-900/40">
                <table className="w-full text-left">
                  <tbody className="divide-y divide-ink-600/40 text-[11px]">
                    {data.items?.map((item) => (
                      <tr key={item.id} className="hover:bg-ink-700/30">
                        <td className="px-2.5 py-1.5 font-mono text-slate-400">
                          {when(item.ts)}
                        </td>
                        <td className="px-2.5 py-1.5 text-slate-200">
                          {formatLocation(item)}
                        </td>
                        <td className="px-2 py-1.5 text-center">
                          {item.success ? (
                            <span className="text-emerald-400">ok</span>
                          ) : (
                            <span className="text-rose-400 font-bold">failed</span>
                          )}
                        </td>
                        <td className="px-2.5 py-1.5 text-right">
                          <Band band={item.band} score={item.risk} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </Card>
  )
}
