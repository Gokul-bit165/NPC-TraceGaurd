import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { Moon, Sun } from 'lucide-react'

// One theme system for the whole app: the choice is stamped on <html data-theme>, every colour class
// reads CSS variables keyed off that attribute (see index.css), and Recharts gets its palette from useChartTheme().
const KEY = 'tg_theme'

function readStored() {
  try {
    const t = localStorage.getItem(KEY)
    if (t === 'light' || t === 'dark') return t
  } catch {
    /* storage blocked: fall through to the system preference */
  }
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

const ThemeContext = createContext({ theme: 'dark', setTheme: () => {}, toggle: () => {} })

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(readStored)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem(KEY, theme)
    } catch {
      /* non-fatal */
    }
  }, [theme])

  const setTheme = useCallback((t) => setThemeState(t === 'light' ? 'light' : 'dark'), [])
  const toggle = useCallback(() => setThemeState((t) => (t === 'dark' ? 'light' : 'dark')), [])
  const value = useMemo(() => ({ theme, setTheme, toggle }), [theme, setTheme, toggle])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export const useTheme = () => useContext(ThemeContext)

export function ThemeToggle({ className = '' }) {
  const { theme, toggle } = useTheme()
  const next = theme === 'dark' ? 'light' : 'dark'
  return (
    <button
      type="button"
      onClick={toggle}
      className={`inline-flex h-9 w-9 items-center justify-center rounded-lg border border-ink-600 bg-ink-800 text-slate-400 transition-colors hover:bg-ink-700 hover:text-slate-100 ${className}`}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
    >
      {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
    </button>
  )
}

const CHART = {
  dark: { grid: '#263449', axis: '#94A3B8', tooltipBg: '#172338', tooltipBorder: '#263449', text: '#F1F5F9', muted: '#CBD5E1', cellStroke: '#111B2E', neutral: '#64748B' },
  light: { grid: '#E2E8F0', axis: '#64748B', tooltipBg: '#FFFFFF', tooltipBorder: '#E2E8F0', text: '#172033', muted: '#334155', cellStroke: '#FFFFFF', neutral: '#94A3B8' },
}

// Series colours are shared by both themes; they were chosen to hold contrast on navy and on white.
export const SERIES = {
  critical: '#E11D48',
  high: '#F97316',
  medium: '#F59E0B',
  low: '#10B981',
  email: '#F59E0B',
  login: '#8B5CF6',
  primary: '#3B82F6',
}

export function useChartTheme() {
  const { theme } = useTheme()
  return useMemo(() => {
    const c = CHART[theme] || CHART.dark
    return {
      ...c,
      colors: SERIES,
      tooltip: {
        contentStyle: { background: c.tooltipBg, border: `1px solid ${c.tooltipBorder}`, borderRadius: 8, fontSize: 12, color: c.text, boxShadow: 'var(--shadow-pop)' },
        labelStyle: { color: c.muted, fontWeight: 600, marginBottom: 4 },
        itemStyle: { color: c.text },
        cursor: { fill: c.grid, opacity: 0.35 },
      },
      axis: { stroke: c.axis, fontSize: 11, tickLine: false, axisLine: { stroke: c.grid } },
      legend: { wrapperStyle: { fontSize: 12, paddingTop: 8, color: c.axis } },
    }
  }, [theme])
}
