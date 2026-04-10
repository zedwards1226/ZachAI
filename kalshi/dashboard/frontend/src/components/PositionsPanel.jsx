import { motion, AnimatePresence } from 'framer-motion'

function fmtTime(ts) {
  if (!ts) return '--'
  const d = new Date(ts.includes('T') ? ts : ts.replace(' ', 'T'))
  return isNaN(d) ? '--' : d.toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', hour12: false,
  })
}

function PriceArrow({ entry, current }) {
  if (current == null || current === 0) return null
  const diff = current - entry
  if (diff === 0) return null
  return (
    <span style={{ color: diff > 0 ? '#26de81' : '#ff5e7d', fontSize: 9 }}>
      {diff > 0 ? ' \u25B2' : ' \u25BC'}{Math.abs(diff)}c
    </span>
  )
}

function PositionRow({ pos }) {
  const sideColor = pos.side === 'YES' ? '#26de81' : '#ff5e7d'
  const hasLive = pos.current_price != null && pos.current_price > 0
  const pnlVal = pos.unrealized_pnl
  const pnlColor = pnlVal > 0 ? '#26de81' : pnlVal < 0 ? '#ff5e7d' : '#94a3b8'

  // Clean up title: strip markdown bold
  const title = (pos.title || pos.market_id || '').replace(/\*\*/g, '')

  return (
    <motion.div
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
      className="px-3 py-2.5 border-b"
      style={{ borderColor: '#1a1a24' }}
    >
      {/* Row 1: City badge, Side, Title */}
      <div className="flex items-center gap-2 mb-1.5">
        <span
          className="text-[11px] font-bold px-1.5 py-0.5 rounded shrink-0"
          style={{ background: '#1a1a24', color: '#f8fafc', border: '1px solid #2a2a3a' }}
        >
          {pos.city}
        </span>
        <span
          className="text-[10px] font-bold px-1.5 py-0.5 rounded shrink-0"
          style={{
            color: sideColor,
            background: `${sideColor}18`,
            border: `1px solid ${sideColor}30`,
          }}
        >
          {pos.side}
        </span>
        <span className="text-[10px] text-text-secondary truncate flex-1" title={title}>
          {title}
        </span>
      </div>

      {/* Row 2: Price grid */}
      <div className="flex items-end gap-4">
        {/* Entry → Live */}
        <div className="flex items-center gap-1.5">
          <div className="text-center">
            <div className="text-[8px] text-text-muted">ENTRY</div>
            <div className="stat-value text-[12px] text-text-secondary">{pos.entry_price}c</div>
          </div>
          <span className="text-text-muted text-[10px] pb-0.5">&rarr;</span>
          <div className="text-center">
            <div className="text-[8px] text-text-muted">BID</div>
            <div className="stat-value text-[12px]" style={{ color: hasLive ? '#f8fafc' : '#475569' }}>
              {hasLive ? `${pos.current_price}c` : '--'}
              <PriceArrow entry={pos.entry_price} current={pos.current_price} />
            </div>
          </div>
          {pos.ask_price != null && pos.ask_price > 0 && (
            <div className="text-center">
              <div className="text-[8px] text-text-muted">ASK</div>
              <div className="stat-value text-[11px] text-text-muted">{pos.ask_price}c</div>
            </div>
          )}
        </div>

        {/* Qty */}
        <div className="text-center">
          <div className="text-[8px] text-text-muted">QTY</div>
          <div className="stat-value text-[11px] text-text-secondary">{pos.contracts}</div>
        </div>

        {/* Stake */}
        <div className="text-center">
          <div className="text-[8px] text-text-muted">RISK</div>
          <div className="stat-value text-[11px] text-text-secondary">${pos.stake.toFixed(2)}</div>
        </div>

        {/* Edge */}
        <div className="text-center">
          <div className="text-[8px] text-text-muted">EDGE</div>
          <div className="stat-value text-[11px]" style={{ color: '#818cf8' }}>
            {((pos.edge ?? 0) * 100).toFixed(0)}%
          </div>
        </div>

        {/* Unrealized P&L */}
        <div className="text-center ml-auto">
          <div className="text-[8px] text-text-muted">P&amp;L</div>
          <div className="stat-value text-[12px] font-bold" style={{ color: pnlColor }}>
            {pnlVal != null ? `${pnlVal >= 0 ? '+' : ''}$${pnlVal.toFixed(2)}` : '--'}
          </div>
        </div>
      </div>
    </motion.div>
  )
}

export default function PositionsPanel({ positions, totalUnrealizedPnl }) {
  const list = positions ?? []
  const totalPnl = totalUnrealizedPnl ?? 0
  const pnlColor = totalPnl > 0 ? '#26de81' : totalPnl < 0 ? '#ff5e7d' : '#94a3b8'
  const totalStake = list.reduce((s, p) => s + (p.stake || 0), 0)

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b shrink-0" style={{ borderColor: '#2a2a3a' }}>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full animate-pulse-glow" style={{ background: '#26de81' }} />
          <span className="text-[10px] font-semibold text-text-muted" style={{ letterSpacing: '0.06em' }}>
            {list.length} OPEN POSITION{list.length !== 1 ? 'S' : ''}
          </span>
          <span className="text-[9px] text-text-muted">
            | ${totalStake.toFixed(2)} at risk
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[9px] text-text-muted">UNREALIZED:</span>
          <span className="stat-value text-[12px] font-bold" style={{ color: pnlColor }}>
            {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}
          </span>
        </div>
      </div>

      {/* Position list */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {list.length === 0 ? (
          <div className="flex items-center justify-center py-8 text-sm text-text-muted">
            No open positions
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {list.map(p => <PositionRow key={p.id} pos={p} />)}
          </AnimatePresence>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-3 py-1.5 border-t text-[9px] text-text-muted shrink-0" style={{ borderColor: '#2a2a3a' }}>
        <span>Prices refresh every 5s</span>
        <span>Bid = what you could sell at</span>
      </div>
    </div>
  )
}
