import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, ChevronUp, ExternalLink } from 'lucide-react'

const COLS = [
  { key: 'status',      label: 'Status',   w: 70  },
  { key: 'city',        label: 'City',     w: 50  },
  { key: 'market_id',   label: 'Market',   w: 140 },
  { key: 'side',        label: 'Side',     w: 50  },
  { key: 'contracts',   label: 'Qty',      w: 40  },
  { key: 'price_cents', label: 'Price',    w: 55  },
  { key: 'edge',        label: 'Edge',     w: 60  },
  { key: 'stake_usd',   label: 'Stake',    w: 65  },
  { key: 'pnl_usd',     label: 'P&L',      w: 70  },
  { key: 'timestamp',   label: 'Time',     w: 80  },
]

function StatusBadge({ status }) {
  const cfg = {
    open:   { bg: 'rgba(129,140,248,0.12)', color: '#818cf8', border: 'rgba(129,140,248,0.25)', text: 'OPEN' },
    won:    { bg: 'rgba(38,222,129,0.12)',  color: '#26de81', border: 'rgba(38,222,129,0.25)',  text: 'WIN'  },
    lost:   { bg: 'rgba(255,94,125,0.12)',  color: '#ff5e7d', border: 'rgba(255,94,125,0.25)',  text: 'LOSS' },
    cancelled: { bg: 'rgba(71,85,105,0.12)', color: '#475569', border: 'rgba(71,85,105,0.25)', text: 'CXLD' },
  }
  const c = cfg[status] ?? cfg.open
  return (
    <span
      className="text-[9px] font-bold px-1.5 py-0.5 rounded"
      style={{ background: c.bg, color: c.color, border: `1px solid ${c.border}`, letterSpacing: '0.05em' }}
    >
      {c.text}
    </span>
  )
}

function fmtTime(ts) {
  if (!ts) return '--'
  const d = new Date(ts.includes('T') ? ts : ts.replace(' ', 'T'))
  return isNaN(d) ? '--' : d.toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  })
}

