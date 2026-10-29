import React from 'react'
import { ShieldCheck } from 'lucide-react'
import api from '../api.js'
import { Card, Chip, Empty, ErrorBox, Spinner, useLoad, when } from '../ui.jsx'

export default function MyAlerts() {
  const { data, error, loading, reload } = useLoad(() => api.get('/me/alerts'))
  const ack = async (id, answer) => { await api.post(`/me/alerts/${id}/ack`, { answer }); reload() }
  if (loading) return <Spinner />
  if (error) return <ErrorBox error={error} />
  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-white"><ShieldCheck className="text-sky-400" /> My security alerts</h1>
        <p className="text-sm text-slate-400">Hi {data.user.name}. These are messages from campus IT about activity on your account.</p>
      </div>
      {data.items.length === 0 ? <Card><Empty>Nothing to review. Your account looks normal.</Empty></Card> : data.items.map((n) => (
        <Card key={n.id} title={n.title} right={<span className="text-xs text-slate-500">{when(n.ts)}</span>}>
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-slate-300">{n.body}</pre>
          {n.acknowledged ? <div className="mt-3"><Chip tone={n.acknowledged === 'it_was_me' ? 'emerald' : 'rose'}>You answered: {n.acknowledged === 'it_was_me' ? 'it was me' : 'it was not me'}</Chip></div> : (
            <div className="mt-4 flex gap-2">
              <button className="btn btn-ok" onClick={() => ack(n.id, 'it_was_me')}>Yes, it was me</button>
              <button className="btn btn-bad" onClick={() => ack(n.id, 'not_me')}>No, it was not me</button>
            </div>
          )}
        </Card>
      ))}
    </div>
  )
}
