export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace']
      },
      boxShadow: {
        soft: '0 1px 2px rgb(15 23 42 / 0.05), 0 10px 30px -12px rgb(15 23 42 / 0.12)',
        card: '0 1px 2px rgb(15 23 42 / 0.04), 0 4px 16px -6px rgb(15 23 42 / 0.08)'
      },
      keyframes: {
        'fade-up': { '0%': { opacity: '0', transform: 'translateY(6px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        'typing-dot': { '0%, 60%, 100%': { transform: 'translateY(0)', opacity: '.35' }, '30%': { transform: 'translateY(-3px)', opacity: '1' } }
      },
      animation: {
        'fade-up': 'fade-up .35s ease both',
        'typing-dot': 'typing-dot 1.2s ease-in-out infinite'
      }
    }
  },
  plugins: []
}
