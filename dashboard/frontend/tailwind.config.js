/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        mono: ['"Share Tech Mono"', '"Courier New"', 'monospace'],
      },
      keyframes: {
        'pulse-neon': {
          '0%, 100%': { boxShadow: '0 0 4px #00ff41' },
          '50%':       { boxShadow: '0 0 12px #00ff41, 0 0 24px #00ff41' },
        },
        blink: {
          '50%': { opacity: '0' },
        },
      },
      animation: {
        'pulse-neon': 'pulse-neon 2s ease-in-out infinite',
        blink:        'blink 1s step-end infinite',
      },
    },
  },
  plugins: [],
}
