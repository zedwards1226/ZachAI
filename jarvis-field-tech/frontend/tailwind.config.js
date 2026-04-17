/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        jarvis: {
          cyan: '#00d4ff',
          amber: '#ffb74d',
          dark: '#0a0e1a',
        },
      },
      fontFamily: {
        mono: ['Consolas', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
}
