function Bar({ value, max, colorOk = '#00ff41', colorWarn = '#ff0040' }) {
  const pct = Math.min(100, max > 0 ? (value / max) * 100 : 0)
  const color = pct >= 90 ? colorWarn : pct >= 70 ? '#ffcc00' : colorOk
  return (
    <div className="w-full bg-[#001a08] rounded h-1.5 mt-1">
      <div
        className="h-1.5 rounded transition-all duration-500"
        style={{ width: `${pct}%`, backgroundColor: color }}
      />
    </div>
  )
}

function Row({ label, value, max, suffix = '', warn = false }) {
  return (
    <div className="border-b border-[#001a08] pb-2 mb-2">
      <div className="flex justify-between text-xs">
        <span className="text-[#006622]">{label}</span>
        <span className={warn ? 'text-red-400' : 'text-[#00ff41]'}>
          {value}{suffix}{max != null ? ` / ${max}${suffix}` : ''}
        </span>
      </div>
      {max != null && <Bar value={value} max={max} />}
    </div>
  )
}

export default function GuardrailPanel({ guardrails: g }) {
  if (!g) return (
    <div className="neon-card rounded bg-[#080808] p-4 min-h-[260px]">
      <h2 className="text-xs font-bold tracking-widest mb-3 neon-text">▶ GUARDRAILS</h2>
      <p className="text-[#004d18] text-xs mt-8 text-center">— loading —</p>
    </div>
  )

  const cardClass = g.halted
    ? 'neon-card neon-red rounded bg-[#0d0005] p-4'
    : 'neon-card rounded bg-[#080808] p-4'

  return (
    <div className={cardClass + ' min-h-[260px]'}>
      <h2 className="text-xs font-bold tracking-widest mb-3 neon-text flex items-center gap-2">
        <span>▶</span> GUARDRAILS
        {g.halted
          ? <span className="ml-auto text-red-400 text-[10px] animate-pulse">HALTED</span>
          : g.trade_window_active
          ? <span className="ml-auto text-[#00ff41] text-[10px]">WINDOW OPEN</span>
          : <span className="ml-auto text-[#006622] text-[10px]">WINDOW CLOSED</span>
        }
      </h2>

      {g.halted && (
        <div className="text-xs text-red-400 border border-red-500 rounded p-2 mb-3">
          {g.halt_reason}
        </div>
      )}

      <div>
        <Row label="Daily Trades"
             value={g.daily_trades} max={g.max_daily_trades}
             warn={g.daily_trades >= g.max_daily_trades} />
        <Row label="Daily P&L"
             value={`$${g.daily_pnl_usd?.toFixed(2)}`}
             warn={g.daily_pnl_usd <= -(g.max_daily_loss * 0.8)} />
        <Row label="Consec. Losses"
             value={g.consecutive_losses} max={g.max_consecutive_losses}
             warn={g.consecutive_losses >= g.max_consecutive_losses} />
        <Row label="Capital at Risk"
             value={`$${g.capital_at_risk_usd?.toFixed(2)}`}
             max={`$${g.max_capital_at_risk?.toFixed(2)}`}
             warn={g.capital_at_risk_usd >= g.max_capital_at_risk * 0.9} />
        <div className="text-[10px] text-[#003311] mt-2">
          Trade window: 6AM–10AM CST &nbsp;|&nbsp; {g.trade_window_msg}
        </div>
      </div>
    </div>
  )
}
