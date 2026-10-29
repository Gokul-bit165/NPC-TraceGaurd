import React from 'react'

export const CODE_SIDE = {
  email: { label: 'E', tone: 'bg-amber-400/20 text-amber-300 border-amber-400/30' },
  login: { label: 'L', tone: 'bg-violet-400/20 text-violet-300 border-violet-400/30' },
  correlation: { label: 'X', tone: 'bg-sky-400/20 text-sky-300 border-sky-400/30' },
  cap: { label: '—', tone: 'bg-ink-700 text-slate-400 border-ink-600' },
}

export default function EvidencePanel({
  ledger = [],
  highlightedCode = null,
  onCodeClick,
  className = '',
}) {
  return (
    <div className={`card overflow-hidden ${className}`}>
      <header className="border-b border-ink-600/60 px-4 py-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-200">
          Evidence Ledger <span className="text-xs text-slate-500 font-normal">(Determines Incident Score)</span>
        </h3>
        <span className="text-xs text-slate-400">
          {ledger.length} {ledger.length === 1 ? 'signal' : 'signals'}
        </span>
      </header>

      <div className="overflow-x-auto">
        <table className="w-full">
          <tbody className="divide-y divide-ink-600/40">
            {ledger.length === 0 ? (
              <tr>
                <td className="td text-slate-500 text-center py-6">
                  No evidence signals recorded.
                </td>
              </tr>
            ) : (
              ledger.map((item, idx) => {
                const sideInfo = CODE_SIDE[item.side] || CODE_SIDE.cap
                const isHighlighted = highlightedCode && (item.code === highlightedCode || highlightedCode.includes(item.code))
                const isCapped = item.points !== item.raw_points && item.raw_points !== undefined

                return (
                  <tr
                    key={item.code || idx}
                    id={`evidence-${item.code}`}
                    onClick={() => onCodeClick && onCodeClick(item.code)}
                    className={`transition-all duration-300 ${
                      item.points === 0 ? 'opacity-60' : ''
                    } ${
                      isHighlighted
                        ? 'bg-sky-950/70 border-l-4 border-l-sky-400 ring-1 ring-sky-500/50'
                        : 'hover:bg-ink-700/30'
                    }`}
                  >
                    <td className="td w-10 align-top">
                      <span className={`inline-flex h-6 w-6 items-center justify-center rounded-md border text-xs font-mono font-bold ${sideInfo.tone}`}>
                        {sideInfo.label}
                      </span>
                    </td>
                    <td className="td">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="rounded bg-ink-900 border border-ink-600 px-1.5 py-0.5 font-mono text-[10px] text-sky-300">
                          {item.code}
                        </span>
                        {item.group && (
                          <span className="text-[10px] text-slate-500 uppercase">
                            [{item.group}]
                          </span>
                        )}
                      </div>
                      <div className="mt-1 text-sm font-medium text-slate-200">
                        {item.label}
                      </div>
                      {item.detail && (
                        <div className="text-xs text-slate-400 mt-0.5 leading-relaxed">
                          {item.detail}
                        </div>
                      )}
                    </td>
                    <td className="td w-28 text-right align-top font-mono text-sm">
                      <span
                        className={
                          item.points > 0
                            ? 'text-amber-400 font-semibold'
                            : item.points < 0
                            ? 'text-slate-400'
                            : 'text-slate-600'
                        }
                      >
                        {item.points > 0 ? `+${item.points}` : item.points}
                      </span>
                      {isCapped && (
                        <div className="text-[10px] text-slate-500 mt-0.5">
                          cap hit, was {item.raw_points}
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
