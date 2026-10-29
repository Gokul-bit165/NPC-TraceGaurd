import React from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

// Without a boundary, one render exception unmounts the whole tree and leaves a blank page.
// This keeps the shell (sidebar, header) alive and shows what went wrong. `resetKey` clears it on navigation.
export default class ErrorBoundary extends React.Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('TraceGuard render error:', error, info?.componentStack)
  }

  componentDidUpdate(prev) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null })
    }
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="card mx-auto mt-6 max-w-xl p-6 text-center animate-fade-in" role="alert">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-rose-500/10 text-rose-400">
          <AlertTriangle size={24} />
        </div>
        <h2 className="text-base font-semibold text-slate-100">This page failed to render</h2>
        <p className="mt-1 text-sm text-slate-400">
          The rest of TraceGuard is still available from the navigation. Details were written to the browser console.
        </p>
        <pre className="mt-4 overflow-x-auto rounded-lg border border-ink-600 bg-ink-900 p-3 text-left font-mono text-xs text-rose-300">
          {String(this.state.error?.message || this.state.error)}
        </pre>
        <button type="button" className="btn btn-primary mt-4" onClick={() => this.setState({ error: null })}>
          <RefreshCw size={14} /> Try again
        </button>
      </div>
    )
  }
}
