import React from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Download, Mail, KeyRound, ShieldAlert } from 'lucide-react'
import api from '../api.js'
import { Band, Card, Chip, CodeChip, Empty, ErrorBox, Narrative, Spinner, useLoad, when } from '../ui.jsx'

export function CaseList({ base }) {
  const { data, loading } = useLoad(() => api.get('/cases', { params: { status: 'active', limit: 60 } }))
  const { id } = useParams()
  if (loading) return <Spinner />
  return (
    <div className="card max-h-[80vh] overflow-y-auto">
      <div className="border-b border-ink-600/60 px-4 py-2.5 text-sm font-semibold">Open cases ({data?.total})</div>
      <ul className="divide-y divide-ink-600/40">
        {data?.items.map((c) => (
          <li key={c.id}>
            <Link to={`/${base}/${c.id}`} className={`block px-4 py-2.5 hover:bg-ink-700/40 ${String(c.id) === id ? 'bg-ink-700/60' : ''}`}>
              <div className="flex items-center justify-between"><span className="truncate text-sm text-slate-200">{c.user.name}</span><Band band={c.band} score={c.score} /></div>
              <div className="mt-0.5 truncate text-xs text-slate-500">{c.headline}{c.campaign_size > 1 ? ` · campaign of ${c.campaign_size}` : ''}</div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function Investigation() {
  const { id } = useParams()
  const nav = useNavigate()
  const first = useLoad(() => (id ? Promise.resolve({ data: null }) : api.get('/cases', { params: { status: 'active', limit: 1 } })), [id])
  React.useEffect(() => { if (!id && first.data?.items?.[0]) nav(`/investigate/${first.data.items[0].id}`, { replace: true }) }, [id, first.data])
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-white">AI Threat Investigation</h1>
        <p className="text-sm text-slate-400">Every sentence points at an evidence line. Nothing is scored by the language model.</p>
      </div>
      <div className="grid gap-5 lg:grid-cols-4">
        <div className="lg:col-span-1"><CaseList base="investigate" /></div>
        <div className="space-y-5 lg:col-span-3">{id ? <CaseView id={id} /> : <Empty>Pick a case.</Empty>}</div>
      </div>
    </div>
  )
}

function CaseView({ id }) {
  const { data: d, error, loading } = useLoad(() => api.get(`/cases/${id}`), [id])
  const [dl, setDl] = React.useState(false)
  if (loading) return <Spinner />
  if (error) return <ErrorBox error={error} />
  const c = d.case
  const download = async () => {
    setDl(true)
    const r = await api.get(`/cases/${id}/report`, { responseType: 'blob' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(r.data); a.download = `traceguard-case-${id}.md`; a.click(); setDl(false)
  }
  const ex = d.extras || {}
  return (
    <>
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-xs text-slate-500">Incident #{c.id} · {d.user.email} · {d.user.dept}</div>
            <h2 className="text-lg font-semibold text-white">{d.narrative.headline}</h2>
            <div className="mt-1 text-sm text-slate-400">User: {d.user.name}</div>
          </div>
          <div className="flex items-center gap-2">
            <Band band={c.band} score={c.score} />
            <Link className="btn btn-primary" to={`/response/${c.id}`}><ShieldAlert size={15} /> Respond</Link>
            <button className="btn btn-ghost" onClick={download} disabled={dl}><Download size={15} /> Report</button>
          </div>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-4">
          <Score label="Email evidence" v={c.email_score} icon={Mail} />
          <Score label="Login evidence" v={c.login_score} icon={KeyRound} />
          <Score label="Correlation uplift" v={ex.uplift ? `+${ex.uplift}` : '0'} />
          <Score label="Case score" v={c.score} strong />
        </div>
        <p className="mt-3 rounded-lg bg-ink-900 px-3 py-2 font-mono text-xs text-slate-400">{d.formula}</p>
        {d.low_confidence_reason && <p className="mt-2 rounded-lg border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-sm text-amber-200">Low confidence: {d.low_confidence_reason}</p>}
      </Card>

      <Card title="AI-generated explanation" right={<Chip tone={d.narrative.source === 'llm' ? 'violet' : 'slate'}>{d.narrative.source === 'llm' ? 'language model, validated against evidence' : 'written from the evidence ledger'}</Chip>}>
        <Narrative text={d.narrative.summary} />
        {d.narrative.rejected_reason && <p className="mt-2 text-xs text-amber-300">{d.narrative.rejected_reason}</p>}
      </Card>

      <div className="grid gap-5 xl:grid-cols-2">
        <Card title="Evidence ledger (this is the score)">
          <table className="w-full">
            <tbody className="divide-y divide-ink-600/40">
              {d.ledger.map((e, i) => {
                const capped = (e.side === 'email' || e.side === 'login') && e.points !== e.raw_points
                return (
                  <tr key={i} className={e.points === 0 ? 'opacity-50' : ''}>
                    <td className="td w-8 align-top"><Chip tone={e.side === 'email' ? 'amber' : e.side === 'login' ? 'violet' : 'sky'}>{e.side === 'email' ? 'E' : e.side === 'login' ? 'L' : e.side === 'correlation' ? 'X' : '·'}</Chip></td>
                    <td className="td"><CodeChip code={e.code} /><div className="mt-0.5 text-slate-200">{e.label}</div><div className="text-xs text-slate-500">{e.detail}</div></td>
                    <td className="td w-24 text-right align-top font-mono text-slate-200">{e.points > 0 ? '+' : ''}{e.points}{capped && <div className="text-[10px] text-slate-500">cap hit, was {e.raw_points}</div>}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </Card>
        <div className="space-y-5">
          <Card title="Timeline">
            <ol className="relative ml-2 space-y-3 border-l border-ink-600 pl-4">
              {d.timeline.map((t, i) => (
                <li key={i}>
                  <span className={`absolute -left-[5px] h-2.5 w-2.5 rounded-full ${t.kind === 'email' ? 'bg-amber-400' : t.severity === 'high' ? 'bg-rose-400' : 'bg-slate-500'}`} />
                  <div className="text-xs text-slate-500">{when(t.ts)}</div>
                  <div className="text-sm text-slate-300">{t.text}</div>
                </li>
              ))}
            </ol>
          </Card>
          {d.not_evaluated.length > 0 && (
            <Card title="Not checked"><ul className="list-disc space-y-1 pl-5 text-sm text-amber-200">{d.not_evaluated.map((x, i) => <li key={i}>{x}</li>)}</ul></Card>
          )}
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <Card title="Email panel">
          {!d.email ? <Empty>No email evidence in this case.</Empty> : (
            <div className="space-y-2 text-sm">
              <div><span className="text-slate-500">From </span><span className="text-slate-200">{d.email.sender}</span></div>
              <div><span className="text-slate-500">Subject </span><span className="text-slate-200">{d.email.subject}</span></div>
              {d.email.reply_to && <div><span className="text-slate-500">Reply-To </span><span className="text-slate-200">{d.email.reply_to}</span></div>}
              <div className="flex gap-1">{Object.entries(d.email.auth || {}).filter(([k]) => ['spf', 'dkim', 'dmarc'].includes(k)).map(([k, v]) => <Chip key={k} tone={v === 'pass' ? 'emerald' : 'rose'}>{k.toUpperCase()} {v}</Chip>)}</div>
              {d.email.hidden_text_found && <div className="text-xs text-rose-300">Hidden text addressed to an AI reviewer was found and removed.</div>}
              <div className="rounded-lg bg-ink-900 p-2 text-xs text-slate-400">{d.email.preview}</div>
              <div className="text-xs text-slate-500">Links</div>
              <ul className="space-y-1 text-xs">{(ex.flagged_links || []).map((l, i) => <li key={i} className="break-all text-rose-300">{l.href}<div className="text-slate-500">{l.reason}</div></li>)}</ul>
              {d.text_terms.length > 0 && <div className="flex flex-wrap gap-1">{d.text_terms.map((t) => <Chip key={t.term} tone="amber">{t.term}</Chip>)}</div>}
            </div>
          )}
        </Card>
        <Card title="Login panel (against the user's usual pattern)">
          {ex.baseline && (
            <div className="mb-3 flex flex-wrap gap-1 text-xs">
              <span className="text-slate-500">Usual:</span>
              {ex.baseline.countries?.map((x) => <Chip key={x} tone="sky">{x}</Chip>)}
              {ex.baseline.devices?.map((x) => <Chip key={x} tone="violet">{x}</Chip>)}
              <Chip>{ex.baseline.n_success} past logins</Chip>
            </div>
          )}
          <table className="w-full">
            <tbody className="divide-y divide-ink-600/40">
              {d.recent_logins.map((r, i) => (
                <tr key={i} className={r.flagged ? 'bg-rose-500/5' : ''}>
                  <td className="td text-xs text-slate-500">{when(r.ts)}</td>
                  <td className="td text-xs text-slate-300">{[r.city, r.country].filter(Boolean).join(', ') || 'Unknown'}<div className="text-slate-500">{r.device}</div></td>
                  <td className="td text-xs">{r.success ? <Chip tone="emerald">ok</Chip> : <Chip tone="rose">failed</Chip>}</td>
                  <td className="td text-right"><Band band={r.risk >= 60 ? 'high' : r.risk >= 30 ? 'medium' : 'low'} score={r.risk} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </>
  )
}

const Score = ({ label, v, icon: Icon, strong }) => (
  <div className={`rounded-lg border p-3 ${strong ? 'border-sky-500/50 bg-sky-500/10' : 'border-ink-600/60 bg-ink-900'}`}>
    <div className="flex items-center gap-1 text-xs text-slate-400">{Icon && <Icon size={12} />}{label}</div>
    <div className="text-2xl font-semibold text-white">{v}</div>
  </div>
)
