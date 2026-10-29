import React from 'react'
import { Link } from 'react-router-dom'
import { X } from 'lucide-react'
import api from '../api.js'
import { Band, Card, Chip, Empty, ErrorBox, Spinner, useLoad, when } from '../ui.jsx'

const place = (r) => [r.city, r.country].filter(Boolean).join(', ') || 'Unknown'

export default function Logins() {
  const [f, setF] = React.useState({ q: '', country: '', device: '', risk: '', success: '', start: '', end: '', unusual_only: false })
  const [page, setPage] = React.useState(0)
  const [sel, setSel] = React.useState(null)
  const params = { ...f, limit: 25, offset: page * 25 }
  Object.keys(params).forEach((k) => (params[k] === '' || params[k] === false) && delete params[k])
  const { data, error, loading } = useLoad(() => api.get('/logins', { params }), [JSON.stringify(params)])
  const facets = useLoad(() => api.get('/facets'))
  const set = (k) => (e) => { setPage(0); setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }) }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-white">Suspicious Login Investigation</h1>
        <p className="text-sm text-slate-400">Each login is scored against that user's own history: places, devices, hours, and failed attempts.</p>
      </div>
      <Card>
        <div className="grid gap-3 md:grid-cols-4 lg:grid-cols-8">
          <input className="input md:col-span-2" placeholder="Search student ID, name, email, IP" value={f.q} onChange={set('q')} />
          <select className="input" value={f.country} onChange={set('country')}><option value="">Any country</option>{facets.data?.countries.map((c) => <option key={c}>{c}</option>)}</select>
          <select className="input" value={f.device} onChange={set('device')}><option value="">Any device</option>{facets.data?.devices.map((c) => <option key={c}>{c}</option>)}</select>
          <select className="input" value={f.risk} onChange={set('risk')}><option value="">Any risk</option>{['critical', 'high', 'medium', 'low'].map((c) => <option key={c} value={c}>{c}</option>)}</select>
          <select className="input" value={f.success} onChange={set('success')}><option value="">Any result</option><option value="true">Successful</option><option value="false">Failed</option></select>
          <input className="input" type="date" value={f.start} onChange={set('start')} title="From" />
          <input className="input" type="date" value={f.end} onChange={set('end')} title="To" />
        </div>
        <label className="mt-3 flex items-center gap-2 text-sm text-slate-400"><input type="checkbox" checked={f.unusual_only} onChange={set('unusual_only')} /> Only successful logins from unusual places or devices</label>
      </Card>

      <div className="grid gap-5 xl:grid-cols-3">
        <Card className="xl:col-span-2" title={data ? `${data.total.toLocaleString()} logins` : 'Logins'}>
          <ErrorBox error={error} />
          {loading && !data ? <Spinner /> : !data || data.items.length === 0 ? <Empty>No logins match.</Empty> : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead><tr><th className="th">User</th><th className="th">Location</th><th className="th">Device</th><th className="th">Result</th><th className="th">Risk</th><th className="th">Time</th></tr></thead>
                  <tbody className="divide-y divide-ink-600/40">
                    {data.items.map((r) => (
                      <tr key={r.id} className={`cursor-pointer hover:bg-ink-700/40 ${sel?.id === r.id ? 'bg-ink-700/60' : ''}`} onClick={() => setSel(r)}>
                        <td className="td text-slate-200">{r.user.name}</td>
                        <td className="td text-slate-300">{place(r)}<div className="text-[11px] text-slate-500">{r.ip}</div></td>
                        <td className="td text-slate-400">{r.device || 'unknown'}</td>
                        <td className="td">{r.success ? <Chip tone="emerald">success</Chip> : <Chip tone="rose">failed</Chip>}</td>
                        <td className="td"><Band band={r.band} score={r.risk} /></td>
                        <td className="td text-slate-500">{when(r.ts)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-3 flex items-center justify-between text-sm text-slate-400">
                <button className="btn btn-ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
                <span>Page {page + 1} of {Math.max(1, Math.ceil(data.total / 25))}</span>
                <button className="btn btn-ghost" disabled={(page + 1) * 25 >= data.total} onClick={() => setPage(page + 1)}>Next</button>
              </div>
            </>
          )}
        </Card>
        <UserPanel row={sel} onClose={() => setSel(null)} />
      </div>
    </div>
  )
}

function UserPanel({ row, onClose }) {
  const { data, loading } = useLoad(() => row ? api.get(`/users/${row.user.id}/logins`) : Promise.resolve({ data: null }), [row?.user.id])
  if (!row) return <Card title="Login details"><Empty>Click a login to see why it was scored that way and the user's full history.</Empty></Card>
  return (
    <Card title={row.user.name} right={<button onClick={onClose} className="text-slate-500 hover:text-slate-300"><X size={16} /></button>}>
      <div className="space-y-3 text-sm">
        <div className="flex items-center justify-between"><span className="text-slate-400">{row.user.email}</span><Band band={row.band} score={row.risk} /></div>
        <div className="rounded-lg bg-ink-900 p-3">
          <div className="mb-1 text-xs text-slate-500">This login</div>
          <div className="text-slate-200">{place(row)} · {row.device || 'unknown device'} · {row.success ? 'success' : 'failed'}</div>
          <div className="mt-2 flex flex-wrap gap-1">{row.flags.length ? row.flags.map((c) => <Chip key={c} tone="amber">{c.replace('L_', '').toLowerCase().replaceAll('_', ' ')}</Chip>) : <span className="text-xs text-slate-500">No unusual signals</span>}</div>
        </div>
        {loading || !data ? <Spinner /> : (
          <>
            <div>
              <div className="mb-1 text-xs text-slate-500">Usual for this user ({data.baseline.n_success} successful logins{data.baseline.thin ? ', thin history' : ''})</div>
              <div className="flex flex-wrap gap-1">
                {data.baseline.countries.map((c) => <Chip key={c} tone="sky">{c}</Chip>)}
                {data.baseline.cities.map((c) => <Chip key={c}>{c}</Chip>)}
                {data.baseline.devices.map((c) => <Chip key={c} tone="violet">{c}</Chip>)}
              </div>
              {data.baseline.usual_hours.length > 0 && <div className="mt-1 text-xs text-slate-500">Usual hours (UTC): {data.baseline.usual_hours.join(', ')}</div>}
            </div>
            {data.case_id && <Link className="btn btn-primary" to={`/investigate/${data.case_id}`}>Open investigation</Link>}
            <div>
              <div className="mb-1 text-xs text-slate-500">Complete history (latest {data.items.length})</div>
              <div className="max-h-72 overflow-y-auto rounded-lg border border-ink-600/50">
                <table className="w-full">
                  <tbody className="divide-y divide-ink-600/40">
                    {data.items.map((r) => (
                      <tr key={r.id}>
                        <td className="px-2 py-1 text-xs text-slate-500">{when(r.ts)}</td>
                        <td className="px-2 py-1 text-xs text-slate-300">{place(r)}</td>
                        <td className="px-2 py-1 text-xs">{r.success ? '' : <span className="text-rose-400">failed</span>}</td>
                        <td className="px-2 py-1 text-right"><Band band={r.band} /></td>
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
