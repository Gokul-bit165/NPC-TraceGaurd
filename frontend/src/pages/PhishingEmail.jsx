import React from 'react'
import { AlertTriangle, Upload } from 'lucide-react'
import api, { errText } from '../api.js'
import { Band, Card, Chip, CodeChip, ErrorBox, Narrative } from '../ui.jsx'

const SAMPLE = {
  sender: 'helpdesk@kestrel-support.com', subject: 'Urgent: Campus account verification',
  body: 'Your Kestrel mailbox will be deactivated within 24 hours. Verify your account now and confirm your password at http://kestrel-edu-login.top/verify',
}

export default function PhishingEmail() {
  const [f, setF] = React.useState({ sender: '', subject: '', body: '', urls: '', reply_to: '', recipient: '' })
  const [file, setFile] = React.useState(null)
  const [res, setRes] = React.useState(null)
  const [err, setErr] = React.useState('')
  const [busy, setBusy] = React.useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const run = async (save) => {
    setBusy(true); setErr('')
    try {
      const fd = new FormData()
      if (file) fd.append('file', file)
      Object.entries(f).forEach(([k, v]) => fd.append(k, v))
      fd.append('save', save ? 'true' : 'false')
      setRes((await api.post('/emails/analyze', fd)).data)
    } catch (e) { setErr(errText(e)); setRes(null) } finally { setBusy(false) }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-white">Phishing Email Investigation</h1>
        <p className="text-sm text-slate-400">Upload an .eml file for the full check, or type the details. Typed fields cannot be checked for SPF, DKIM or DMARC, and the result says so.</p>
      </div>
      <div className="grid gap-5 lg:grid-cols-5">
        <Card title="Email to analyze" className="lg:col-span-2">
          <div className="space-y-3">
            <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-dashed border-ink-600 p-3 text-sm text-slate-400 hover:bg-ink-700/40">
              <Upload size={16} /> {file ? file.name : 'Upload .eml file'}
              <input type="file" accept=".eml,message/rfc822" className="hidden" onChange={(e) => setFile(e.target.files[0] || null)} />
            </label>
            <div className="text-center text-xs text-slate-500">or enter details</div>
            <input className="input" placeholder="Sender email address" value={f.sender} onChange={set('sender')} />
            <input className="input" placeholder="Reply-To (optional)" value={f.reply_to} onChange={set('reply_to')} />
            <input className="input" placeholder="Subject" value={f.subject} onChange={set('subject')} />
            <textarea className="input h-28" placeholder="Message body" value={f.body} onChange={set('body')} />
            <textarea className="input h-16" placeholder="Extra URLs, one per line (links in the body are extracted automatically)" value={f.urls} onChange={set('urls')} />
            <input className="input" placeholder="Recipient (name, email or user id) to open a case" value={f.recipient} onChange={set('recipient')} />
            <div className="flex flex-wrap gap-2">
              <button className="btn btn-primary" disabled={busy} onClick={() => run(false)}>{busy ? 'Analyzing…' : 'Analyze'}</button>
              <button className="btn btn-ghost" disabled={busy || !f.recipient} onClick={() => run(true)}>Analyze and open case</button>
              <button className="btn btn-ghost" onClick={() => { setF({ ...f, ...SAMPLE }); setFile(null) }}>Fill sample</button>
            </div>
            <ErrorBox error={err} />
          </div>
        </Card>

        <div className="space-y-5 lg:col-span-3">
          {!res ? <Card><p className="py-10 text-center text-sm text-slate-500">Results appear here.</p></Card> : (
            <>
              <Card title="Email investigation" right={<Band band={res.band} score={res.score} />}>
                <div className="grid grid-cols-3 gap-3 text-sm">
                  <div><div className="text-xs text-slate-500">Subject</div><div className="text-slate-200">{res.email.subject || '(none)'}</div></div>
                  <div><div className="text-xs text-slate-500">From</div><div className="break-all text-slate-200">{res.email.sender || '(none)'}</div></div>
                  <div><div className="text-xs text-slate-500">Phishing probability (text model)</div><div className="text-2xl font-semibold text-white">{res.probability !== null ? `${Math.round(res.probability * 100)}%` : 'n/a'}</div></div>
                </div>
                {res.saved_case_id && <div className="mt-3 text-sm text-emerald-300">Case #{res.saved_case_id} opened or updated for the recipient.</div>}
                {res.email.hidden_text_found && <div className="mt-3 flex items-center gap-2 rounded-lg border border-rose-500/40 bg-rose-500/10 p-2 text-sm text-rose-300"><AlertTriangle size={16} /> Hidden text found. It was removed before analysis.</div>}
              </Card>
              <Card title="AI investigation" right={<Chip tone={res.narrative.source === 'llm' ? 'violet' : 'slate'}>{res.narrative.source === 'llm' ? 'language model, validated' : 'template from evidence'}</Chip>}>
                <p className="mb-1 text-sm font-semibold text-white">{res.narrative.headline}</p>
                <Narrative text={res.narrative.summary} />
                {res.narrative.rejected_reason && <p className="mt-2 text-xs text-amber-300">{res.narrative.rejected_reason}</p>}
              </Card>
              <Card title="Detected evidence">
                <table className="w-full">
                  <tbody className="divide-y divide-ink-600/40">
                    {res.ledger.length === 0 && <tr><td className="td text-slate-500">Nothing suspicious was found.</td></tr>}
                    {res.ledger.map((e) => (
                      <tr key={e.code}>
                        <td className="td w-44"><CodeChip code={e.code} /></td>
                        <td className="td"><div className="text-slate-200">{e.label}</div><div className="text-xs text-slate-500">{e.detail}</div></td>
                        <td className={`td w-20 text-right font-mono ${e.points < 0 ? 'text-slate-500' : e.points === 0 ? 'text-slate-600' : 'text-amber-300'}`}>{e.points > 0 ? '+' : ''}{e.points}{e.points !== e.raw_points && e.raw_points ? <span className="block text-[10px] text-slate-500">capped from {e.raw_points}</span> : null}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
              <div className="grid gap-5 md:grid-cols-2">
                <Card title="Links found">
                  {res.email.links.length === 0 ? <p className="text-sm text-slate-500">No links.</p> : (
                    <ul className="space-y-2 text-sm">
                      {res.email.links.map((l, i) => {
                        const bad = res.flagged_links.find((x) => x.href === l.href)
                        return <li key={i} className="break-all"><span className={bad ? 'text-rose-300' : 'text-slate-300'}>{l.href}</span>{l.text && <div className="text-xs text-slate-500">shown as: {l.text}</div>}{bad && <div className="text-xs text-rose-400">{bad.reason}</div>}</li>
                      })}
                    </ul>
                  )}
                </Card>
                <Card title="Sender checks">
                  {Object.keys(res.auth).length ? <div className="flex gap-2">{Object.entries(res.auth).map(([k, v]) => <Chip key={k} tone={v === 'pass' ? 'emerald' : 'rose'}>{k.toUpperCase()} {v}</Chip>)}</div> : null}
                  {res.not_evaluated.map((x, i) => <p key={i} className="mt-2 text-xs text-amber-300">{x}</p>)}
                  {res.terms.length > 0 && <div className="mt-3"><div className="mb-1 text-xs text-slate-500">Words that pushed the text score up</div><div className="flex flex-wrap gap-1">{res.terms.map((t) => <Chip key={t.term} tone="amber">{t.term}</Chip>)}</div></div>}
                </Card>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
