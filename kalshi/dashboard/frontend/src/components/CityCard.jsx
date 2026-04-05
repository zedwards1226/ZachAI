import { motion } from 'framer-motion'

const MIN_EDGE = 0.08

const CITY_NAMES = {
  NYC: { name: 'New York',    state: 'NY' },
  CHI: { name: 'Chicago',     state: 'IL' },
  MIA: { name: 'Miami',       state: 'FL' },
  LAX: { name: 'Los Angeles', state: 'CA' },
  MEM: { name: 'Memphis',     state: 'TN' },
  DEN: { name: 'Denver',      state: 'CO' },
}

function ActionBadge({ action }) {
  const configs = {
    TRADE: {
      bg: 'rgba(38, 222, 129, 0.15)',
      color: '#26de81',
      border: 'rgba(38, 222, 129, 0.35)',
    },
    WATCH: {
      bg: 'rgba(56, 189, 248, 0.12)',
      color: '#38bdf8',
      border: 'rgba(56, 189, 248, 0.3)',
    },
    SKIP: {
      bg: 'rgba(251, 191, 36, 0.12)',
      color: '#fbbf24',
      border: 'rgba(251, 191, 36, 0.3)',
    },
    'NO MARKET': {
      bg: 'rgba(71, 85, 105, 0.2)',
      color: '#475569',
      border: '#2a2a3a',
    },
  }
  const cfg = configs[action] ?? configs['NO MARKET']
  return (
    <span
      className="text-[10px] font-bold px-2 py-0.5 rounded"
      style={{
        background: cfg.bg,
        color: cfg.color,
        border: `1px solid ${cfg.border}`,
        letterSpacing: '0.06em',
      }}
    >
      {action}
    </span>
  )
}

function ProbBar({ label, value, color }) {
  const pct = Math.round((value ?? 0) * 100)
  return (
    <div>
      <div className="flex justify-between items-center mb-1">
        <span className="text-[10px] text-text-muted font-medium">{label}</span>
        <span
          className="stat-value text-[11px] font-semibold"
          style={{ color }}
        >
          {pct}%
        </span>
      </div>
      <div className="probability-bar">
        <div
          className="probability-bar-fill"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  )
}

export default function CityCard({ forecast, isActive, scanning }) {
  const fc = forecast
  const cityInfo = CITY_NAMES[fc?.city] ?? { name: fc?.city ?? '—', state: '' }

  const edge = fc?.edge ?? null
  const absEdge = edge != null ? Math.abs(edge) : null
  const hasEdge = absEdge != null && absEdge >= MIN_EDGE
  const nearEdge = absEdge != null && absEdge >= 0.04 && !hasEdge

  const edgeColor = !fc
    ? '#475569'
    : hasEdge
    ? '#26de81'
    : nearEdge
    ? '#fbbf24'
    : '#ff5e7d'

  // Determine action badge
  let action = 'NO MARKET'
  if (fc) {
    if (hasEdge) action = 'TRADE'
    else if (nearEdge) action = 'WATCH'
    else if (fc.kalshi_yes_price != null) action = 'SKIP'
  }

  const yesProb = fc?.our_prob_yes ?? null
  const noProb  = yesProb != null ? 1 - yesProb : null

  const isScanning = scanning && isActive

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      className="card p-4 flex flex-col gap-3 relative overflow-hidden"
      style={{
        border: isActive
          ? '1px solid rgba(129, 140, 248, 0.5)'
          : '1px solid #2a2a3a',
        boxShadow: isActive
          ? '0 0 0 1px rgba(129, 140, 248, 0.1), 0 4px 16px rgba(129, 140, 248, 0.08)'
          : 'none',
      }}
    >
      {/* Scanning pulse overlay */}
      {isScanning && (
        <div
          className="absolute inset-0 pointer-events-none rounded-xl"
          style={{
            background: 'rgba(129, 140, 248, 0.04)',
            animation: 'pulseGlow 1s ease-in-out infinite',
          }}
        />
      )}

      {/* Header row */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span
              className="stat-value text-base font-bold text-text-primary"
              style={{ letterSpacing: '-0.01em' }}
            >
              {fc?.city ?? '—'}
            </span>
            {isActive && (
              <span
                className="text-[9px] px-1.5 py-0.5 rounded font-semibold"
                style={{
                  background: 'rgba(129, 140, 248, 0.15)',
                  color: '#818cf8',
                  border: '1px solid rgba(129, 140, 248, 0.3)',
                  letterSpacing: '0.06em',
                }}
              >
                ACTIVE
              </span>
            )}
          </div>
          <div className="text-[11px] text-text-muted mt-0.5">
            {cityInfo.name}, {cityInfo.state}
          </div>
        </div>
        <ActionBadge action={action} />
      </div>

      {/* Temperature row */}
      <div className="flex items-end gap-3">
        {fc?.forecast_hi_f != null ? (
          <>
            <div>
              <div className="text-[10px] text-text-muted mb-0.5">High</div>
              <div
                className="stat-value text-2xl font-bold"
                style={{ color: '#f8fafc', letterSpacing: '-0.02em' }}
              >
                {fc.forecast_hi_f.toFixed(0)}&deg;
              </div>
            </div>
            {fc?.forecast_lo_f != null && (
              <div className="mb-1">
                <div className="text-[10px] text-text-muted mb-0.5">Low</div>
                <div className="stat-value text-base font-semibold text-text-secondary">
                  {fc.forecast_lo_f.toFixed(0)}&deg;
                </div>
              </div>
            )}
            {fc?.kalshi_strike_f != null && (
              <div className="mb-1 ml-auto">
                <div className="text-[10px] text-text-muted mb-0.5">Strike</div>
                <div className="stat-value text-sm font-semibold text-text-secondary">
                  {fc.kalshi_strike_f}&deg;F
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="text-text-muted text-sm">No forecast data</div>
        )}
      </div>

      {/* Probability bars */}
      {yesProb != null && (
        <div className="flex flex-col gap-2">
          <ProbBar label="YES" value={yesProb} color="#26de81" />
          <ProbBar label="NO"  value={noProb}  color="#ff5e7d" />
        </div>
      )}

      {/* Edge row */}
      <div
        className="flex items-center justify-between pt-1 border-t"
        style={{ borderColor: '#2a2a3a' }}
      >
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-text-muted">Edge</span>
          <span
            className="stat-value text-sm font-bold"
            style={{ color: edgeColor }}
          >
            {absEdge != null
              ? `${edge >= 0 ? '+' : '−'}${(absEdge * 100).toFixed(1)}%`
              : '—'}
          </span>
        </div>
        {fc?.kalshi_yes_price != null && (
          <span className="stat-value text-[11px] text-text-muted">
            mkt {fc.kalshi_yes_price}¢
          </span>
        )}
        {isScanning && (
          <span
            className="text-[10px] font-semibold animate-pulse-glow"
            style={{ color: '#818cf8' }}
          >
            ● scanning
          </span>
        )}
      </div>
    </motion.div>
  )
}
