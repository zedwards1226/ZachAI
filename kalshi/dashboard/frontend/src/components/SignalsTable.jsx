import { motion, AnimatePresence } from 'framer-motion'
import { Zap, Ban } from 'lucide-react'

function fmtTime(ts) {
  if (!ts) return '--'
  const d = new Date(ts.includes('T') ? ts : ts.replace(' ', 'T'))
  return isNaN(d) ? '--' : d.toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  })
}

function EdgeBar({ edge }) {
  const absEdge = Math.abs(edge ?? 0)
  const pct = Math.min(100, absEdge * 100 / 30) // scale: 30% = full bar
  const color = absEdge >= 0.15 ? '#26de81' : absEdge >= 0.08 ? '#818cf8' : '#fbbf24'
  return (
    <div className="probability-bar" style={{ width: 50 }}>
      <div className="probability-bar-fill" style={{ width: `${pct}%`, background: color }} />
    </div>
  )
}

function SignalRow({ signal }) {
  const s = signal
  const edgePct = ((s.edge ?? 0) * 100).toFixed(1)
  const isActionable = s.actionable === 1 || s.actionable === true
  const settled = s.actual_outcome != null

  const outcomeColor = s.outcome_correct === 1 ? '#26de81'
    : s.outcome_correct === 0 ? '#ff5e7d'
    : '#475569'

  return (
    <motion.div
      initial={{ opacity: 0, x: -4 }}
      animate={{ opacity: isActionable ? 1 : 0.5, x: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
      className="flex items-center gap-2 px-2 py-2 border-b"
      style={{ borderColor: '#1a1a24' }}
    >
      {/* Actionable indicator */}
      <div className="w-4 shrink-0">
        {isActionable ? (
          <Zap size={12} style={{ color: '#26de81' }} />
        ) : (
          <Ban size={10} style={{ color: '#475569' }} />
        )}
      </div>

      {/* City */}
      <span className="text-[11px] font-medium text-text-primary w-10 shrink-0">{s.city}</span>

      {/* Direction */}
      <span
        className="text-[10px] font-bold w-8 shrink-0"
        style={{ color: s.direction === 'YES' ? '#26de81' : s.direction === 'NO' ? '#ff5e7d' : '#475569' }}
      >
        {s.direction ?? '--'}
      </span>

      {/* Edge */}
      <div className="flex items-center gap-1.5 w-20 shrink-0">
        <span className="stat-value text-[10px] font-semibold" style={{ color: '#818cf8' }}>
          {edgePct}%
        </span>
        <EdgeBar edge={s.edge} />
      </div>

      {/* Model prob */}
      <span className="stat-value text-[10px] text-text-secondary w-12 shrink-0">
        {s.model_prob != null ? `${(s.model_prob * 100).toFixed(0)}%` : '--'}
      </span>

      {/* Forecast */}
      <span className="stat-value text-[10px] text-text-muted w-12 shrink-0">
        {s.forecast_hi_f != null ? `${s.forecast_hi_f.toFixed(0)}F` : '--'}
      </span>

      {/* Outcome */}
      <span className="text-[10px] font-semibold w-10 shrink-0" style={{ color: outcomeColor }}>
        {settled ? (s.outcome_correct ? 'HIT' : 'MISS') : '--'}
      </span>

      {/* Time */}
      <span className="stat-value text-[10px] text-text-muted flex-1 text-right">
        {fmtTime(s.timestamp)}
      </span>
    </motion.div>
  )
}

export default function SignalsTable({ signals }) {
  const list = signals ?? []

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div
        className="flex items-center gap-2 px-2 py-1.5 border-b text-[9px] font-semibold text-text-muted shrink-0"
        style={{ borderColor: '#2a2a3a', letterSpacing: '0.04em' }}
      >
        <span className="w-4" />
        <span className="w-10">City</span>
        <span className="w-8">Side</span>
        <span className="w-20">Edge</span>
        <span className="w-12">Prob</span>
        <span className="w-12">Fcst</span>
        <span className="w-10">Result</span>
        <span className="flex-1 text-right">Time</span>
      </div>

      {/* Rows */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {list.length === 0 ? (
          <div className="flex items-center justify-center py-8 text-sm text-text-muted">
            No signals yet
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {list.map(s => <SignalRow key={s.id} signal={s} />)}
          </AnimatePresence>
        )}
      </div>

      {/* Footer */}
      <div
        className="flex items-center justify-between pt-2 border-t text-[10px] shrink-0"
        style={{ borderColor: '#2a2a3a' }}
      >
        <span className="text-text-muted">
          {list.filter(s => s.actionable).length} actionable / {list.length} total
        </span>
      </div>
    </div>
  )
}
