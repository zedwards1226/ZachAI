import { useState, useEffect } from 'react'
import { Radar } from 'lucide-react'

const SERIES_LABEL = {
  KXBTC15M: 'BTC 15m',
  KXETH15M: 'ETH 15m',
  KXBTCD: 'BTC daily',
}

export default function LiveScan({ scan }) {
  // Tick the "next scan in Xs" countdown locally so the user sees it move
  // between polls (poll interval is 5s, but countdown is more responsive).
  const [tick, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000)
    return () => clearInterval(id)
  }, [])

  if (!scan || scan.ok === false) {
    return (
      <div
        className="rounded-xl gradient-card border p-3 flex flex-col"
        style={{ borderColor: '#2a2a3a' }}
      >
        <div className="flex items-center gap-1.5">
          <Radar size={12} className="animate-pulse" style={{ color: '#fbbf24' }} />
          <span
            className="text-[10px] uppercase tracking-wider"
            style={{ color: '#94a3b8' }}
          >
            Live scan
          </span>
        </div>
        <div className="text-[10px] mt-3" style={{ color: '#64748b' }}>
          {scan?.message || 'Waiting for first scan…'}
        </div>
      </div>
    )
  }

  const totals = scan.totals || {}
  const ageS = scan.age_seconds ?? 0
  const nextInRaw = (scan.next_scan_in_seconds ?? 0) - tick
  const nextIn = Math.max(0, Math.round(nextInRaw))
  const stale = ageS > 180  // bot hasn't scanned in 3+ min

  return (
    <div
      className="rounded-xl gradient-card border p-3 flex flex-col"
      style={{ borderColor: stale ? '#ff5e7d' : '#2a2a3a' }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <Radar
              size={12}
              className={stale ? '' : 'animate-pulse'}
              style={{ color: stale ? '#ff5e7d' : '#fbbf24' }}
            />
            <span
              className="text-[10px] uppercase tracking-wider truncate"
              style={{ color: '#94a3b8' }}
            >
              Live scan
            </span>
          </div>
          <div
            className="font-mono text-xs mt-0.5"
            style={{ color: '#f8fafc', fontFamily: '"JetBrains Mono", monospace' }}
          >
            {totals.scanned ?? 0} markets · {Object.keys(scan.by_series || {}).length} series
          </div>
        </div>
        <div className="text-right shrink-0">
          <div
            className="font-mono font-bold text-sm"
            style={{ color: stale ? '#ff5e7d' : '#26de81' }}
          >
            {stale ? 'stalled' : `${nextIn}s`}
          </div>
          <div className="text-[10px]" style={{ color: '#64748b' }}>
            {stale ? `last ${Math.round(ageS)}s ago` : 'next scan'}
          </div>
        </div>
      </div>

      {/* Per-series mini-rows */}
      <div className="mt-2 space-y-1">
        {Object.entries(scan.by_series || {}).map(([series, s]) => (
          <div key={series} className="flex items-center justify-between text-[10px]">
            <span
              className="truncate"
              style={{ color: '#94a3b8', fontFamily: '"JetBrains Mono", monospace' }}
            >
              {SERIES_LABEL[series] || series}
            </span>
            <span style={{ color: '#64748b' }}>
              {s.scanned ?? 0} → {s.decisions ?? 0} pick · {s.placed ?? 0} placed
            </span>
          </div>
        ))}
      </div>

      {/* Why-no-trade explainer */}
      <div
        className="text-[10px] mt-2 leading-snug"
        style={{ color: totals.placed > 0 ? '#26de81' : '#64748b' }}
      >
        {scan.why_no_trade}
      </div>
    </div>
  )
}
