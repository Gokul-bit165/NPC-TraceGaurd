import React, { useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Clock,
  HelpCircle,
  Info,
  Lock,
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
  const [ackError, setAckError] = useState('')

  const handleAck = async (alertId, answer) => {
    setSubmittingId(alertId)
    setAckError('')
    try {
      await api.post(`/me/alerts/${alertId}/ack`, { answer })
      setToastMessage(
        answer === 'it_was_me'
          ? 'Thank you for confirming your sign-in activity.'
          : 'Security team notified: you reported this activity was not you.'
      )
      await reload()
    } catch (e) {
      setAckError(errText(e))
    } finally {
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

      <ErrorBox error={ackError} />

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
            const isBusy = submittingId === n.id

            return (
              <div
                key={n.id}
                className={`card rounded-2xl border p-5 shadow-lg transition duration-200 ${
                  isPending
                    ? 'border-sky-500/40 bg-ink-900/90 ring-1 ring-sky-500/20'
                    : isReportedNotSelf
                    ? 'border-rose-500/40 bg-rose-950/10'
                    : 'border-ink-600/60 bg-ink-900/50'
                }`}
              >
                {/* Alert Header */}
                <div className="flex items-start justify-between gap-3 border-b border-ink-600/50 pb-3">
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="text-xs uppercase font-bold tracking-wider text-sky-400">
                        Campus Security Check
                      </span>
                      {isPending && (
                        <span className="rounded-full bg-amber-400/20 px-2 py-0.5 text-[10px] font-bold text-amber-300 animate-pulse">
                          Action Required
                        </span>
                      )}
                    </div>
                    <h3 className="text-base font-bold text-slate-100">
                      {n.title || 'Security check: was this you?'}
                    </h3>
                  </div>

                  <div className="text-right text-xs text-slate-400 font-mono shrink-0">
                    {when(n.ts)}
                  </div>
                </div>

                {/* Message Body */}
                <div className="py-4">
                  <div className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-slate-200 select-text">
                    {n.body}
                  </div>
                </div>

                {/* Student Response State */}
                <div className="border-t border-ink-600/50 pt-4">
                  {isPending ? (
                    <div className="space-y-3">
                      <div className="text-xs font-semibold text-slate-300">
                        Please confirm whether this activity was initiated by you:
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <button
                          type="button"
                          disabled={isBusy}
                          onClick={() => handleAck(n.id, 'it_was_me')}
                          className="btn btn-ok justify-center !py-3 text-sm font-semibold rounded-xl shadow-md hover:scale-[1.01] transition"
                        >
                          <CheckCircle2 size={18} />
                          <span>Yes, it was me</span>
                        </button>
                        <button
                          type="button"
                          disabled={isBusy}
                          onClick={() => handleAck(n.id, 'not_me')}
                          className="btn btn-bad justify-center !py-3 text-sm font-semibold rounded-xl shadow-md hover:scale-[1.01] transition"
                        >
                          <AlertTriangle size={18} />
                          <span>No, it was not me</span>
                        </button>
                      </div>
                    </div>
                  ) : isConfirmedSelf ? (
                    <div className="rounded-xl border border-emerald-500/40 bg-emerald-950/20 p-3.5 text-xs text-emerald-200 space-y-1">
                      <div className="flex items-center gap-1.5 font-bold text-emerald-300 text-sm">
                        <CheckCircle2 size={16} />
                        <span>You confirmed: "Yes, it was me"</span>
                      </div>
                      <p className="leading-relaxed text-emerald-200/90">
                        Your response has been logged by the security team. If you travel or switch devices in the future, these checks help keep your account secure.
                      </p>
                    </div>
                  ) : (
                    <div className="rounded-xl border border-rose-500/40 bg-rose-950/25 p-4 text-xs text-rose-200 space-y-2.5">
                      <div className="flex items-center gap-2 font-bold text-rose-300 text-sm">
                        <AlertCircle size={18} />
                        <span>You reported: "No, it was not me"</span>
                      </div>

                      <p className="text-slate-200 leading-relaxed font-medium">
                        The campus security team has been notified and is currently investigating this unauthorized access.
                      </p>

                      <div className="space-y-2 pt-1 border-t border-rose-500/30">
                        <div className="font-bold text-slate-100 text-xs uppercase tracking-wide">
                          Important Next Steps for Your Account:
                        </div>
                        <ul className="space-y-1.5 list-disc pl-4 text-slate-300">
                          <li>
                            <b>Contact IT Support:</b> Reach out to the campus IT service desk immediately via your campus directory or support portal.
                          </li>
                          <li>
                            <b>Change your password:</b> Go directly to the official campus single sign-on page (<span className="text-sky-300 font-mono">sso.kestrel.edu</span>) from a trusted device and update your password.
                          </li>
                          <li>
                            <b>Await security investigation:</b> Do not click any links in suspicious emails. The security operations center will follow up if additional account verification is required.
                          </li>
                          <li>
                            <b>Official policy reminder:</b> Campus IT will never ask for your password via email or text message.
                          </li>
                        </ul>
                      </div>
                    </div>
                  )}
                </div>
              </div>
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
