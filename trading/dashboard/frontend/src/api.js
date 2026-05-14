// Tiny fetch helper. All endpoints are JSON GETs served by the Flask backend.
const base = ''

async function get(path) {
  const r = await fetch(base + path, { headers: { Accept: 'application/json' } })
  if (!r.ok) throw new Error(`${path} ${r.status}`)
  return r.json()
}

export const api = {
  health:   ()             => get('/api/health'),
  summary:  ()             => get('/api/summary'),
  trades:   (days = 30)    => get(`/api/trades?days=${days}`),
  equity:   ()             => get('/api/equity'),
  learning: (days = 30)    => get(`/api/learning?days=${days}`),
  live:     ()             => get('/api/live'),
  signals:  (days = 14)    => get(`/api/signals?days=${days}`),
}

// React hook: useApi(api.summary, [], 30000) polls every 30s.
import { useEffect, useState, useRef } from 'react'

export function useApi(fn, deps = [], intervalMs = 30000) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    let cancelled = false
    const tick = async () => {
      try {
        const d = await fnRef.current()
        if (!cancelled) {
          setData(d)
          setError(null)
        }
      } catch (e) {
        if (!cancelled) setError(e.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    tick()
    const id = setInterval(tick, intervalMs)
    return () => { cancelled = true; clearInterval(id) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { data, error, loading }
}

// Formatting helpers
export const fmt = {
  usd: (n) => {
    if (n === null || n === undefined || isNaN(n)) return '—'
    const sign = n >= 0 ? '+' : '−'
    return `${sign}$${Math.abs(n).toFixed(2)}`
  },
  pct: (n) => (n === null || n === undefined || isNaN(n)) ? '—' : `${n.toFixed(1)}%`,
  int: (n) => (n === null || n === undefined) ? '—' : String(n),
  time: (iso) => {
    if (!iso) return '—'
    try {
      const d = new Date(iso)
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    } catch { return iso }
  },
  date: (s) => {
    if (!s) return '—'
    const d = new Date(s)
    if (isNaN(d.getTime())) return s
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
  },
  signed: (n) => (n >= 0 ? '+' : '') + (n?.toFixed?.(1) ?? n),
}
