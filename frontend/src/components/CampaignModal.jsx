import React from 'react'
import { Link } from 'react-router-dom'
import { AlertCircle, AlertTriangle, Check, CheckCircle2, Link2, Mail, RotateCcw, Shield, Trash2, Users, X } from 'lucide-react'
import api, { errText } from '../api.js'
import { Band, Chip, ErrorBox, Spinner, when } from '../ui.jsx'

export default function CampaignModal({ campaignKey, onClose, onSuccess }) {
  const [data, setData] = React.useState(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState(null)
  const [selectedUsers, setSelectedUsers] = React.useState(new Set())
  const [note, setNote] = React.useState('')
  const [busy, setBusy] = React.useState(false)
  const [resultMsg, setResultMsg] = React.useState(null)

  const loadDetails = React.useCallback(async () => {
    if (!campaignKey) return
    setLoading(true)
    setError(null)
    try {
      const res = await api.get(`/campaigns/${encodeURIComponent(campaignKey)}`)
      setData(res.data)
      // By default select all recipients
      setSelectedUsers(new Set(res.data.recipients.map((r) => r.user_id)))
    } catch (e) {
      setError(errText(e))
    } finally {
      setLoading(false)
    }
  }, [campaignKey])

  React.useEffect(() => {
    loadDetails()
  }, [loadDetails])

  if (!campaignKey) return null

  const toggleUser = (userId) => {
    setSelectedUsers((prev) => {
      const next = new Set(prev)
      if (next.has(userId)) next.delete(userId)
      else next.add(userId)
      return next
    })
  }

  const selectAll = () => {
    if (!data) return
    setSelectedUsers(new Set(data.recipients.map((r) => r.user_id)))
  }

  const deselectAll = () => {
    setSelectedUsers(new Set())
  }

  const handleApprove = async () => {
    if (!data) return
    setBusy(true)
    setResultMsg(null)
    setError(null)
    try {
      const allUserIds = data.recipients.map((r) => r.user_id)
      const excluded = allUserIds.filter((uid) => !selectedUsers.has(uid))
      const res = await api.post(`/campaigns/${encodeURIComponent(campaignKey)}/action`, {
        excluded_user_ids: excluded,
        user_ids: Array.from(selectedUsers),
        note: note.trim() || 'One-click campaign remediation approved by analyst',
      })
      setResultMsg({
        type: 'success',
        text: `Campaign actions approved! Remediated ${res.data.users_remediated} user(s). 1 audit entry recorded per recipient.`,
      })
      await loadDetails()
      if (onSuccess) onSuccess()
    } catch (e) {
      setError(errText(e))
    } finally {
      setBusy(false)
    }
  }

  const handleUndo = async () => {
    if (!data) return
    setBusy(true)
    setResultMsg(null)
    setError(null)
    try {
      const res = await api.post(`/campaigns/${encodeURIComponent(campaignKey)}/undo`, {
        note: note.trim() || 'Analyst reversed reversible campaign actions',
      })
      setResultMsg({
        type: 'info',
        text: `Reversible campaign actions undone for ${res.data.users_undone} user(s). Mailbox purges remain irreversible. 1 audit entry recorded per recipient.`,
      })
      await loadDetails()
      if (onSuccess) onSuccess()
    } catch (e) {
      setError(errText(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-4xl flex-col rounded-2xl border border-ink-600 bg-ink-950 shadow-2xl">
        {/* Header */}
        <header className="flex items-center justify-between border-b border-ink-600/70 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-rose-500/20 text-rose-400">
              <Shield size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-white">Campaign Remediation</h2>
                {data && (
                  data.remediated ? (
                    <Chip tone="emerald">Remediated</Chip>
                  ) : (
                    <Chip tone="rose">Active Threat</Chip>
                  )
                )}
              </div>
              <p className="text-xs text-slate-400">One action for the whole campaign: block sender & links, purge messages, alert recipients.</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 transition hover:bg-ink-700 hover:text-white"
          >
            <X size={20} />
          </button>
        </header>

        {/* Content body */}
        <div className="flex-1 space-y-5 overflow-y-auto p-6">
          {loading && !data && <Spinner />}
          {error && <ErrorBox error={error} />}
          {resultMsg && (
            <div className={`flex items-center gap-2 rounded-lg p-3 text-sm ${
              resultMsg.type === 'success' ? 'border border-emerald-500/40 bg-emerald-500/10 text-emerald-300' : 'border border-sky-500/40 bg-sky-500/10 text-sky-300'
            }`}>
              <CheckCircle2 size={16} />
              <span>{resultMsg.text}</span>
            </div>
          )}

          {data && (
            <>
              {/* Campaign details */}
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-xl border border-ink-700 bg-ink-900/80 p-4">
                  <div className="text-xs font-semibold uppercase text-slate-400">Campaign Subject & Sender</div>
                  <div className="mt-1 font-medium text-white">{data.subject}</div>
                  <div className="mt-1 text-xs text-slate-400">
                    <span className="text-slate-300">{data.sender}</span> (domain: <span className="text-sky-300 font-mono">{data.sender_domain}</span>)
                  </div>
                </div>

                <div className="rounded-xl border border-ink-700 bg-ink-900/80 p-4">
                  <div className="text-xs font-semibold uppercase text-slate-400">Flagged URLs in Payload</div>
                  {data.links && data.links.length > 0 ? (
                    <ul className="mt-1 max-h-20 space-y-1 overflow-y-auto font-mono text-xs text-rose-300">
                      {data.links.map((link, idx) => (
                        <li key={idx} className="flex items-center gap-1.5 truncate">
                          <Link2 size={12} className="shrink-0 text-slate-400" />
                          <span className="truncate" title={link}>{link}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="mt-1 text-xs text-slate-500">No external hyperlinks flagged</div>
                  )}
                </div>
              </div>

              {/* Action bundle details */}
              <div className="rounded-xl border border-ink-700 bg-ink-900/50 p-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">Unified Campaign Action Bundle</span>
                  <span className="text-xs text-slate-500">Executes on all included recipients</span>
                </div>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  <div className="flex items-start gap-2 rounded-lg border border-ink-800 bg-ink-900 p-2.5">
                    <Shield size={16} className="mt-0.5 text-sky-400" />
                    <div>
                      <div className="text-xs font-medium text-slate-200">1. Block Sender & Domain</div>
                      <div className="text-[11px] text-slate-400">Block {data.sender_domain} in gateway (reversible)</div>
                    </div>
                  </div>
                  <div className="flex items-start gap-2 rounded-lg border border-ink-800 bg-ink-900 p-2.5">
                    <Link2 size={16} className="mt-0.5 text-amber-400" />
                    <div>
                      <div className="text-xs font-medium text-slate-200">2. Block All Links</div>
                      <div className="text-[11px] text-slate-400">Add {data.links?.length || 0} URLs to perimeter blocklist (reversible)</div>
                    </div>
                  </div>
                  <div className="flex items-start gap-2 rounded-lg border border-ink-800 bg-ink-900 p-2.5">
                    <Trash2 size={16} className="mt-0.5 text-rose-400" />
                    <div>
                      <div className="text-xs font-medium text-slate-200">3. Purge Message Everywhere</div>
                      <div className="text-[11px] text-slate-400">Remove phishing email from mailboxes (irreversible)</div>
                    </div>
                  </div>
                  <div className="flex items-start gap-2 rounded-lg border border-ink-800 bg-ink-900 p-2.5">
                    <Bell size={16} className="mt-0.5 text-emerald-400" />
                    <div>
                      <div className="text-xs font-medium text-slate-200">4. Alert Every Recipient</div>
                      <div className="text-[11px] text-slate-400">Notify user portal with security advice (reversible)</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Affected users checklist */}
              <div>
                <div className="flex flex-wrap items-center justify-between gap-2 pb-2">
                  <div className="flex items-center gap-2">
                    <Users size={16} className="text-sky-400" />
                    <span className="text-sm font-semibold text-white">
                      Affected Recipients ({selectedUsers.size} of {data.recipients.length} selected)
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    <button
                      type="button"
                      onClick={selectAll}
                      className="text-sky-400 hover:underline"
                    >
                      Select all
                    </button>
                    <span className="text-slate-600">·</span>
                    <button
                      type="button"
                      onClick={deselectAll}
                      className="text-slate-400 hover:underline"
                    >
                      Deselect all
                    </button>
                  </div>
                </div>

                <div className="max-h-60 overflow-y-auto rounded-xl border border-ink-700 bg-ink-900/70">
                  <table className="w-full text-left text-xs">
                    <thead className="sticky top-0 bg-ink-900 border-b border-ink-700 text-slate-400">
                      <tr>
                        <th className="p-2.5 pl-3 w-8">Include</th>
                        <th className="p-2.5">Recipient</th>
                        <th className="p-2.5">Department</th>
                        <th className="p-2.5">Case / Status</th>
                        <th className="p-2.5">Received</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-800">
                      {data.recipients.map((r) => {
                        const isChecked = selectedUsers.has(r.user_id)
                        return (
                          <tr
                            key={r.user_id}
                            className={`transition hover:bg-ink-800/60 ${!isChecked ? 'opacity-50 bg-ink-950/40' : ''}`}
                          >
                            <td className="p-2.5 pl-3">
                              <input
                                type="checkbox"
                                checked={isChecked}
                                onChange={() => toggleUser(r.user_id)}
                                className="h-4 w-4 rounded border-ink-600 bg-ink-800 text-sky-500 focus:ring-sky-500 focus:ring-offset-ink-950"
                              />
                            </td>
                            <td className="p-2.5 font-medium text-slate-200">
                              <div>{r.name}</div>
                              <div className="text-[11px] text-slate-400">{r.email || r.user_id}</div>
                            </td>
                            <td className="p-2.5 text-slate-400">{r.dept || '—'}</td>
                            <td className="p-2.5">
                              {r.case_id ? (
                                <div className="flex items-center gap-1.5">
                                  <Link
                                    to={`/investigate/${r.case_id}`}
                                    className="font-medium text-sky-400 hover:underline"
                                    onClick={onClose}
                                  >
                                    #{r.case_id}
                                  </Link>
                                  <Band band={r.band} score={r.score} />
                                </div>
                              ) : (
                                <span className="text-slate-500">Will auto-create case</span>
                              )}
                            </td>
                            <td className="p-2.5 text-slate-400">{when(r.received_at)}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
                <p className="mt-2 text-[11px] text-slate-500">
                  Unchecking a recipient removes them from this action bundle and leaves their mailbox untouched.
                </p>
              </div>

              {/* Justification Note */}
              <div>
                <label className="block text-xs font-semibold text-slate-300">
                  Analyst Justification / Audit Note (recorded in every recipient's audit trail)
                </label>
                <input
                  type="text"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="e.g. Campaign verified malicious by SOC analyst; approving whole-campus purge & blocks"
                  className="input mt-1.5"
                />
              </div>
            </>
          )}
        </div>

        {/* Footer controls */}
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-ink-600/70 bg-ink-900/60 px-6 py-4">
          <div className="text-xs text-slate-400">
            {data && (
              <span>
                {selectedUsers.size === 0
                  ? 'No users selected'
                  : `Approving will write 1 audit entry per user (${selectedUsers.size} total)`}
              </span>
            )}
          </div>

          <div className="flex items-center gap-3">
            {data && data.can_undo && (
              <button
                type="button"
                disabled={busy}
                onClick={handleUndo}
                className="btn btn-ghost text-amber-300 hover:text-amber-200"
              >
                <RotateCcw size={14} />
                Undo Reversible Actions
              </button>
            )}
            <button
              type="button"
              disabled={busy || selectedUsers.size === 0}
              onClick={handleApprove}
              className="btn btn-bad"
            >
              <Check size={14} />
              Approve Campaign Action ({selectedUsers.size} recipients)
            </button>
          </div>
        </footer>
      </div>
    </div>
  )
}
