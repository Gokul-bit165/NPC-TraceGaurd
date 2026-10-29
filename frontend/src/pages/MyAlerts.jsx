import React, { useRef, useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Clock,
  HelpCircle,
  Loader2,
  PhoneCall,
  ShieldAlert,
  ShieldCheck,
  User,
  XCircle,
} from 'lucide-react'
import api, { errText } from '../api.js'
import {
  Card,
  Chip,
  Empty,
  ErrorBox,
  NotificationToast,
  PageHeader,
  Spinner,
  when,
} from '../ui.jsx'
import { useApi } from '../hooks/useApi.js'

export default function MyAlerts() {
  const { data, error, loading, reload } = useApi(() => api.get('/me/alerts'))
  const [submittingId, setSubmittingId] = useState(null)
  const [toastMessage, setToastMessage] = useState(null)
  const [ackError, setAckError] = useState(null) // { id, message }
  const inFlight = useRef(false) // blocks a double click before React re-renders the disabled buttons

  const handleAck = async (alertId, answer) => {
    if (inFlight.current) return
    inFlight.current = true
    setSubmittingId({ id: alertId, answer })
    setAckError(null)
    try {
      await api.post(`/me/alerts/${alertId}/ack`, { answer })
      setToastMessage(answer === 'it_was_me' ? 'Login confirmed as you.' : 'Login reported as unrecognized.')
      await reload()
    } catch (e) {
      setAckError({ id: alertId, message: errText(e) })
    } finally {
      inFlight.current = false
      setSubmittingId(null)
    }
  }
  if (loading && !data) return <Spinner message="Checking security alerts for your account…" />
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />

  const user = data?.user || { name: 'Student' }
  const items = data?.items || []

  return (
    <div className="mx-auto max-w-2xl space-y-6 pb-12">
      <NotificationToast
        show={!!toastMessage}
        message={toastMessage}
        type="info"
        onClose={() => setToastMessage(null)}
      />

      {/* Header Banner */}
      <div className="space-y-1">
        <h1 className="flex items-center gap-2.5 text-2xl font-bold tracking-tight text-slate-100">
          <ShieldCheck className="text-sky-400 shrink-0" size={28} />
          <span>My Security Alerts</span>
        </h1>
        <p className="text-sm text-slate-400">
          Hi <b className="text-slate-200">{user.name}</b>. These are official notifications from campus IT security regarding activity on your student/staff account.
        </p>
      </div>

      {items.length === 0 ? (
        <Card className="text-center py-12">
          <div className="flex h-14 w-14 mx-auto items-center justify-center rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 mb-3">
            <CheckCircle2 size={32} />
          </div>
          <h3 className="text-base font-semibold text-slate-200">
            No Security Alerts
          </h3>
          <p className="mt-1 text-xs text-slate-400 max-w-sm mx-auto">
            Your account looks normal. There are no suspicious sign-ins or phishing alerts requiring your attention right now.
          </p>
        </Card>
      ) : (
        <div className="space-y-5">
          {items.map((n) => {
            const isPending = !n.acknowledged
            const isConfirmedSelf = n.acknowledged === 'it_was_me'
            const isReportedNotSelf = n.acknowledged === 'not_me'
            const busyHere = submittingId?.id === n.id
            const anyBusy = submittingId !== null
            const failed = ackError?.id === n.id ? ackError.message : null

            return (
              <section
                key={n.id}
                aria-busy={busyHere}
                className={`card p-5 ${isPending ? 'border-sky-500/40' : ''}`}
              >
                {/* Alert header */}
                <div className="flex items-start justify-between gap-3 border-b border-ink-600/50 pb-3">
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="eyebrow !text-sky-400">Campus Security Check</span>
                      {isPending && (
                        <span className="rounded-full border border-amber-400/40 bg-amber-400/10 px-2 py-0.5 text-[10px] font-semibold text-amber-300">
                          Awaiting your response
                        </span>
                      )}
                    </div>
                    <h3 className="text-base font-semibold text-slate-100">
                      {n.title || 'Security check: was this you?'}
                    </h3>
                  </div>
                  <div className="shrink-0 text-right font-mono text-xs text-slate-400">{when(n.ts)}</div>
                </div>

                {/* Notification message (location, device and time details are part of the message text) */}
                <div className="whitespace-pre-wrap py-4 text-sm leading-relaxed text-slate-200 select-text">
                  {n.body}
                </div>

                {/* Student response */}
                <div className="border-t border-ink-600/50 pt-4">
                  {isPending ? (
                    <div className="space-y-3">
                      <div className="text-xs font-semibold text-slate-300">Did you sign in with this activity?</div>
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        <button
                          type="button"
                          disabled={anyBusy}
                          onClick={() => handleAck(n.id, 'it_was_me')}
                          className="btn btn-ok flex-col !gap-0.5 !py-3 text-sm font-semibold"
                        >
                          <span className="inline-flex items-center gap-2">
                            {busyHere && submittingId.answer === 'it_was_me' ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
                            I am in
                          </span>
                          <span className="text-[11px] font-normal text-white/80">This sign-in was me</span>
                        </button>
                        <button
                          type="button"
                          disabled={anyBusy}
                          onClick={() => handleAck(n.id, 'not_me')}
                          className="btn flex-col !gap-0.5 border border-rose-500/50 bg-rose-500/10 !py-3 text-sm font-semibold text-rose-300 hover:bg-rose-500/20"
                        >
                          <span className="inline-flex items-center gap-2">
                            {busyHere && submittingId.answer === 'not_me' ? <Loader2 size={16} className="animate-spin" /> : <AlertTriangle size={16} />}
                            I am not in
                          </span>
                          <span className="text-[11px] font-normal text-rose-300/80">This sign-in was not me</span>
                        </button>
                      </div>
                      {busyHere && <p className="text-xs text-slate-400" role="status">Submitting your response…</p>}
                      {failed && (
                        <div role="alert" className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
                          Your response was not recorded: {failed} You can try again.
                        </div>
                      )}
                    </div>
                  ) : isConfirmedSelf ? (
                    <div role="status" className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3.5">
                      <div className="flex items-center gap-2 text-sm font-semibold text-emerald-300">
                        <CheckCircle2 size={16} />
                        Login confirmed
                      </div>
                      <p className="mt-1 text-xs leading-relaxed text-slate-300">
                        This activity has been reported as legitimate.
                      </p>
                    </div>
                  ) : (
                    <div role="status" className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3.5">
                      <div className="flex items-center gap-2 text-sm font-semibold text-rose-300">
                        <AlertCircle size={16} />
                        Login reported as unrecognized
                      </div>
                      <p className="mt-1 text-xs leading-relaxed text-slate-300">
                        Your response has been recorded. Contact campus IT security immediately.
                      </p>
                      <ul className="mt-3 list-disc space-y-1.5 border-t border-rose-500/30 pt-3 pl-4 text-xs text-slate-300">
                        <li><b>Contact IT Support</b> through the campus IT service desk.</li>
                        <li><b>Change your password</b> from a trusted device, using the official campus single sign-on page.</li>
                        <li>Do not click links in suspicious emails. Campus IT will never ask for your password by email or text.</li>
                      </ul>
                    </div>
                  )}
                </div>
              </section>
            )
          })}
        </div>
      )}
      {/* Safety Help Card */}
      <div className="rounded-xl border border-ink-600/60 bg-ink-900/60 p-4 text-xs text-slate-400 space-y-1.5">
        <div className="flex items-center gap-1.5 font-semibold text-slate-300">
          <HelpCircle size={14} className="text-sky-400" />
          <span>Need help or suspect your account is compromised?</span>
        </div>
        <p className="leading-relaxed">
          Call the Kestrel University IT Help Desk at <span className="font-mono text-slate-200">(555) 019-8200</span> or visit the IT Support Center in the Student Union building (Mon–Fri 8 AM – 6 PM).
        </p>
      </div>
    </div>
  )
}
