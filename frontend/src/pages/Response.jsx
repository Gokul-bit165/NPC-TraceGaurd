import React, { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  AlertCircle,
  AlertTriangle,
  Check,
  CheckCheck,
  CheckCircle2,
  Clock,
  History,
  Lock,
  MessageSquare,
  RotateCcw,
  Shield,
  ShieldAlert,
  ShieldCheck,
  ThumbsDown,
  ThumbsUp,
  User,
  X,
} from 'lucide-react'
import api, { errText, getRole } from '../api.js'
import {
  Band,
  Card,
  Chip,
  ConfirmDialog,
  Empty,
  ErrorBox,
  NotificationToast,
  PageHeader,
  RiskBadge,
  Spinner,
  StatusBadge,
  when,
} from '../ui.jsx'
import { CaseList } from './Investigation.jsx'
import { useApi } from '../hooks/useApi.js'

const ACTION_STATUS = {
  proposed: { label: 'Waiting Approval', tone: 'amber', icon: Clock },
  approved: { label: 'Approved', tone: 'emerald', icon: CheckCircle2 },
  rejected: { label: 'Rejected', tone: 'rose', icon: X },
  auto_done: { label: 'Ran Automatically', tone: 'sky', icon: Check },
}

export default function Response() {
  const { id } = useParams()

  return (
    <div className="space-y-6">
      <PageHeader
        title="Incident Response Management"
        description="Review, approve, and execute containment procedures in strict dependency order. Reversible steps can run safely; irreversible changes require explicit analyst sign-off."
      />

      <div className="grid gap-6 lg:grid-cols-4">
        <div className="lg:col-span-1">
          <CaseList base="response" />
        </div>
        <div className="space-y-6 lg:col-span-3">
          {id ? (
            <ResponseWorkflow id={id} />
          ) : (
            <Card>
              <div className="py-20 text-center text-slate-500 space-y-2">
                <ShieldAlert className="mx-auto text-slate-600" size={36} />
                <h4 className="text-sm font-semibold text-slate-300">
                  Select an Incident to Manage Response
                </h4>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Pick a case from the active queue on the left to inspect recommended actions, enforce sign-out dependencies, and log audit decisions.
                </p>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}

function ResponseWorkflow({ id }) {
  const { data: d, error, loading, reload } = useApi(() => api.get(`/cases/${id}`), [id])

  const [busy, setBusy] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [toastMessage, setToastMessage] = useState(null)

  // Dialog state for approvals and rejections
  const [confirmDialog, setConfirmDialog] = useState({
    isOpen: false,
    title: '',
    message: '',
    consequences: '',
    confirmTone: 'primary',
    confirmLabel: 'Confirm',
    requireNote: false,
    onConfirm: null,
  })

  if (loading && !d) return <Spinner message="Loading response actions & workflow…" />
  if (error && !d) return <ErrorBox error={error} onRetry={reload} />
  if (!d) return null

  const c = d.case
  const actions = d.actions || []
  const audit = d.audit || []

  // Map actions by code for dependency checking
  const actionByCode = Object.fromEntries(actions.map((a) => [a.code, a]))

  const executeActionDecision = async (actionId, decision, note = '') => {
    setBusy(true)
    setErrorMessage('')
    try {
      await api.post(`/cases/${id}/actions/${actionId}`, { decision, note })
      setToastMessage(`Action ${decision === 'approve' ? 'approved' : 'rejected'} successfully`)
      await reload()
    } catch (e) {
      setErrorMessage(errText(e))
    } finally {
      setBusy(false)
    }
  }

  const handleApprove = (action) => {
    // If action is NOT reversible, require explicit confirmation dialog explaining consequences
    if (!action.reversible) {
      setConfirmDialog({
        isOpen: true,
        title: `Approve Irreversible Action: ${action.label}`,
        message: `You are about to approve "${action.label}". This action cannot be automatically rolled back once executed.`,
        consequences: `Action code: ${action.code}. Connector: ${action.connector}. Detail: ${action.detail}. Ensure that you have verified the user's identity and that the incident warrants this remediation.`,
        confirmTone: 'danger',
        confirmLabel: 'Approve Irreversible Action',
        requireNote: false,
        onConfirm: () => {
          setConfirmDialog((prev) => ({ ...prev, isOpen: false }))
          executeActionDecision(action.id, 'approve', '')
        },
      })
      return
    }

    // Normal reversible action
    executeActionDecision(action.id, 'approve', '')
  }

  const handleReject = (action) => {
    // Rejections require a meaningful explanation note
    setConfirmDialog({
      isOpen: true,
      title: `Reject Response Action: ${action.label}`,
      message: `Please specify the security rationale for rejecting "${action.label}". This note will be recorded permanently in the incident audit trail.`,
      consequences: `The action status will change to Rejected. Automated execution will be aborted.`,
      confirmTone: 'danger',
      confirmLabel: 'Reject Action',
      requireNote: true,
      notePlaceholder: 'e.g. User confirmed travel verbally / False alarm / Legitimate campus broadcast',
      onConfirm: (note) => {
        setConfirmDialog((prev) => ({ ...prev, isOpen: false }))
        executeActionDecision(action.id, 'reject', note)
      },
    })
  }

  // Approve All Safe Steps:
  // Approves only proposed actions that are reversible, not account locks/password resets,
  // and whose dependencies are already approved or auto_done.
  const handleApproveAllSafeSteps = () => {
    const safeActions = actions.filter((a) => {
      if (a.status !== 'proposed') return false
      if (!a.reversible) return false
      if (a.code === 'idp.reset_password' || a.code === 'idp.lock_account') return false

      if (a.depends_on) {
        const dep = actionByCode[a.depends_on]
        if (!dep || !['approved', 'auto_done'].includes(dep.status)) return false
      }
      return true
    })

    if (safeActions.length === 0) {
      alert('There are no eligible safe steps waiting for approval.')
      return
    }

    setConfirmDialog({
      isOpen: true,
      title: 'Approve All Safe Steps',
      message: `This will approve ${safeActions.length} eligible reversible actions (${safeActions.map((a) => a.label).join(', ')}).`,
      consequences:
        'Irreversible actions (like password reset or mailbox purge) and locked dependencies will NOT be touched and still require individual approval.',
      confirmTone: 'ok',
      confirmLabel: `Approve ${safeActions.length} Safe Actions`,
      requireNote: false,
      onConfirm: async () => {
        setConfirmDialog((prev) => ({ ...prev, isOpen: false }))
        setBusy(true)
        setErrorMessage('')
        try {
          for (const sa of safeActions) {
            await api.post(`/cases/${id}/actions/${sa.id}`, { decision: 'approve', note: 'Batch safe steps approval' })
          }
          setToastMessage(`Approved ${safeActions.length} safe steps`)
          await reload()
        } catch (e) {
          setErrorMessage(errText(e))
        } finally {
          setBusy(false)
        }
      },
    })
  }

  const handleUpdateStatus = async (status) => {
    setBusy(true)
    setErrorMessage('')
    try {
      await api.post(`/cases/${id}/status`, { status })
      setToastMessage(`Incident status set to ${status.replace('_', ' ')}`)
      await reload()
    } catch (e) {
      setErrorMessage(errText(e))
    } finally {
      setBusy(false)
    }
  }

  const handleUpdateVerdict = async (verdict) => {
    setBusy(true)
    setErrorMessage('')
    try {
      await api.post(`/cases/${id}/verdict`, { verdict })
      setToastMessage(`Recorded verdict: ${verdict === 'true_positive' ? 'Real threat' : 'False alarm'}`)
      await reload()
    } catch (e) {
      setErrorMessage(errText(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      {/* Toast Notification */}
      <NotificationToast
        show={!!toastMessage}
        message={toastMessage}
        type="success"
        onClose={() => setToastMessage(null)}
      />

      {/* Confirmation & Rejection Dialog */}
      <ConfirmDialog
        isOpen={confirmDialog.isOpen}
        title={confirmDialog.title}
        message={confirmDialog.message}
        consequences={confirmDialog.consequences}
        confirmTone={confirmDialog.confirmTone}
        confirmLabel={confirmDialog.confirmLabel}
        requireNote={confirmDialog.requireNote}
        notePlaceholder={confirmDialog.notePlaceholder}
        onConfirm={confirmDialog.onConfirm}
        onCancel={() => setConfirmDialog((prev) => ({ ...prev, isOpen: false }))}
      />

      {/* Case Overview Banner */}
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
              <span>Incident #{c.id}</span>
              <span>·</span>
              <span>{d.user.name} ({d.user.email})</span>
            </div>
            <h2 className="mt-1 text-lg font-bold text-slate-100">
              {d.user.name}: {d.narrative.headline || c.headline}
            </h2>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              <StatusBadge status={c.status} />
              {c.assignee && (
                <span className="rounded bg-ink-700 border border-ink-600 px-2 py-0.5 text-slate-300">
                  Assigned to: {c.assignee}
                </span>
              )}
              {c.campaign_size > 1 && (
                <span className="rounded border border-rose-500/40 bg-rose-500/15 px-2 py-0.5 font-medium text-rose-300">
                  Same campaign reached {c.campaign_size} recipients
                </span>
              )}
              {c.verdict && (
                <Chip tone={c.verdict === 'true_positive' ? 'rose' : 'emerald'}>
                  Verdict: {c.verdict === 'true_positive' ? 'Confirmed Threat' : 'False Positive'}
                </Chip>
              )}
            </div>
          </div>

          <div className="flex items-center gap-3">
            <RiskBadge band={c.band} score={c.score} size="md" />
            <Link
              to={`/investigate/${c.id}`}
              className="btn btn-ghost text-xs"
            >
              See Evidence Ledger
            </Link>
          </div>
        </div>
      </Card>

      <ErrorBox error={errorMessage} />

      {/* Ordered Recommended Actions */}
      <Card
        title={
          <div className="flex items-center gap-2">
            <span>Ordered Response Actions</span>
            <span className="text-xs text-slate-400 font-normal">
              (Enforced Dependency Order)
            </span>
          </div>
        }
        right={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleApproveAllSafeSteps}
              disabled={busy}
              className="btn btn-ok text-xs"
              title="Batch-approve eligible safe reversible containment steps"
            >
              <CheckCheck size={14} />
              <span>Approve All Safe Steps</span>
            </button>
            <span className="text-[11px] text-slate-500 hidden sm:inline">
              Decisions signed as: <b className="text-slate-300">{getRole()}</b>
            </span>
          </div>
        }
      >
        <ol className="space-y-3">
          {actions.map((action) => {
            const statusConfig = ACTION_STATUS[action.status] || ACTION_STATUS.proposed
            const StatusIcon = statusConfig.icon
            const depAction = action.depends_on ? actionByCode[action.depends_on] : null

            // Strict dependency check: if action has a dependency that is not approved or auto_done, it is locked!
            const isDependencyUnsatisfied =
              depAction && !['approved', 'auto_done'].includes(depAction.status)
            const isBlocked = action.status === 'proposed' && isDependencyUnsatisfied

            return (
              <li
                key={action.id}
                className={`rounded-xl border p-4 transition-colors ${
                  action.status === 'approved'
                    ? 'border-emerald-500/30 bg-emerald-950/10'
                    : action.status === 'rejected'
                    ? 'border-rose-500/30 bg-rose-950/10 opacity-75'
                    : isBlocked
                    ? 'border-amber-500/30 bg-ink-900/80'
                    : 'border-ink-600/70 bg-ink-900'
                }`}
              >
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="flex min-w-0 items-start gap-3.5">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink-700 border border-ink-600 text-xs font-bold text-slate-200">
                      {action.order}
                    </span>

                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-bold text-slate-100">
                          {action.label}
                        </span>
                        <Chip tone={statusConfig.tone}>
                          <StatusIcon size={12} className="inline mr-1" />
                          {statusConfig.label}
                        </Chip>
                        <Chip tone={action.reversible ? 'slate' : 'rose'}>
                          {action.reversible ? 'Reversible' : 'Irreversible'}
                        </Chip>
                        <span className="rounded bg-ink-800 border border-ink-600 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
                          {action.connector}
                        </span>
                      </div>

                      <p className="text-xs text-slate-300 leading-relaxed max-w-2xl">
                        {action.detail}
                      </p>

                      {/* Locked Dependency Warning */}
                      {isBlocked && (
                        <div className="mt-1 flex items-center gap-1.5 text-xs font-semibold text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-md p-1.5">
                          <Lock size={13} className="shrink-0" />
                          <span>
                            Locked because the required sign-out action (
                            <span className="underline">{depAction?.label}</span>) has not been approved.
                          </span>
                        </div>
                      )}

                      {/* Decision Sign-off Info */}
                      {action.decided_by && (
                        <div className="text-[11px] text-slate-400 pt-1 font-mono">
                          Decided by: <b className="text-slate-300">{action.decided_by}</b> · {when(action.decided_at)}
                          {action.note && (
                            <div className="italic text-slate-300 font-sans mt-0.5">
                              "{action.note}"
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Action Decision Buttons */}
                  {action.status === 'proposed' && (
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        type="button"
                        className="btn btn-ok text-xs"
                        disabled={busy || isBlocked}
                        onClick={() => handleApprove(action)}
                        title={isBlocked ? 'Resolve preceding dependency before approval' : ''}
                      >
                        <Check size={14} />
                        <span>Approve</span>
                      </button>
                      <button
                        type="button"
                        className="btn btn-bad text-xs"
                        disabled={busy}
                        onClick={() => handleReject(action)}
                      >
                        <X size={14} />
                        <span>Reject</span>
                      </button>
                    </div>
                  )}
                </div>
              </li>
            )
          })}
        </ol>
      </Card>

      {/* Workflow Controls & User Alert Preview */}
      <div className="grid gap-6 xl:grid-cols-2">
        {/* Status Lifecycle & Feedback */}
        <Card title="Case Lifecycle & Threat Feedback">
          <div className="space-y-4">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                Workflow Status
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className={`btn text-xs ${c.status === 'investigating' ? 'btn-primary' : 'btn-ghost'}`}
                  disabled={busy}
                  onClick={() => handleUpdateStatus('investigating')}
                >
                  Mark Investigating
                </button>
                <button
                  type="button"
                  className={`btn text-xs ${c.status === 'resolved' ? 'btn-ok' : 'btn-ghost'}`}
                  disabled={busy}
                  onClick={() => handleUpdateStatus('resolved')}
                >
                  Mark Resolved
                </button>
                <button
                  type="button"
                  className="btn btn-ghost text-xs"
                  disabled={busy}
                  onClick={() => handleUpdateStatus('open')}
                >
                  <RotateCcw size={13} />
                  <span>Reopen Case</span>
                </button>
              </div>
            </div>

            <div className="border-t border-ink-600/40 pt-3 space-y-2">
              <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Analyst Quality Feedback
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Was this a true threat or a false alarm? Your classification updates the algorithm tuning reports and signal precision metrics.
              </p>
              <div className="flex flex-wrap gap-2 pt-1">
                <button
                  type="button"
                  className={`btn text-xs ${c.verdict === 'true_positive' ? 'btn-bad ring-2 ring-rose-400' : 'btn-bad'}`}
                  disabled={busy}
                  onClick={() => handleUpdateVerdict('true_positive')}
                >
                  <ThumbsDown size={14} />
                  <span>Real Threat</span>
                </button>
                <button
                  type="button"
                  className={`btn text-xs ${c.verdict === 'false_positive' ? 'btn-ok ring-2 ring-emerald-400' : 'btn-ok'}`}
                  disabled={busy}
                  onClick={() => handleUpdateVerdict('false_positive')}
                >
                  <ThumbsUp size={14} />
                  <span>False Alarm</span>
                </button>
              </div>
            </div>
          </div>
        </Card>

        {/* Drafted User Notification Alert */}
        <Card title="Drafted User Notification Alert">
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span className="flex items-center gap-1.5">
                <MessageSquare size={14} className="text-sky-400" />
                <span>Generated from Incident Evidence</span>
              </span>
              <span className="text-[11px] text-slate-500">Sent to student view</span>
            </div>
            <pre className="whitespace-pre-wrap font-sans text-xs leading-relaxed text-slate-300 rounded-lg border border-ink-600/60 bg-ink-900 p-3.5 select-text">
              {d.user_alert || 'No drafted notification generated.'}
            </pre>
          </div>
        </Card>
      </div>

      {/* Incident Audit Trail Table */}
      <Card
        title="Incident Audit Trail"
        right={<span className="text-xs text-slate-400">{audit.length} events logged</span>}
      >
        {audit.length === 0 ? (
          <Empty>No audit log records for this incident.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-ink-600/60 bg-ink-900/50">
                <tr>
                  <th className="th w-40">Timestamp (UTC)</th>
                  <th className="th w-48">Actor & Role</th>
                  <th className="th w-40">Event</th>
                  <th className="th">Details & Notes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-600/40">
                {audit.map((a, idx) => (
                  <tr key={idx} className="hover:bg-ink-700/30">
                    <td className="td font-mono text-slate-400">
                      {when(a.ts)}
                    </td>
                    <td className="td">
                      <div className="font-semibold text-slate-200">{a.actor}</div>
                      <div className="text-[10px] text-slate-500 font-mono capitalize">
                        {a.role}
                      </div>
                    </td>
                    <td className="td">
                      <span className="rounded bg-ink-700/80 px-2 py-0.5 text-[11px] font-medium text-slate-300 capitalize">
                        {a.event.replaceAll('_', ' ')}
                      </span>
                    </td>
                    <td className="td text-slate-400 font-mono text-[11px] break-all">
                      {typeof a.detail === 'object' ? JSON.stringify(a.detail) : a.detail}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  )
}