export default function TradesTable({ trades }) {
  const [sortKey, setSortKey] = useState('timestamp')
  const [sortAsc, setSortAsc] = useState(false)
  const [expanded, setExpanded] = useState(null)

  const list = trades ?? []

  const sorted = [...list].sort((a, b) => {
    let av = a[sortKey], bv = b[sortKey]
    if (typeof av === 'string') av = av.toLowerCase()
    if (typeof bv === 'string') bv = bv.toLowerCase()
    if (av == null) return 1
    if (bv == null) return -1
    if (av < bv) return sortAsc ? -1 : 1
    if (av > bv) return sortAsc ? 1 : -1
    return 0
  })

  function toggleSort(key) {
    if (sortKey === key) setSortAsc(!sortAsc)
    else { setSortKey(key); setSortAsc(false) }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center shrink-0 border-b" style={{ borderColor: '#2a2a3a' }}>
        {COLS.map(col => (
          <button
            key={col.key}
            onClick={() => toggleSort(col.key)}
            className="flex items-center gap-0.5 px-2 py-2 text-[10px] font-semibold text-text-muted hover:text-text-secondary transition-colors"
            style={{ width: col.w, minWidth: col.w, letterSpacing: '0.04em', flexShrink: 0 }}
          >
            {col.label}
            {sortKey === col.key && (
              sortAsc ? <ChevronUp size={10} /> : <ChevronDown size={10} />
            )}
          </button>
        ))}
      </div>

      {/* Rows */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {sorted.length === 0 ? (
          <div className="flex items-center justify-center py-12 text-sm text-text-muted">
            No trades yet
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {sorted.map(t => {
              const pnlColor = t.pnl_usd > 0 ? '#26de81' : t.pnl_usd < 0 ? '#ff5e7d' : '#94a3b8'
              const isExpanded = expanded === t.id
              return (
                <motion.div
                  key={t.id}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15 }}
                >
                  <div
                    className="flex items-center border-b cursor-pointer hover:bg-white/[0.02] transition-colors"
                    style={{ borderColor: '#1a1a24' }}
                    onClick={() => setExpanded(isExpanded ? null : t.id)}
                  >
                    <div className="px-2 py-2" style={{ width: 70, minWidth: 70 }}>
                      <StatusBadge status={t.status} />
                    </div>
                    <div className="px-2 py-2 text-[11px] font-medium text-text-primary" style={{ width: 50, minWidth: 50 }}>
                      {t.city}
                    </div>
                    <div className="px-2 py-2 text-[10px] stat-value text-text-secondary truncate" style={{ width: 140, minWidth: 140 }}>
                      {t.market_id}
                    </div>
                    <div className="px-2 py-2" style={{ width: 50, minWidth: 50 }}>
                      <span
                        className="text-[10px] font-bold"
                        style={{ color: t.side === 'YES' ? '#26de81' : '#ff5e7d' }}
                      >
                        {t.side}
                      </span>
                    </div>
                    <div className="px-2 py-2 text-[11px] stat-value text-text-secondary" style={{ width: 40, minWidth: 40 }}>
                      {t.contracts}
                    </div>
                    <div className="px-2 py-2 text-[11px] stat-value text-text-secondary" style={{ width: 55, minWidth: 55 }}>
                      {t.price_cents}c
                    </div>
                    <div className="px-2 py-2 text-[11px] stat-value font-semibold" style={{ width: 60, minWidth: 60, color: '#818cf8' }}>
                      {((t.edge ?? 0) * 100).toFixed(1)}%
                    </div>
                    <div className="px-2 py-2 text-[11px] stat-value text-text-secondary" style={{ width: 65, minWidth: 65 }}>
                      ${(t.stake_usd ?? 0).toFixed(2)}
                    </div>
                    <div className="px-2 py-2 text-[11px] stat-value font-semibold" style={{ width: 70, minWidth: 70, color: pnlColor }}>
                      {t.pnl_usd != null ? `${t.pnl_usd >= 0 ? '+' : ''}$${t.pnl_usd.toFixed(2)}` : '--'}
                    </div>
                    <div className="px-2 py-2 text-[10px] stat-value text-text-muted" style={{ width: 80, minWidth: 80 }}>
                      {fmtTime(t.timestamp)}
                    </div>
                  </div>

                  {/* Expanded verification row */}
                  {isExpanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="overflow-hidden"
                    >
                      <div
                        className="px-4 py-3 grid grid-cols-2 md:grid-cols-4 gap-3 text-[10px]"
                        style={{ background: '#141420', borderBottom: '1px solid #2a2a3a' }}
                      >
                        <div>
                          <span className="text-text-muted">Forecast High: </span>
                          <span className="stat-value text-text-primary">
                            {t.forecast_hi_f != null ? `${t.forecast_hi_f.toFixed(1)}F` : 'N/A'}
                          </span>
                        </div>
                        <div>
                          <span className="text-text-muted">Forecast Low: </span>
                          <span className="stat-value text-text-primary">
                            {t.forecast_lo_f != null ? `${t.forecast_lo_f.toFixed(1)}F` : 'N/A'}
                          </span>
                        </div>
                        <div>
                          <span className="text-text-muted">Strike: </span>
                          <span className="stat-value text-text-primary">
                            {t.kalshi_strike_f != null ? `${t.kalshi_strike_f.toFixed(0)}F` : 'N/A'}
                          </span>
                        </div>
                        <div>
                          <span className="text-text-muted">Our Prob: </span>
                          <span className="stat-value" style={{ color: '#818cf8' }}>
                            {t.our_prob_yes != null ? `${(t.our_prob_yes * 100).toFixed(1)}%` : 'N/A'}
                          </span>
                        </div>
                        <div>
                          <span className="text-text-muted">Implied Prob: </span>
                          <span className="stat-value text-text-secondary">
                            {t.implied_prob_yes != null ? `${(t.implied_prob_yes * 100).toFixed(1)}%` : 'N/A'}
                          </span>
                        </div>
                        <div>
                          <span className="text-text-muted">Kelly Frac: </span>
                          <span className="stat-value text-text-secondary">
                            {t.kelly_frac != null ? `${(t.kelly_frac * 100).toFixed(1)}%` : 'N/A'}
                          </span>
                        </div>
                        <div>
                          <span className="text-text-muted">Paper: </span>
                          <span className="stat-value" style={{ color: t.paper ? '#fbbf24' : '#26de81' }}>
                            {t.paper ? 'YES' : 'LIVE'}
                          </span>
                        </div>
                        <div>
                          <span className="text-text-muted">Resolved: </span>
                          <span className="stat-value text-text-primary">
                            {t.resolved_at ? fmtTime(t.resolved_at) : 'Pending'}
                          </span>
                        </div>
                        {t.notes && (
                          <div className="col-span-2 md:col-span-4">
                            <span className="text-text-muted">Notes: </span>
                            <span className="text-text-secondary">{t.notes}</span>
                          </div>
                        )}
                      </div>
                    </motion.div>
                  )}
                </motion.div>
              )
            })}
          </AnimatePresence>
        )}
      </div>

      {/* Footer */}
      <div
        className="flex items-center justify-between pt-2 border-t text-[10px] shrink-0"
        style={{ borderColor: '#2a2a3a' }}
      >
        <span className="text-text-muted">{sorted.length} trades</span>
        <span className="text-text-muted">Click row to verify data</span>
      </div>
    </div>
  )
}
