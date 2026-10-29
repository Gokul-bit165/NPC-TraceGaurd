import React from 'react'
import { Link } from 'react-router-dom'
import { AlertOctagon, KeyRound, Mail, MailWarning } from 'lucide-react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import api from '../api.js'
import { Band, Card, Empty, ErrorBox, Spinner, Stat, useLoad, when } from '../ui.jsx'

const tip = { contentStyle: { background: '#151c2b', border: '1px solid #2a3550', borderRadius: 8, fontSize: 12 }, labelStyle: { color: '#cbd5e1' } }

export default function Dashboard() {
  const { data: o, error, loading } = useLoad(() => api.get('/overview'))
  if (loading) return <Spinner />
  if (error) return <ErrorBox error={error} />
  const k = o.kpis, t = o.triage
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-white">Security Dashboard</h1>
        <p className="text-sm text-slate-400">Evidence from email and sign-in records, merged into one ranked list of incidents.</p>
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat icon={Mail} label="Emails analyzed" value={k.emails_analyzed} sub={`${k.logins_scored.toLocaleString()} logins scored`} />
        <Stat icon={MailWarning} label="Phishing emails" value={k.phishing_emails} sub="Medium risk or above" tone="amber" />
        <Stat icon={KeyRound} label="Suspicious logins" value={k.suspicious_logins} sub="Medium risk or above" tone="violet" />
        <Stat icon={AlertOctagon} label="Critical incidents" value={k.critical_incidents} sub="Need investigation now" tone="rose" />
      </div>

      <div className="card flex flex-wrap items-center gap-x-8 gap-y-2 px-5 py-3 text-sm">
        <span className="font-semibold text-white">Triage on this data</span>
        <span><b className="text-white">{t.events_scored.toLocaleString()}</b> <span className="text-slate-400">events scored</span></span>
        <span><b className="text-white">{t.needs_review}</b> <span className="text-slate-400">cases need a human ({(t.review_share * 100).toFixed(1)}% of events)</span></span>
        <span><b className="text-white">{t.auto_closed}</b> <span className="text-slate-400">low-risk cases auto-closed with a note</span></span>
        <span className="text-xs text-slate-500">Seeded demo data: shows the workflow, not real-world performance.</span>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card title="Threat activity (flagged per day)" className="lg:col-span-2">
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={o.activity}>
              <CartesianGrid stroke="#2a3550" strokeDasharray="3 3" />
              <XAxis dataKey="day" stroke="#64748b" fontSize={11} /><YAxis stroke="#64748b" fontSize={11} allowDecimals={false} />
              <Tooltip {...tip} /><Legend wrapperStyle={{ fontSize: 12 }} />
              <Area type="monotone" dataKey="phishing_emails" name="Phishing emails" stroke="#fbbf24" fill="#fbbf2433" />
              <Area type="monotone" dataKey="suspicious_logins" name="Suspicious logins" stroke="#a78bfa" fill="#a78bfa33" />
            </AreaChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Phishing vs legitimate email">
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={[{ name: 'Flagged', value: o.email_mix.flagged }, { name: 'Clean', value: o.email_mix.clean }]} dataKey="value" innerRadius={55} outerRadius={85} paddingAngle={2}>
                <Cell fill="#f97316" /><Cell fill="#34d399" />
              </Pie>
              <Tooltip {...tip} /><Legend wrapperStyle={{ fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card title="Login activity by location (last 14 days)">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={o.countries} layout="vertical" margin={{ left: 8 }}>
              <CartesianGrid stroke="#2a3550" strokeDasharray="3 3" />
              <XAxis type="number" stroke="#64748b" fontSize={11} /><YAxis type="category" dataKey="country" stroke="#64748b" fontSize={11} width={34} />
              <Tooltip {...tip} /><Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="flagged" name="Flagged" stackId="a" fill="#f97316" />
              <Bar dataKey="failed" name="Failed" stackId="a" fill="#64748b" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title="High-risk incidents requiring action" right={<Link className="text-xs text-sky-400" to="/response">Open queue</Link>}>
          {o.action_needed.length === 0 ? <Empty>Nothing waiting.</Empty> : (
            <ul className="divide-y divide-ink-600/50">
              {o.action_needed.map((c) => (
                <li key={c.id} className="flex items-center justify-between py-2">
                  <Link to={`/response/${c.id}`} className="min-w-0">
                    <div className="truncate text-sm text-slate-200">{c.user}{c.campaign_size > 1 && <span className="ml-1 text-xs text-slate-500">· campaign of {c.campaign_size}</span>}</div>
                    <div className="truncate text-xs text-slate-500">{c.headline}</div>
                  </Link>
                  <div className="ml-2 flex shrink-0 flex-col items-end gap-1"><Band band={c.band} score={c.score} />{c.pending_approvals > 0 && <span className="text-[11px] text-amber-300">{c.pending_approvals} to approve</span>}</div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Top suspicious users">
          <ul className="divide-y divide-ink-600/50">
            {o.top_users.map((c) => (
              <li key={c.id} className="flex items-center justify-between py-2">
                <Link to={`/investigate/${c.id}`} className="text-sm text-slate-200 hover:text-sky-300">{c.user}</Link>
                <Band band={c.band} score={c.score} />
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card title="Recent security alerts">
        <table className="w-full">
          <thead><tr><th className="th">User</th><th className="th">What we found</th><th className="th">Risk</th><th className="th">Status</th><th className="th">Updated</th></tr></thead>
          <tbody className="divide-y divide-ink-600/40">
            {o.recent_alerts.map((c) => (
              <tr key={c.id} className="hover:bg-ink-700/40">
                <td className="td"><Link className="text-sky-300" to={`/investigate/${c.id}`}>{c.user}</Link></td>
                <td className="td text-slate-400">{c.headline}</td>
                <td className="td"><Band band={c.band} score={c.score} /></td>
                <td className="td text-slate-400">{c.status.replace('_', ' ')}</td>
                <td className="td text-slate-500">{when(c.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
