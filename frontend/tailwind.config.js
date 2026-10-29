// Colours resolve to CSS variables (see src/index.css) so one class name serves both themes.
// The light theme re-tunes shades for contrast on white rather than inverting the dark palette.
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`
const scale = (family, shades) => Object.fromEntries(shades.map((s) => [s, v(`${family}-${s}`)]))
const ACCENT = [200, 300, 400, 500, 600, 950]

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: scale('ink', [950, 900, 800, 700, 600]),
        sidebar: v('sidebar'),
        slate: scale('slate', [100, 200, 300, 400, 500, 600]),
        sky: scale('sky', ACCENT),
        cyan: scale('cyan', [300, 400, 500, 600]),
        rose: scale('rose', [...ACCENT, 700]),
        amber: scale('amber', ACCENT),
        emerald: scale('emerald', ACCENT),
        violet: scale('violet', ACCENT),
        orange: scale('orange', ACCENT),
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Consolas', 'monospace'],
      },
      boxShadow: {
        card: 'var(--shadow-card)',
        pop: 'var(--shadow-pop)',
      },
      keyframes: {
        'fade-in': { from: { opacity: 0, transform: 'translateY(4px)' }, to: { opacity: 1, transform: 'none' } },
        'slide-in': { from: { transform: 'translateX(-100%)' }, to: { transform: 'none' } },
        shimmer: { '100%': { transform: 'translateX(100%)' } },
      },
      animation: {
        'fade-in': 'fade-in 160ms ease-out',
        'slide-in': 'slide-in 180ms ease-out',
      },
    },
  },
  plugins: [],
}
