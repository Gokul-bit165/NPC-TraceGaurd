import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Inbox, Link2, Loader2, Mail, MailWarning, RefreshCw, Search, Users } from 'lucide-react'
import api, { errText } from '../api.js'
import { Card, EmptyState, ErrorBox, NotificationToast, PageHeader, RiskBadge, Spinner, StatCard, when } from '../ui.jsx'
import { useApi } from '../hooks/useApi.js'

const BANDS = ['', 'critical', 'high', 'medium', 'low']
const POLL_MS = 10000

export default function Mailbox() {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [band, setBand] = useState('')
  const [syncing, setSyncing] = useState(false)
  const [toast, setToast] = useState(null)
  const [toastType, setToastType] = useState('success')
  const { data, error, loading, reload } = useApi(
    (signal) => api.get('/emails', { params: { q: q || undefined, band: band || undefined, limit: 200 }, signal }),
    [q, band],
  )

  // New mail arrives from the n8n workflow on its own, so the list refreshes itself.
  useEffect(() => {
    const t = setInterval(() => reload(), POLL_MS)
    return () => clearInterval(t)
  }, [reload])

  const syncNow = async () => {
    setSyncing(true)
    try {
      const { data: r } = await api.post('/mail/sync')
      setToastType('success')
      setToast(`Sync finished: ${r.fetched ?? 0} fetched, ${r.analysed ?? 0} analysed, ${r.suspicious ?? 0} suspicious.`)
      await reload()
    } catch (e) {
      setToastType('error')
      setToast(errText(e))
    } finally {
      setSyncing(false)
    }
  }

  if (loading && !data) return <Spinner message="Loading fetched mail…" />
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />

  const items = data?.items || []

  return (
    <div className="space-y-6 pb-12">
      <NotificationToast show={!!toast} message={toast} type={toastType} onClose={() => setToast(null)} />
      <PageHeader
        icon={Inbox}
        title="Mailbox"
        description="Mail fetched from the connected Gmail accounts, scored by the phishing model as it arrives."
        badge={<span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-xs font-semibold text-emerald-300">Auto-sync · every 5 min</span>}
        right={
          <button type="button" onClick={syncNow} disabled={syncing} className="btn btn-primary inline-flex items-center gap-2">
            {syncing ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
            {syncing ? 'Syncing…' : 'Sync now'}
          </button>
        }
      />

      <section aria-label="Mail summary" className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatCard icon={Mail} label="Emails fetched" value={(data?.total ?? 0).toLocaleString()} sub="matching the filter below" tone="sky" />
        <StatCard icon={MailWarning} label="Suspicious" value={data?.suspicious ?? 0} sub="medium risk or above" tone="rose" />
        <StatCard icon={Users} label="Mailboxes" value={data?.mailboxes ?? 0} sub="with analysed mail" tone="violet" />
        <StatCard icon={RefreshCw} label="Newest mail" value={data?.newest ? when(data.newest) : '—'} sub="refreshes every 10 s" tone="emerald" />
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <label className="relative">
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search sender, subject or mailbox"
            className="input w-72 pl-8" aria-label="Search mail" />
        </label>
        <select value={band} onChange={(e) => setBand(e.target.value)} className="input w-40" aria-label="Filter by risk">
          {BANDS.map((b) => <option key={b} value={b}>{b ? `${b[0].toUpperCase()}${b.slice(1)} risk` : 'All risk levels'}</option>)}
        </select>
      </div>

      <Card bodyClassName="p-0">
        {items.length === 0 ? (
          <EmptyState icon={Inbox} title="No mail yet" message="Once the Gmail workflow runs, fetched emails appear here. Use Sync now to fetch immediately." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-ink-600/60 text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-4 py-3">Risk</th>
                  <th className="px-4 py-3">From</th>
                  <th className="px-4 py-3">Subject</th>
                  <th className="px-4 py-3">Mailbox</th>
                  <th className="px-4 py-3">Received</th>
                  <th className="px-4 py-3">Case</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-600/40">
                {items.map((m) => (
                  <tr key={m.id} className="cursor-pointer hover:bg-ink-700/40"
                    onClick={() => navigate(`/investigate/mail/${m.id}`)}>
                    <td className="px-4 py-2.5"><RiskBadge band={m.band} score={m.score} aligned /></td>
                    <td className="max-w-[220px] truncate px-4 py-2.5 text-slate-200" title={m.sender}>{m.sender || '—'}</td>
                    <td className="max-w-[360px] truncate px-4 py-2.5 text-slate-100" title={m.subject}>
                      {m.subject || '(no subject)'}
                      {m.links > 0 && <span className="ml-2 inline-flex items-center gap-1 text-xs text-slate-400"><Link2 size={11} />{m.links}</span>}
                    </td>
                    <td className="max-w-[200px] truncate px-4 py-2.5 font-mono text-xs text-slate-400" title={m.mailbox.email}>{m.mailbox.email || m.mailbox.id}</td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-slate-400">{when(m.received_at)}</td>
                    <td className="px-4 py-2.5">
                      {m.case_id ? <span className="text-sky-300">#{m.case_id}</span> : <span className="text-slate-500">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
