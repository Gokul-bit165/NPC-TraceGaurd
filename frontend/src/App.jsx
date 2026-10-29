import React, { useState, useEffect } from 'react'
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Compass } from 'lucide-react'
import api, { getRole, setRole, homeFor, isSignedIn, signOut } from './api.js'
import Sidebar, { NAV_ITEMS, STUDENT_NAV } from './components/Sidebar.jsx'
import Header from './components/Header.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import EmptyState from './components/EmptyState.jsx'
import Login from './pages/Login.jsx'
import Dashboard from './pages/Dashboard.jsx'
import PhishingEmail from './pages/PhishingEmail.jsx'
import Logins from './pages/Logins.jsx'
import Investigation from './pages/Investigation.jsx'
import Response from './pages/Response.jsx'
import Reports from './pages/Reports.jsx'
import Evaluation from './pages/Evaluation.jsx'
import MyAlerts from './pages/MyAlerts.jsx'

const COLLAPSE_KEY = 'tg_sidebar_collapsed'

function titleFor(pathname, role) {
  const items = role === 'user' ? STUDENT_NAV : NAV_ITEMS
  const hit = items.find(([to]) => (to === '/' ? pathname === '/' : pathname === to || pathname.startsWith(`${to}/`)))
  return hit ? hit[1] : 'Page not found'
}

function NotFound({ role }) {
  return (
    <div className="card mx-auto mt-10 max-w-md">
      <EmptyState
        icon={Compass}
        title="Page not found"
        message="This address does not match any TraceGuard page."
      />
      <div className="pb-8 text-center">
        <Link to={homeFor(role)} className="btn btn-primary">Back to {role === 'user' ? 'My Alerts' : 'Dashboard'}</Link>
      </div>
    </div>
  )
}

function Shell({ role, setRoleState }) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(COLLAPSE_KEY) === '1' } catch { return false }
  })
  const [pendingApprovals, setPendingApprovals] = useState(0)
  const location = useLocation()
  const navigate = useNavigate()

  useEffect(() => { setMobileMenuOpen(false) }, [location.pathname])

  // Pending approvals count for security staff; real API data only.
  useEffect(() => {
    if (role === 'user') { setPendingApprovals(0); return }
    let active = true
    api.get('/overview')
      .then((res) => {
        if (!active) return
        setPendingApprovals(res.data?.action_needed?.reduce((acc, c) => acc + (c.pending_approvals || 0), 0) || 0)
      })
      .catch(() => { if (active) setPendingApprovals(0) })
    return () => { active = false }
  }, [role, location.pathname])

  const toggleCollapsed = () => {
    setCollapsed((c) => {
      try { localStorage.setItem(COLLAPSE_KEY, c ? '0' : '1') } catch { /* non-fatal */ }
      return !c
    })
  }

  const switchRole = (next) => {
    setRole(next)
    setRoleState(next)
    navigate(homeFor(next), { replace: true })
  }

  const logout = () => {
    signOut()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex min-h-screen bg-ink-950 text-slate-200">
      <Sidebar
        role={role}
        isOpen={mobileMenuOpen}
        onClose={() => setMobileMenuOpen(false)}
        collapsed={collapsed}
        onToggleCollapsed={toggleCollapsed}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          role={role}
          title={titleFor(location.pathname, role)}
          onSwitchRole={switchRole}
          onToggleMobileMenu={() => setMobileMenuOpen((o) => !o)}
          onLogout={logout}
          pendingApprovals={pendingApprovals}
        />

        <main className="mx-auto w-full max-w-[1440px] flex-1 p-4 md:p-6 lg:p-8">
          <ErrorBoundary resetKey={location.pathname}>
            <Routes>
              {role === 'user' ? (
                <>
                  <Route path="/my-alerts" element={<MyAlerts />} />
                  <Route path="/" element={<Navigate to="/my-alerts" replace />} />
                  <Route path="*" element={<NotFound role={role} />} />
                </>
              ) : (
                <>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/dashboard" element={<Navigate to="/" replace />} />
                  <Route path="/email" element={<PhishingEmail />} />
                  <Route path="/phishing" element={<Navigate to="/email" replace />} />
                  <Route path="/logins" element={<Logins />} />
                  <Route path="/investigate" element={<Investigation />} />
                  <Route path="/investigate/:id" element={<Investigation />} />
                  <Route path="/response" element={<Response />} />
                  <Route path="/response/:id" element={<Response />} />
                  <Route path="/reports" element={<Reports />} />
                  <Route path="/evaluation" element={<Evaluation />} />
                  <Route path="/my-alerts" element={<Navigate to="/" replace />} />
                  <Route path="*" element={<NotFound role={role} />} />
                </>
              )}
            </Routes>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  )
}

export default function App() {
  const [role, setRoleState] = useState(getRole())
  const location = useLocation()
  const signedIn = isSignedIn()

  // Keep the role in sync if another tab changed it or the session was cleared.
  useEffect(() => { setRoleState(getRole()) }, [location.pathname])

  if (location.pathname === '/login') {
    return signedIn
      ? <Navigate to={location.state?.from || homeFor(role)} replace />
      : <Login onSignedIn={(r) => setRoleState(r)} />
  }

  if (!signedIn) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }

  return <Shell role={role} setRoleState={setRoleState} />
}
