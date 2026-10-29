import React, { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bell, ChevronDown, LogOut, Menu, ShieldAlert } from 'lucide-react'
import { ROLES } from '../api.js'
import { ThemeToggle } from '../theme.jsx'
import { Brand } from './Sidebar.jsx'

export default function Header({
  role,
  title,
  onSwitchRole,
  onToggleMobileMenu,
  onLogout,
  pendingApprovals = 0,
}) {
  const current = ROLES[role] || ROLES.analyst
  const [menuOpen, setMenuOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!menuOpen) return
    const close = (e) => {
      if (e.type === 'keydown' ? e.key === 'Escape' : !ref.current?.contains(e.target)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', close)
    }
  }, [menuOpen])

  return (
    <header className="app-header sticky top-0 z-30 flex h-16 items-center justify-between gap-3 border-b border-ink-600/70 bg-ink-950/90 px-4 backdrop-blur-md md:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onToggleMobileMenu}
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-ink-600 bg-ink-800 text-slate-400 hover:text-slate-100 md:hidden"
          aria-label="Open navigation menu"
        >
          <Menu size={18} />
        </button>
        <div className="md:hidden"><Brand collapsed /></div>
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold text-slate-100 sm:text-base">{title}</h2>
          <p className="hidden truncate text-xs text-slate-500 sm:block">Kestrel University · campus security operations</p>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {/* Only real pending approvals from the API; hidden when there are none. */}
        {role !== 'user' && (
          <Link
            to="/response"
            className="relative flex h-9 w-9 items-center justify-center rounded-lg border border-ink-600 bg-ink-800 text-slate-400 transition-colors hover:bg-ink-700 hover:text-slate-100"
            aria-label={pendingApprovals > 0 ? `${pendingApprovals} actions waiting for approval` : 'No actions waiting for approval'}
            title={pendingApprovals > 0 ? `${pendingApprovals} action${pendingApprovals === 1 ? '' : 's'} waiting for approval` : 'No actions waiting for approval'}
          >
            {pendingApprovals > 0 ? <ShieldAlert size={17} className="text-amber-400" /> : <Bell size={17} />}
            {pendingApprovals > 0 && (
              <span className="absolute -right-1 -top-1 min-w-[18px] rounded-full bg-amber-500 px-1 text-center text-[10px] font-bold leading-[18px] text-slate-950">
                {pendingApprovals > 99 ? '99+' : pendingApprovals}
              </span>
            )}
          </Link>
        )}

        <ThemeToggle />

        <div className="relative" ref={ref}>
          <button
            type="button"
            onClick={() => setMenuOpen((o) => !o)}
            className="flex h-9 items-center gap-2 rounded-lg border border-ink-600 bg-ink-800 pl-1.5 pr-2 transition-colors hover:bg-ink-700"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
          >
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-sky-600 text-xs font-semibold text-white">
              {current.name.charAt(0)}
            </span>
            <span className="hidden text-left leading-tight lg:block">
              <span className="block text-xs font-semibold text-slate-100">{current.name}</span>
              <span className="block text-[10px] text-slate-400">{current.label}</span>
            </span>
            <ChevronDown size={14} className="text-slate-400" />
          </button>

          {menuOpen && (
            <div role="menu" className="absolute right-0 top-11 w-64 overflow-hidden rounded-xl border border-ink-600 bg-ink-800 shadow-pop animate-fade-in">
              <div className="border-b border-ink-600/70 px-4 py-3">
                <div className="text-sm font-semibold text-slate-100">{current.name}</div>
                <div className="text-xs text-slate-400">{current.label}</div>
              </div>
              <div className="p-2">
                <div className="px-2 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">View as</div>
                {Object.entries(ROLES).map(([k, v]) => (
                  <button
                    key={k}
                    type="button"
                    role="menuitemradio"
                    aria-checked={k === role}
                    onClick={() => { setMenuOpen(false); if (k !== role) onSwitchRole(k) }}
                    className={`flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-xs transition-colors hover:bg-ink-700 ${k === role ? 'text-sky-400' : 'text-slate-300'}`}
                  >
                    <span>
                      <span className="block font-medium">{v.label}</span>
                      <span className="block text-[11px] text-slate-500">{v.name}</span>
                    </span>
                    {k === role && <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />}
                  </button>
                ))}
              </div>
              <div className="border-t border-ink-600/70 p-2">
                <button
                  type="button"
                  role="menuitem"
                  onClick={onLogout}
                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-xs font-medium text-rose-400 transition-colors hover:bg-rose-500/10"
                >
                  <LogOut size={14} /> Sign out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
