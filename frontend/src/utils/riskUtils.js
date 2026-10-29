export const BANDS = {
  critical: {
    key: 'critical',
    label: 'Critical',
    scoreRange: [80, 100],
    cls: 'bg-rose-600/20 text-rose-300 border-rose-500/50',
    dot: '#f43f5e',
    textTone: 'text-rose-400',
    badgeTone: 'rose',
  },
  high: {
    key: 'high',
    label: 'High',
    scoreRange: [60, 79],
    cls: 'bg-orange-500/20 text-orange-300 border-orange-500/50',
    dot: '#f97316',
    textTone: 'text-orange-400',
    badgeTone: 'orange',
  },
  medium: {
    key: 'medium',
    label: 'Medium',
    scoreRange: [30, 59],
    cls: 'bg-amber-400/15 text-amber-300 border-amber-400/40',
    dot: '#fbbf24',
    textTone: 'text-amber-400',
    badgeTone: 'amber',
  },
  low: {
    key: 'low',
    label: 'Low',
    scoreRange: [0, 29],
    cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
    dot: '#34d399',
    textTone: 'text-emerald-400',
    badgeTone: 'emerald',
  },
}

export function getBandInfo(bandOrScore) {
  if (typeof bandOrScore === 'string') {
    const key = bandOrScore.toLowerCase()
    return BANDS[key] || BANDS.low
  }
  // Score-only callers get the fixed UI ranges; the case view shows the backend's own band separately.
  if (typeof bandOrScore === 'number') {
    if (bandOrScore >= 80) return BANDS.critical
    if (bandOrScore >= 60) return BANDS.high
    if (bandOrScore >= 30) return BANDS.medium
    return BANDS.low
  }
  return BANDS.low
}

export const STATUS_CONFIG = {
  open: { label: 'Open', tone: 'sky', bg: 'bg-sky-500/15 text-sky-300' },
  investigating: { label: 'Investigating', tone: 'violet', bg: 'bg-violet-500/15 text-violet-300' },
  resolved: { label: 'Resolved', tone: 'emerald', bg: 'bg-emerald-500/15 text-emerald-300' },
  auto_closed: { label: 'Auto Closed', tone: 'slate', bg: 'bg-ink-700 text-slate-300' },
  proposed: { label: 'Waiting', tone: 'amber', bg: 'bg-amber-500/15 text-amber-300' },
  approved: { label: 'Approved', tone: 'emerald', bg: 'bg-emerald-500/15 text-emerald-300' },
  rejected: { label: 'Rejected', tone: 'rose', bg: 'bg-rose-500/15 text-rose-300' },
  auto_done: { label: 'Ran automatically', tone: 'sky', bg: 'bg-sky-500/15 text-sky-300' },
}

export function getStatusInfo(status) {
  if (!status) return { label: 'Unknown', tone: 'slate', bg: 'bg-ink-700 text-slate-300' }
  const key = status.toLowerCase()
  return STATUS_CONFIG[key] || { label: status.replace('_', ' '), tone: 'slate', bg: 'bg-ink-700 text-slate-300' }
}
