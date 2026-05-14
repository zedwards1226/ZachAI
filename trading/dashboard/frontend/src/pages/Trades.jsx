import { useState } from 'react'
import { useApi, api, fmt } from '../api.js'
import { ChevronDown, ChevronRight } from 'lucide-react'

function ScoreBadge({ score }) {
  // Score range observed: -5 to +12 in live data
  const tone =
    score >= 9  ? 'bg-profit/20 text-profit' :
    score >= 6  ? 'bg-accent/15 text-accent' :
    score >= 3  ? 'bg-warn/15 text-warn' :
                  'bg-loss/20 text-loss'
  return <span className={`px-2 py-0.5 rounded text-xs font-bold ${tone} font-mono`}>{score}</span>
}

function OutcomeBadge({ outcome }) {
  if (outcome === 'WIN')
    return <span className="px-2 py-0.5 rounded text-xs font-bold bg-profit/20 text-profit">WIN</span>
  if (outcome === 'LOSS')
    return <span className="px-2 py-0.5 rounded text-xs font-bold bg-loss/20 text-loss">LOSS</span>
  return <span className="px-2 py-0.5 rounded text-xs font-bold bg-bg-panel text-text-secondary border border-border">{outcome || '—'}</span>
}

function ScoreBreakdownDetail({ breakdown }) {
  // breakdown is a dict of {factor_name: int_score, ..., details: {...}, total: int}
  const factors = Object.entries(breakdown)
    .filter(([k, v]) => k !== 'details' && k !== 'total' && typeof v === 'number' && v !== 0)
    .sort((a, b) => b[1] - a[1])  // highest contribution first
  const details = breakdown.details || {}
  if (factors.length === 0)
    return <div className="text-xs text-text-muted">No scoring factors recorded.</div>

  return (
    <div className="mt-2 space-y-1">
      {factors.map(([k, v]) => (
        <div key={k} className="flex items-start gap-2 text-xs">
          <span className={`font-mono w-8 text-right ${v > 0 ? 'text-profit' : 'text-loss'}`}>
            {v > 0 ? '+' : ''}{v}
          </span>
          <span className="text-text-secondary w-32 truncate">{k}</span>
          <span className="text-text-muted flex-1 truncate">{details[k.replace(/_/g, '_')] || details[k.split('_')[0]] || ''}</span>
        </div>
      ))}
      <div className="flex gap-2 text-xs pt-1 border-t border-border-light mt-1">
        <span className="font-mono w-8 text-right text-accent">{breakdown.total ?? 0}</span>
        <span className="text-text-primary font-semibold">total</span>
      </div>
    </div>
  )
}

function TradeRow({ t }) {
  const [open, setOpen] = useState(false)
  const isLong = t.direction === 'LONG'
  const pnl = t.pnl_after_slippage ?? t.pnl
  const pnlTone = pnl > 0 ? 'text-profit' : pnl < 0 ? 'text-loss' : 'text-text-secondary'

  return (
    <div className="border-b border-border-light last:border-b-0">
      <button
        onClick={() => setOpen(!open)}
        className="w-full text-left px-3 py-2 hover:bg-bg-card/50 transition flex items-center gap-3"
      >
        {open ? <ChevronDown size={14} className="text-text-muted" /> : <ChevronRight size={14} className="text-text-muted" />}
        <span className="font-mono text-xs text-text-muted w-20">{t.date} {t.time?.slice(0, 5)}</span>
        <span className={`px-2 py-0.5 rounded text-xs font-bold ${isLong ? 'bg-profit/20 text-profit' : 'bg-loss/20 text-loss'} w-14 text-center`}>
          {t.direction}
        </span>
        <ScoreBadge score={t.score ?? 0} />
        <span className="text-xs text-text-secondary hidden sm:inline">
          {t.entry?.toFixed(2)}
          {t.exit_price && <span className="text-text-muted"> → {t.exit_price.toFixed(2)}</span>}
        </span>
        {t.was_second_break && <span className="text-xs px-1.5 py-0.5 rounded bg-accent/15 text-accent">2nd</span>}
        <span className="flex-1" />
        <OutcomeBadge outcome={t.outcome} />
        <span className={`font-mono text-sm w-20 text-right ${pnlTone}`}>{fmt.usd(pnl ?? 0)}</span>
      </button>

      {open && (
        <div className="px-3 pb-3 pl-10 bg-bg-card/30">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs mb-2 mt-1">
            <div><span className="text-text-muted">Setup:</span> <span>{t.setup_type || 'ORB'}{t.was_second_break ? ' (2nd break)' : ''}</span></div>
            <div><span className="text-text-muted">Size:</span> <span>{t.size || '—'}</span></div>
            <div><span className="text-text-muted">Stop:</span> <span className="font-mono text-loss">{t.stop?.toFixed(2)}</span></div>
            <div><span className="text-text-muted">T1/T2:</span> <span className="font-mono">{t.target_1?.toFixed(2)} / {t.target_2?.toFixed(2)}</span></div>
            <div><span className="text-text-muted">ORB hi/lo:</span> <span className="font-mono">{t.orb_high?.toFixed(2)} / {t.orb_low?.toFixed(2)}</span></div>
            <div><span className="text-text-muted">VIX:</span> <span className="font-mono">{t.vix_at_entry?.toFixed(2) || '—'}</span></div>
            <div><span className="text-text-muted">RVOL:</span> <span className="font-mono">{t.rvol_at_entry?.toFixed(2) || '—'}</span></div>
            <div><span className="text-text-muted">RR:</span> <span className="font-mono">{t.rr?.toFixed(2) || '—'}</span></div>
          </div>
          <div className="text-xs text-text-muted italic mb-1">{t.notes || ''}</div>
          <div className="text-xs uppercase tracking-wider text-text-muted mt-2">Score breakdown</div>
          <ScoreBreakdownDetail breakdown={t.breakdown || {}} />
        </div>
      )}
    </div>
  )
}

export default function Trades() {
  const [days, setDays] = useState(30)
  const { data, error } = useApi(() => api.trades(days), [days])

  if (error) return <div className="text-loss text-sm mt-4">Error: {error}</div>
  if (!data) return <div className="text-text-muted text-sm mt-4">Loading…</div>

  return (
    <div className="mt-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Trades</h2>
        <div className="flex gap-1">
          {[7, 30, 90].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={
                'px-2.5 py-1 rounded text-xs font-medium transition ' +
                (days === d ? 'bg-accent/15 text-accent' : 'text-text-secondary hover:text-text-primary hover:bg-bg-card')
              }
            >
              {d}d
            </button>
          ))}
        </div>
      </div>
      <div className="gradient-card border border-border rounded-lg overflow-hidden">
        {data.trades.length === 0 ? (
          <div className="p-4 text-text-muted text-sm">No trades in last {days} days.</div>
        ) : (
          data.trades.map((t) => <TradeRow key={t.id} t={t} />)
        )}
      </div>
    </div>
  )
}
