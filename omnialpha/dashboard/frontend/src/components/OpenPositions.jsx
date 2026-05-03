import { CheckCircle2, XCircle, HelpCircle } from 'lucide-react'
import { LineChart, Line, ReferenceLine, ResponsiveContainer, XAxis, YAxis, Tooltip } from 'recharts'

function StatusPill({ winning }) {
  if (winning === true) {
    return (
      <span
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-bold tracking-wider"
        style={{ background: 'rgba(38, 222, 129, 0.12)', color: '#26de81', border: '1px solid rgba(38, 222, 129, 0.30)' }}
      >
        <CheckCircle2 size={12} /> WINNING
      </span>
    )
  }
  if (winning === false) {
    return (
      <span
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-bold tracking-wider"
        style={{ background: 'rgba(255, 94, 125, 0.12)', color: '#ff5e7d', border: '1px solid rgba(255, 94, 125, 0.30)' }}
      >
        <XCircle size={12} /> LOSING
      </span>
    )
  }
  return (
    <span
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-bold tracking-wider"
      style={{ background: 'rgba(148, 163, 184, 0.10)', color: '#94a3b8', border: '1px solid #2a2a3a' }}
    >
      <HelpCircle size={12} /> WAITING
    </span>
  )
}

function PositionCard({ p }) {
  const winning = p.winning  // true / false / null
  const borderColor = winning === true ? '#26de81' : winning === false ? '#ff5e7d' : '#2a2a3a'
  const sideColor = p.side === 'yes' ? '#26de81' : '#ff5e7d'

  // Recharts data: [{ts: ms, price}, ...]
  const series = (p.price_history || []).map(([t, price]) => ({
    t,
    price,
    label: new Date(t).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }),
  }))

  // Compute y-axis domain that includes both the recent path AND the strike
  let yMin = null, yMax = null
  if (series.length > 0) {
    yMin = Math.min(...series.map(d => d.price))
    yMax = Math.max(...series.map(d => d.price))
    if (p.strike !== null && p.strike !== undefined) {
      yMin = Math.min(yMin, p.strike)
      yMax = Math.max(yMax, p.strike)
    }
    const pad = (yMax - yMin) * 0.05 || 1
    yMin -= pad
    yMax += pad
  }

  return (
    <div
      className="rounded-xl border overflow-hidden gradient-card animate-fade-in-up"
      style={{ borderColor, borderLeftWidth: 4, borderLeftColor: borderColor }}
    >
      <div className="flex items-start justify-between px-4 py-3" style={{ borderBottom: '1px solid #2a2a3a' }}>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] font-bold" style={{ color: '#64748b' }}>#{p.id}</span>
            <span
              className="font-mono text-sm font-semibold truncate"
              style={{ color: '#f8fafc', fontFamily: '"JetBrains Mono", monospace' }}
            >
              {p.market_ticker}
            </span>
            <span className="font-bold text-xs" style={{ color: sideColor }}>
              {p.side.toUpperCase()} @ {p.price_cents}¢
            </span>
            <span className="text-xs" style={{ color: '#64748b' }}>· {p.strategy}</span>
          </div>
          {p.market_subtitle && (
            <div className="text-xs mt-1" style={{ color: '#94a3b8' }}>{p.market_subtitle}</div>
          )}
        </div>
        <StatusPill winning={winning} />
      </div>

      <div className="px-4 pt-3 pb-1 grid grid-cols-3 gap-3 text-xs">
        <div>
          <div className="text-[10px] tracking-[0.12em] uppercase" style={{ color: '#64748b' }}>Strike</div>
          <div className="font-mono font-semibold mt-0.5" style={{ color: '#f8fafc' }}>
            {p.strike ? `$${p.strike.toLocaleString('en-US', { maximumFractionDigits: 2 })}` : '—'}
          </div>
        </div>
        <div>
          <div className="text-[10px] tracking-[0.12em] uppercase" style={{ color: '#64748b' }}>
            {p.coin?.toUpperCase() || 'PRICE'} now
          </div>
          <div className="font-mono font-semibold mt-0.5" style={{ color: '#f8fafc' }}>
            {p.current_price ? `$${p.current_price.toLocaleString('en-US', { maximumFractionDigits: 2 })}` : '—'}
          </div>
        </div>
        <div>
          <div className="text-[10px] tracking-[0.12em] uppercase" style={{ color: '#64748b' }}>Stake</div>
          <div className="font-mono font-semibold mt-0.5" style={{ color: '#fbbf24' }}>
            ${p.stake_usd.toFixed(2)}
          </div>
        </div>
      </div>

      <div className="px-2 pb-2 pt-1" style={{ height: 130 }}>
        {series.length > 1 ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={series} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#64748b' }} stroke="#2a2a3a" />
              <YAxis
                domain={[yMin, yMax]}
                tick={{ fontSize: 10, fill: '#64748b' }}
                stroke="#2a2a3a"
                width={60}
                tickFormatter={(v) => `$${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}`}
              />
              <Tooltip
                contentStyle={{ background: '#0a0a10', border: '1px solid #2a2a3a', fontSize: 12 }}
                labelStyle={{ color: '#94a3b8' }}
                formatter={(v) => [`$${v.toLocaleString('en-US', { maximumFractionDigits: 2 })}`, 'price']}
              />
              <Line
                type="monotone"
                dataKey="price"
                stroke="#818cf8"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
              {p.strike && (
                <ReferenceLine
                  y={p.strike}
                  stroke={borderColor}
                  strokeDasharray="3 3"
                  label={{ value: `strike $${p.strike.toLocaleString('en-US', { maximumFractionDigits: 0 })}`, fill: '#94a3b8', fontSize: 10, position: 'right' }}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-full text-xs" style={{ color: '#64748b' }}>
            Loading price history…
          </div>
        )}
      </div>
    </div>
  )
}

export default function OpenPositions({ positions }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <div
          className="text-[10px] font-bold tracking-[0.14em] uppercase"
          style={{ color: '#94a3b8' }}
        >
          Open Positions
        </div>
        <span className="text-[10px]" style={{ color: '#64748b' }}>
          {positions.length} active
        </span>
      </div>

      {positions.length === 0 ? (
        <div
          className="rounded-xl gradient-card border p-6 text-center"
          style={{ borderColor: '#2a2a3a' }}
        >
          <div className="text-sm" style={{ color: '#94a3b8' }}>
            No open positions.
          </div>
          <div className="text-xs mt-2" style={{ color: '#64748b' }}>
            Bot is selective — only enters in the 20-30¢ NO band or 75-85¢ YES band,
            in the last 3 minutes of a market's life. When a trade opens, the
            strike-vs-price chart appears here.
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {positions.map((p) => (
            <PositionCard key={p.id} p={p} />
          ))}
        </div>
      )}
    </div>
  )
}
