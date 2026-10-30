import React from 'react'
import { NavLink } from 'react-router-dom'
import {
  Bell,
  ChevronsLeft,
  ChevronsRight,
  FileSearch,
  KeyRound,
  LayoutDashboard,
  LineChart,
  Inbox,
  ShieldAlert,
  ShieldCheck,
  X,
} from 'lucide-react'

// [path, label, icon]. Paths are the app's existing routes; /dashboard and /phishing are redirect aliases in App.jsx.
export const NAV_ITEMS = [
  ['/', 'Security Dashboard', LayoutDashboard],
  ['/mailbox', 'Mailbox', Inbox],
  ['/logins', 'Suspicious Logins', KeyRound],
  ['/investigate', 'AI Investigation', FileSearch],
  ['/response', 'Incident Response', ShieldAlert],
  ['/reports', 'Reports & Analytics', LineChart],
]
export const STUDENT_NAV = [['/my-alerts', 'My Alerts', Bell]]

export function Brand({ collapsed = false }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-sky-500 to-cyan-600 text-white shadow-sm">
        <ShieldCheck size={20} />
      </div>
      {!collapsed && (
        <div className="min-w-0">
          <div className="text-[15px] font-bold leading-tight tracking-[0.12em] text-slate-100">TRACEGUARD</div>
          <div className="truncate text-[11px] text-slate-400">Threat detection &amp; response</div>
        </div>
      )}
    </div>
  )
}

export default function Sidebar({ role, isOpen, onClose, collapsed, onToggleCollapsed }) {
  const items = role === 'user' ? STUDENT_NAV : NAV_ITEMS

  const nav = (isCollapsed, mobile) => (
    <div className="flex h-full flex-col">
      <div className={`flex h-16 shrink-0 items-center border-b border-ink-600/70 ${isCollapsed ? 'justify-center px-2' : 'justify-between px-4'}`}>
        <Brand collapsed={isCollapsed} />
        {mobile && (
          <button type="button" onClick={onClose} className="rounded-md p-1 text-slate-400 hover:text-slate-100" aria-label="Close navigation">
            <X size={20} />
          </button>
        )}
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4" aria-label="Primary">
        {items.map(([to, label, Icon]) => (
          <SideLink key={to} to={to} label={label} Icon={Icon} collapsed={isCollapsed} onClick={onClose} />
        ))}
      </nav>

      <div className="shrink-0 border-t border-ink-600/70 p-3">
        {!isCollapsed && (
          <div className="mb-2 rounded-lg border border-ink-600/70 bg-ink-900 p-2.5">
            <div className="flex items-center gap-2 text-xs font-medium text-slate-300">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              Detection engine online
            </div>
            <p className="mt-1 text-[11px] leading-snug text-slate-500">Mail: live Gmail via n8n. Sign-ins: simulated (no identity provider connected).</p>
          </div>
        )}
        {!mobile && (
          <button
            type="button"
            onClick={onToggleCollapsed}
            className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-slate-400 transition-colors hover:bg-ink-700 hover:text-slate-100 ${isCollapsed ? 'justify-center' : ''}`}
            aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {isCollapsed ? <ChevronsRight size={16} /> : <><ChevronsLeft size={16} /> Collapse</>}
          </button>
        )}
      </div>
    </div>
  )

  return (
    <>
      <aside
        className={`sticky top-0 hidden h-screen shrink-0 border-r border-ink-600/70 bg-sidebar transition-[width] duration-200 md:block ${collapsed ? 'w-[72px]' : 'w-64'}`}
      >
        {nav(collapsed, false)}
      </aside>

      {isOpen && (
        <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-slate-950/60 backdrop-blur-sm" onClick={onClose} />
          <aside className="relative h-full w-72 max-w-[85vw] border-r border-ink-600/70 bg-sidebar shadow-pop animate-slide-in">
            {nav(false, true)}
          </aside>
        </div>
      )}
    </>
  )
}

function SideLink({ to, label, Icon, collapsed, onClick }) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      onClick={onClick}
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        `group flex items-center gap-3 rounded-lg py-2.5 text-sm font-medium transition-colors ${collapsed ? 'justify-center px-2' : 'px-3'} ${
          isActive ? 'bg-sky-500/10 text-sky-300 shadow-[inset_2px_0_0_rgb(var(--sky-500))]' : 'text-slate-400 hover:bg-ink-700/70 hover:text-slate-100'
        }`
      }
    >
      {() => (
        <>
          <Icon size={18} className="shrink-0" />
          {!collapsed && <span className="truncate">{label}</span>}
        </>
      )}
    </NavLink>
  )
}
