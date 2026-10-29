import React from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { Bell, FileSearch, KeyRound, LayoutDashboard, LineChart, Mail, ShieldAlert, ShieldCheck, FlaskConical } from 'lucide-react'
import { ROLES, getRole, setRole } from './api.js'
import Dashboard from './pages/Dashboard.jsx'
import PhishingEmail from './pages/PhishingEmail.jsx'
import Logins from './pages/Logins.jsx'
import Investigation from './pages/Investigation.jsx'
import Response from './pages/Response.jsx'
import Reports from './pages/Reports.jsx'
import Evaluation from './pages/Evaluation.jsx'
import MyAlerts from './pages/MyAlerts.jsx'

const NAV = [
  ['/', 'Security Dashboard', LayoutDashboard],
  ['/email', 'Phishing Email', Mail],
  ['/logins', 'Suspicious Logins', KeyRound],
  ['/investigate', 'AI Investigation', FileSearch],
  ['/response', 'Incident Response', ShieldAlert],
  ['/reports', 'Reports & Analytics', LineChart],
  ['/evaluation', 'Evaluation', FlaskConical],
]

export default function App() {
  const [role, setRoleState] = React.useState(getRole())
  const switchRole = (r) => { setRole(r); setRoleState(r); window.location.assign(r === 'user' ? '/my-alerts' : '/') }

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-60 shrink-0 border-r border-ink-600/60 bg-ink-900 md:block">
        <div className="flex items-center gap-2 px-5 py-5">
          <ShieldCheck className="text-sky-400" />
          <div>
            <div className="text-lg font-bold leading-none text-white">TraceGuard</div>
            <div className="text-[11px] text-slate-500">Phishing + login investigation</div>
          </div>
        </div>
        <nav className="space-y-0.5 px-3">
          {role === 'user' ? (
            <SideLink to="/my-alerts" label="My Security Alerts" Icon={Bell} />
          ) : NAV.map(([to, label, Icon]) => <SideLink key={to} to={to} label={label} Icon={Icon} />)}
        </nav>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-10 flex items-center justify-between border-b border-ink-600/60 bg-ink-950/90 px-6 py-3 backdrop-blur">
          <div className="text-sm text-slate-400">Kestrel University · campus security operations <span className="ml-2 rounded bg-ink-700 px-1.5 py-0.5 text-[10px] uppercase text-slate-400">demo data</span></div>
          <label className="flex items-center gap-2 text-xs text-slate-400">
            View as
            <select className="input !w-auto" value={role} onChange={(e) => switchRole(e.target.value)}>
              {Object.entries(ROLES).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </label>
        </header>
        <main className="mx-auto max-w-[1400px] p-6">
          <Routes>
            {role === 'user' ? (
              <>
                <Route path="/my-alerts" element={<MyAlerts />} />
                <Route path="*" element={<Navigate to="/my-alerts" replace />} />
              </>
            ) : (
              <>
                <Route path="/" element={<Dashboard />} />
                <Route path="/email" element={<PhishingEmail />} />
                <Route path="/logins" element={<Logins />} />
                <Route path="/investigate" element={<Investigation />} />
                <Route path="/investigate/:id" element={<Investigation />} />
                <Route path="/response" element={<Response />} />
                <Route path="/response/:id" element={<Response />} />
                <Route path="/reports" element={<Reports />} />
                <Route path="/evaluation" element={<Evaluation />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </>
            )}
          </Routes>
        </main>
      </div>
    </div>
  )
}

function SideLink({ to, label, Icon }) {
  return (
    <NavLink to={to} end={to === '/'} className={({ isActive }) => `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm ${isActive ? 'bg-sky-600/20 text-sky-300' : 'text-slate-400 hover:bg-ink-800 hover:text-slate-200'}`}>
      <Icon size={17} /> {label}
    </NavLink>
  )
}
