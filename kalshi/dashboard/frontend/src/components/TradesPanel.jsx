const STATUS_STYLE = {
  open:      'text-yellow-400 border-yellow-400',
  won:       'text-[#00ff41] border-[#00ff41]',
  lost:      'text-red-400 border-red-500',
  cancelled: 'text-[#006622] border-[#003311]',
}

function Trade({ t }) {
  const ss = STATUS_STYLE[t.status] ?? 'text-[#006622] border-[#003311]'
  const edgePct = (Math.abs(t.edge) * 100).toFixed(1)
  return (
    <div className="border border-[#002211] rounded p-2 bg-[#040d06] text-xs">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className="font-bold text-[#00ff41]">{t.city}</span>
          <span className={`border rounded px-1.5 py-0.5 text-[10px] ${
            t.side === 'YES' ? 'text-[#00ff41] border-[#006622]' : 'text-orange-400 border-orange-800'
          }`}>{t.side}</span>
          {t.paper ? (
            <span className="text-[10px] text-[#003311] border border-[#001a08] rounded px-1">PAPER</span>
          ) : null}
        </div>
        <span className={`text-[10px] border rounded px-1.5 py-0.5 ${ss}`}>
          {t.status?.toUpperCase()}
        </span>
      </div>

      <div className="flex flex-wrap gap-3 text-[10px] text-[#006622]">
        <span>x{t.contracts} @ {t.price_cents}¢</span>
        <span>Stake: <span className="text-[#00aa33]">${t.stake_usd?.toFixed(2)}</span></span>
        <span>Edge: <span className="text-[#00cc33]">{edgePct}%</span></span>
        {t.pnl_usd != null && (
          <span className={t.pnl_usd >= 0 ? 'text-[#00ff41]' : 'text-red-400'}>
            P&L: ${t.pnl_usd?.toFixed(2)}
          </span>
        )}
      </div>

      <div className="text-[10px] text-[#002211] mt-0.5 truncate">
        {t.market_id} · {new Date(t.timestamp).toLocaleString()}
      </div>
    </div>
  )
}

export default function TradesPanel({ trades }) {
  const open   = trades.filter(t => t.status === 'open')
  const closed = trades.filter(t => t.status !== 'open').slice(0, 15)

  return (
    <div className="neon-card rounded bg-[#080808] p-4 min-h-[260px]">
      <h2 className="text-xs font-bold tracking-widest mb-3 neon-text flex items-center gap-2">
        <span>▶</span> LIVE TRADES
        <span className="ml-auto bg-[#001a08] border border-[#00ff41] rounded px-2 py-0.5 text-[10px]">
          {open.length} open
        </span>
      </h2>

      <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
        {trades.length === 0 ? (
          <p className="text-[#004d18] text-xs mt-8 text-center">
            — no trades yet — use SCAN NOW or wait for trade window —
          </p>
        ) : (
          <>
            {open.length > 0 && (
              <p className="text-[10px] text-[#004d18] uppercase tracking-wider mb-1">Open</p>
            )}
            {open.map(t => <Trade key={t.id} t={t} />)}
            {closed.length > 0 && (
              <p className="text-[10px] text-[#004d18] uppercase tracking-wider mt-2 mb-1">History</p>
            )}
            {closed.map(t => <Trade key={t.id} t={t} />)}
          </>
        )}
      </div>
    </div>
  )
}
