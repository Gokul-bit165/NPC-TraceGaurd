import React from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import api from '../api.js'
import { Band, Card, Empty, ErrorBox, Spinner, useLoad, when } from '../ui.jsx'

const tip = { contentStyle: { background: '#151c2b', border: '1px solid #2a3550', borderRadius: 8, fontSize: 12 } }

export default function Reports() {
  const { data: r, error, loading } = useLoad(() => api.get('/reports'))
  const camps = useLoad(() => api.get('/campaigns'))
  if (loading) return <Spinner />
  if (error) return <ErrorBox error={error} />
  const fp = r.verdicts
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-white">Reports and Analytics</h1>
        <p className="text-sm text-slate-400">Threat statistics, user risk, phishing campaigns, investigation history and where analysts say the signals are wrong.</p>
      </div>
      <div className="grid gap-5 lg:grid-cols-3">
        <Card title="New cases by risk band" className="lg:col-span-2">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={r.trend}>
              <CartesianGrid stroke="#2a3550" strokeDasharray="3 3" /><XAxis dataKey="day" stroke="#64748b" fontSize={11} /><YAxis stroke="#64748b" fontSize={11} allowDecimals={false} />
              <Tooltip {...tip} /><Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="critical" stackId="a" fill="#f43f5e" /><Bar dataKey="high" stackId="a" fill="#f97316" /><Bar dataKey="medium" stackId="a" fill="#fbbf24" /><Bar dataKey="low" stackId="a" fill="#34d399" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Analyst feedback">
          <div className="grid grid-cols-2 gap-3 text-center">
            <div className="rounded-lg bg-ink-900 p-3"><div className="text-2xl font-semibold text-rose-300">{fp.true_positive}</div><div className="text-xs text-slate-500">real threats</div></div>
            <div className="rounded-lg bg-ink-900 p-3"><div className="text-2xl font-semibold text-emerald-300">{fp.false_positive}</div><div className="text-xs text-slate-500">false alarms</div></div>
          </div>
          <p className="mt-3 text-xs text-slate-500">Mark cases on the Incident Response page. Signals that show up often in false alarms are the first to retune.</p>
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Phishing campaigns (same message, many recipients)">
          {!camps.data?.length ? <Empty>No campaigns.</Empty> : (
            <table className="w-full"><thead><tr><th className="th">Sender and subject</th><th className="th">Recipients</th><th className="th">Max score</th></tr></thead>
              <tbody className="divide-y divide-ink-600/40">{camps.data.map((c) => (
                <tr key={c.key}><td className="td"><div className="text-slate-200">{c.subject}</div><div className="text-xs text-slate-500">{c.sender} · {when(c.first_seen)}</div></td><td className="td text-white">{c.recipients}<div className="text-xs text-slate-500">{c.open_cases} open</div></td><td className="td"><Band band={c.max_email_score >= 60 ? 'high' : 'medium'} score={c.max_email_score} /></td></tr>
              ))}</tbody></table>
          )}
        </Card>
        <Card title="Evidence signals that drive cases">
          <table className="w-full"><thead><tr><th className="th">Signal</th><th className="th">Cases</th><th className="th">In false alarms</th></tr></thead>
            <tbody className="divide-y divide-ink-600/40">{r.signals.map((s) => (
              <tr key={s.code}><td className="td"><div className="text-slate-200">{s.label}</div><div className="font-mono text-[10px] text-slate-500">{s.code}</div></td><td className="td text-white">{s.cases}</td><td className="td text-slate-400">{s.false_positive_cases}</td></tr>
            ))}</tbody></table>
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="User risk report">
          <table className="w-full"><thead><tr><th className="th">User</th><th className="th">Department</th><th className="th">Highest score</th><th className="th">Cases</th></tr></thead>
            <tbody className="divide-y divide-ink-600/40">{r.risky_users.map((u) => (
              <tr key={u.user_id}><td className="td text-slate-200">{u.user}</td><td className="td text-slate-400">{u.dept}</td><td className="td"><Band band={u.max_score >= 80 ? 'critical' : u.max_score >= 60 ? 'high' : u.max_score >= 30 ? 'medium' : 'low'} score={u.max_score} /></td><td className="td text-slate-400">{u.cases}</td></tr>
            ))}</tbody></table>
        </Card>
        <Card title="By department">
          <table className="w-full"><thead><tr><th className="th">Department</th><th className="th">Cases</th><th className="th">High or critical</th></tr></thead>
            <tbody className="divide-y divide-ink-600/40">{r.departments.map((d) => (
              <tr key={d.dept}><td className="td text-slate-200">{d.dept}</td><td className="td text-slate-400">{d.cases}</td><td className="td text-white">{d.high_or_critical}</td></tr>
            ))}</tbody></table>
        </Card>
      </div>

      <Card title="Investigation history (audit log)">
        <table className="w-full">
          <thead><tr><th className="th">When</th><th className="th">Who</th><th className="th">What</th><th className="th">Case</th></tr></thead>
          <tbody className="divide-y divide-ink-600/40">{r.history.map((h, i) => (
            <tr key={i}><td className="td text-xs text-slate-500">{when(h.ts)}</td><td className="td text-xs text-slate-300">{h.actor} <span className="text-slate-500">({h.role})</span></td><td className="td text-xs text-slate-200">{h.event.replaceAll('_', ' ')}</td><td className="td text-xs">{h.case_id ? <Link className="text-sky-300" to={`/investigate/${h.case_id}`}>#{h.case_id}</Link> : ''}</td></tr>
          ))}</tbody>
        </table>
      </Card>
    </div>
  )
}
