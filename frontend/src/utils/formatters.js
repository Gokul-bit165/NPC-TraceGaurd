export function formatDate(iso, opts = {}) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    return d.toLocaleString([], {
      month: opts.month || 'short',
      day: opts.day || 'numeric',
      hour: opts.hour || '2-digit',
      minute: opts.minute || '2-digit',
      year: opts.year,
      ...opts,
    })
  } catch {
    return iso
  }
}

export function formatTimeAgo(iso) {
  if (!iso) return ''
  try {
    const diff = (Date.now() - new Date(iso).getTime()) / 1000
    if (diff < 60) return 'just now'
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    return `${Math.floor(diff / 86400)}d ago`
  } catch {
    return ''
  }
}

export function formatPct(val, decimals = 1) {
  if (val === null || val === undefined || isNaN(val)) return 'n/a'
  return `${(Number(val) * 100).toFixed(decimals)}%`
}

export function formatNumber(val) {
  if (val === null || val === undefined) return '0'
  return Number(val).toLocaleString()
}

export function formatLocation(row) {
  if (!row) return 'Unknown'
  const parts = [row.city, row.country].filter(Boolean)
  return parts.length > 0 ? parts.join(', ') : 'Unknown'
}

export function truncate(str, len = 120) {
  if (!str) return ''
  return str.length > len ? str.slice(0, len) + '…' : str
}
