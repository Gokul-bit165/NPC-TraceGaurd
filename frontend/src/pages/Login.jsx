import React, { useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Activity, Check, FileSearch, Loader2, LogIn, Mail, ShieldCheck } from 'lucide-react'
import api, { ROLES, errText, getRole, homeFor, markSignedIn, setRole } from '../api.js'
import { ThemeToggle } from '../theme.jsx'

const DESCRIPTIONS = {
  admin: 'Full access, including scoring configuration and ingest.',
  analyst: 'Triage incidents, review evidence and approve response actions.',
  user: 'See security notices about your own account and respond to them.',
}

const FEATURES = [
  { icon: Mail, text: 'Phishing email analysis with explainable evidence' },
  { icon: Activity, text: 'Login behaviour checked against each user’s baseline' },
  { icon: FileSearch, text: 'One correlated, graded incident per user, not two alerts' },
]

export default function Login({ onSignedIn }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [selected, setSelected] = useState(getRole())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const submitting = useRef(false)

  const submit = async (e) => {
    e.preventDefault()
    if (submitting.current) return // blocks a double Enter / double click
    if (!ROLES[selected]) {
      setError('Choose an account to continue.')
      return
    }
    submitting.current = true
    setBusy(true)
    setError('')
    try {
      // Same mechanism the app already uses: the chosen identity is sent as request headers.
      setRole(selected)
      await api.get('/health')
      markSignedIn()
      onSignedIn?.(selected)
      const from = location.state?.from
      navigate(selected === 'user' || !from || from === '/login' ? homeFor(selected) : from, { replace: true })
    } catch (err) {
      setError(errText(err))
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-screen bg-ink-950 text-slate-200 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
      {/* Branding */}
      <section className="relative hidden flex-col justify-between overflow-hidden border-r border-ink-600/70 bg-sidebar p-12 lg:flex">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-[0.5]"
          style={{
            backgroundImage: 'linear-gradient(rgb(var(--ink-600) / 0.35) 1px, transparent 1px), linear-gradient(90deg, rgb(var(--ink-600) / 0.35) 1px, transparent 1px)',
            backgroundSize: '44px 44px',
            maskImage: 'radial-gradient(ellipse at 30% 20%, black, transparent 70%)',
            WebkitMaskImage: 'radial-gradient(ellipse at 30% 20%, black, transparent 70%)',
          }}
        />
        <div className="relative flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500 to-cyan-600 text-white shadow-sm">
            <ShieldCheck size={24} />
          </div>
          <span className="text-xl font-bold tracking-[0.14em] text-slate-100">TRACEGUARD</span>
        </div>

        <div className="relative max-w-lg">
          <h1 className="text-4xl font-semibold leading-tight tracking-tight text-slate-100">
            AI-Powered Security Threat Detection
          </h1>
          <p className="mt-4 text-base leading-relaxed text-slate-400">
            Protect your organization with intelligent threat detection, security investigations, and incident response.
          </p>
          <ul className="mt-8 space-y-4">
            {FEATURES.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-start gap-3 text-sm text-slate-300">
                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-ink-600 bg-ink-800 text-sky-400">
                  <Icon size={16} />
                </span>
                <span className="pt-1.5">{text}</span>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-slate-500">Kestrel University demo environment. All data is synthetic.</p>
      </section>

      {/* Form */}
      <section className="relative flex flex-col px-4 py-6 sm:px-8">
        <div className="flex justify-end"><ThemeToggle /></div>

        <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center py-8">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-sky-600 text-white"><ShieldCheck size={22} /></div>
            <div>
              <div className="text-lg font-semibold leading-tight tracking-tight text-slate-100">TRACEGUARD</div>
              <div className="text-xs text-slate-400">AI-Powered Security Threat Detection</div>
            </div>
          </div>

          <h2 className="text-2xl font-semibold tracking-tight text-slate-100">Sign in</h2>
          <p className="mt-1.5 text-sm text-slate-400">Choose the account you want to use for this session.</p>

          <form onSubmit={submit} className="mt-6 space-y-5" noValidate>
            <fieldset disabled={busy} className="space-y-2.5">
              <legend className="label">Account</legend>
              {Object.entries(ROLES).map(([key, r]) => {
                const active = selected === key
                return (
                  <label
                    key={key}
                    className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3.5 transition-colors ${
                      active ? 'border-sky-500 bg-sky-500/10' : 'border-ink-600 bg-ink-800 hover:border-slate-500'
                    } focus-within:ring-2 focus-within:ring-sky-500/60`}
                  >
                    <input
                      type="radio"
                      name="account"
                      value={key}
                      checked={active}
                      onChange={() => { setSelected(key); setError('') }}
                      className="sr-only"
                    />
                    <span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${active ? 'border-sky-500 bg-sky-600 text-white' : 'border-ink-600'}`}>
                      {active && <Check size={12} strokeWidth={3} />}
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold text-slate-100">{r.name}</span>
                      <span className="block text-xs font-medium text-sky-400">{r.label}</span>
                      <span className="mt-0.5 block text-xs leading-snug text-slate-400">{DESCRIPTIONS[key]}</span>
                    </span>
                  </label>
                )
              })}
            </fieldset>

            {error && (
              <div role="alert" className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3.5 py-2.5 text-sm text-rose-300">
                {error}
              </div>
            )}

            <button type="submit" disabled={busy} className="btn btn-primary w-full !py-2.5 text-sm">
              {busy ? <Loader2 size={16} className="animate-spin" /> : <LogIn size={16} />}
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          <p className="mt-6 rounded-lg border border-ink-600 bg-ink-800 p-3 text-xs leading-relaxed text-slate-400">
            <span className="font-semibold text-slate-300">Demo sign-in.</span> This build has no password check: the API trusts the selected
            role. A real deployment sits behind campus single sign-on.
          </p>
        </div>
      </section>
    </div>
  )
}
