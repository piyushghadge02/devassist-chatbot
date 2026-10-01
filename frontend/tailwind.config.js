// DevAssist — dark technical theme tokens (UI/UX redesign, 2026-10-01)
export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      colors: {
        // Surfaces
        canvas: '#0B1120',
        workspace: '#0F172A',
        sidebar: '#0D1424',
        panel: '#111827',
        raised: '#151D2E',
        // Lines
        edge: '#263248',
        'edge-soft': 'rgba(38, 50, 72, 0.7)',
        // Type
        ink: '#F8FAFC',
        'ink-2': '#CBD5E1',
        'ink-3': '#94A3B8',
        'ink-4': '#64748B',
        // Accents
        brand: {
          DEFAULT: '#6366F1',
          soft: '#818CF8',
          deep: '#4F46E5',
          wash: 'rgba(99, 102, 241, 0.12)'
        },
        signal: {
          DEFAULT: '#22D3EE',
          soft: '#67E8F9',
          wash: 'rgba(34, 211, 238, 0.12)'
        },
        // Status
        ok: '#34D399',
        danger: '#F87171',
        // Code surface
        terminal: '#080D17'
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace']
      },
      boxShadow: {
        // Restrained depth — dark UI reads depth from borders, not heavy shadows.
        panel: '0 1px 0 0 rgba(248,250,252,0.03) inset, 0 8px 24px -16px rgba(2,6,23,0.9)',
        lift: '0 12px 40px -20px rgba(2,6,23,1)',
        'focus-brand': '0 0 0 3px rgba(99,102,241,0.32)',
        'focus-signal': '0 0 0 3px rgba(34,211,238,0.28)'
      },
      borderRadius: {
        panel: '10px',
        control: '8px'
      },
      // Shared by the sidebar brand row and the chat header so both bottom
      // borders sit on exactly the same line across the full page width.
      height: {
        'app-header': '56px'
      },
      keyframes: {
        'fade-up': { '0%': { opacity: '0', transform: 'translateY(6px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        'fade-in': { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        'slide-left': { '0%': { opacity: '0', transform: 'translateX(-8px)' }, '100%': { opacity: '1', transform: 'translateX(0)' } },
        'typing-dot': { '0%, 60%, 100%': { transform: 'translateY(0)', opacity: '.3' }, '30%': { transform: 'translateY(-3px)', opacity: '1' } },
        'pulse-line': { '0%': { transform: 'translateX(-100%)' }, '100%': { transform: 'translateX(100%)' } }
      },
      animation: {
        'fade-up': 'fade-up .3s cubic-bezier(.2,.7,.3,1) both',
        'fade-in': 'fade-in .25s ease both',
        'slide-left': 'slide-left .22s cubic-bezier(.2,.7,.3,1) both',
        'typing-dot': 'typing-dot 1.2s ease-in-out infinite',
        'pulse-line': 'pulse-line 1.4s ease-in-out infinite'
      }
    }
  },
  plugins: []
}