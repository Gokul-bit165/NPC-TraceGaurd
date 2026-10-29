import React from 'react'
import { Bell, CheckCircle2, Mail, MessageSquare, Send, X } from 'lucide-react'
import api, { errText } from '../api.js'
import { Chip, ErrorBox, Spinner, when } from '../ui.jsx'

export default function DailySummaryModal({ onClose }) {
  const [summaryData, setSummaryData] = React.useState(null)
  const [sentList, setSentList] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const [sending, setSending] = React.useState(false)
  const [channel, setChannel] = React.useState('both')
  const [error, setError] = React.useState(null)
  const [sentFeedback, setSentFeedback] = React.useState(null)

  const loadData = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [sumRes, sentRes] = await Promise.all([
        api.get('/notifications/daily-summary'),
        api.get('/notifications/sent'),
      ])
      setSummaryData(sumRes.data)
      setSentList(sentRes.data.messages || [])
    } catch (e) {
      setError(errText(e))
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    loadData()
  }, [loadData])

  const handleSend = async () => {
    setSending(true)
    setError(null)
    setSentFeedback(null)
    try {
      const res = await api.post('/notifications/daily-summary', { channel })
      setSentFeedback(`Successfully dispatched daily summary (${res.data.sent} notification messages delivered to analyst pool).`)
      await loadData()
    } catch (e) {
      setError(errText(e))
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-4xl flex-col rounded-2xl border border-ink-600 bg-ink-950 shadow-2xl">
        {/* Header */}
        <header className="flex items-center justify-between border-b border-ink-600/70 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-sky-500/20 text-sky-400">
              <Bell size={20} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white">Analyst Notifications & Daily Summary</h2>
              <p className="text-xs text-slate-400">Real-time alerts for High & Critical incidents and automated daily SOC digest</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 transition hover:bg-ink-700 hover:text-white"
          >
            <X size={20} />
          </button>
        </header>

        {/* Content */}
        <div className="flex-1 space-y-5 overflow-y-auto p-6">
          {loading && !summaryData && <Spinner />}
          {error && <ErrorBox error={error} />}
          {sentFeedback && (
            <div className="flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm text-emerald-300">
              <CheckCircle2 size={16} />
              <span>{sentFeedback}</span>
            </div>
          )}

          {summaryData && (
            <>
              {/* Daily Summary Preview */}
              <div className="rounded-xl border border-ink-700 bg-ink-900/60 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-ink-800 pb-3">
                  <div>
                    <h3 className="text-sm font-semibold text-slate-200">Daily Threat Summary Briefing</h3>
                    <div className="text-xs text-slate-500">Date: {summaryData.meta?.date} · High/Critical Cases: {summaryData.meta?.critical_cases + summaryData.meta?.high_cases}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <select
                      className="input !w-auto text-xs"
                      value={channel}
                      onChange={(e) => setChannel(e.target.value)}
                    >
                      <option value="both">Dispatch: Email & Chat</option>
                      <option value="email">Dispatch: Email Only</option>
                      <option value="chat">Dispatch: Chat Webhook Only</option>
                    </select>
                    <button
                      type="button"
                      disabled={sending}
                      onClick={handleSend}
                      className="btn btn-primary text-xs"
                    >
                      <Send size={13} />
                      Send to Analysts Now
                    </button>
                  </div>
                </div>

                <pre className="mt-3 whitespace-pre-wrap rounded-lg bg-ink-950 p-3 font-mono text-xs leading-relaxed text-slate-300 border border-ink-800/80">
                  {summaryData.summary}
                </pre>
              </div>

              {/* Sent Notifications Log */}
              <div>
                <div className="flex items-center justify-between pb-2">
                  <h3 className="text-sm font-semibold text-white">Dispatched Analyst Notifications Log</h3>
                  <span className="text-xs text-slate-400">{sentList.length} total messages dispatched (in-memory test sender)</span>
                </div>

                {sentList.length === 0 ? (
                  <div className="rounded-xl border border-ink-800 bg-ink-900/40 p-4 text-center text-xs text-slate-500">
                    No notifications dispatched yet in this session.
                  </div>
                ) : (
                  <div className="max-h-64 overflow-y-auto rounded-xl border border-ink-700 bg-ink-900/70">
                    <table className="w-full text-left text-xs">
                      <thead className="sticky top-0 bg-ink-900 border-b border-ink-700 text-slate-400">
                        <tr>
                          <th className="p-2.5 pl-3">Channel</th>
                          <th className="p-2.5">Recipient</th>
                          <th className="p-2.5">Subject</th>
                          <th className="p-2.5">Timestamp</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-ink-800">
                        {sentList.map((m, idx) => (
                          <tr key={idx} className="hover:bg-ink-800/50">
                            <td className="p-2.5 pl-3">
                              {m.channel === 'email' ? (
                                <Chip tone="sky"><Mail size={11} className="inline mr-1" />email</Chip>
                              ) : (
                                <Chip tone="violet"><MessageSquare size={11} className="inline mr-1" />chat</Chip>
                              )}
                            </td>
                            <td className="p-2.5 font-medium text-slate-300">{m.recipient}</td>
                            <td className="p-2.5 text-slate-200">
                              <div>{m.subject}</div>
                              <div className="text-[11px] text-slate-400 truncate max-w-md">{m.body}</div>
                            </td>
                            <td className="p-2.5 text-slate-400">{when(m.timestamp)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <footer className="flex justify-end border-t border-ink-600/70 bg-ink-900/60 px-6 py-3">
          <button
            type="button"
            onClick={onClose}
            className="btn btn-ghost text-xs"
          >
            Close
          </button>
        </footer>
      </div>
    </div>
  )
}
