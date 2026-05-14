/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: { DEFAULT: '#0b1220', card: '#141b2d', panel: '#0f1626' },
        border: { DEFAULT: '#1f2a3f', light: '#2d3a52' },
        profit: '#26de81',
        loss: '#ff5e7d',
        accent: '#60a5fa',
        warn: '#fbbf24',
        info: '#38bdf8',
        text: { primary: '#e6edf3', secondary: '#94a3b8', muted: '#475569' },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      animation: {
        'fade-in-up': 'fadeInUp 0.3s ease-out',
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite',
      },
      keyframes: {
        fadeInUp: {
          '0%': { transform: 'translateY(8px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        pulseGlow: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' },
        },
      },
    },
  },
  plugins: [],
}
