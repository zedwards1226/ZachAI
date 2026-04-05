import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine, CartesianGrid,
} from 'recharts'

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div
      style={{
        background: '#1a1a24',
        border: '1px solid #2a2a3a',
        borderRadius: 8,
        padding: '8px 12px',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 12,
        boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
      }}
    >
      <div style={{ color: '#475569', marginBottom: 4 }}>
        {new Date(d.timestamp).toLocaleTimeString()}
      </div>
      <div style={{ color: '#f8fafc', fontWeight: 600 }}>
        ${d.capital_usd?.toFixed(2)}
      </div>
      {d.open_risk > 0 && (
        <div style={{ color: '#fbbf24', marginTop: 2 }}>
          risk ${d.open_risk?.toFixed(2)}
        </div>
      )}
    </div>
  )
}

export default function PnlChart({ pnl, summary }) {
  const hasPnl  = pnl && pnl.length > 1
  const base    = 1000
  const latest  = hasPnl ? pnl[pnl.length - 1]?.capital_usd : base
  const pnlUsd  = (latest ?? base) - base
  const pnlPos  = pnlUsd >= 0

  const vals    = hasPnl ? pnl.map(p => p.capital_usd).filter(Boolean) : [base]
  const minV    = Math.min(...vals, base) - 20
  const maxV    = Math.max(...vals, base) + 20

  const wins      = summary?.wins ?? 0
  const losses    = summary?.losses ?? 0
  const winRate   = summary?.win_rate ?? null
  const openRisk  = summary?.open_risk_usd ?? 0

  return (
    <div className="flex flex-col gap-3 h-full">

      {/* Stats row */}
      <div className="flex gap-4 flex-wrap">
        <div>
          <div className="text-[10px] text-text-muted font-medium mb-1">CAPITAL</div>
          <div
            className="stat-value font-bold"
            style={{ fontSize: 18, color: '#f8fafc', letterSpacing: '-0.02em' }}
          >
            ${(latest ?? base).toFixed(2)}
          </div>
        </div>
        <div>
          <div className="text-[10px] text-text-muted font-medium mb-1">TOTAL P&amp;L</div>
          <div
            className="stat-value font-bold"
            style={{
              fontSize: 18,
              color: pnlPos ? '#26de81' : '#ff5e7d',
              letterSpacing: '-0.02em',
            }}
          >
            {pnlPos ? '+' : ''}${pnlUsd.toFixed(2)}
          </div>
        </div>
        {winRate != null && (
          <div>
            <div className="text-[10px] text-text-muted font-medium mb-1">WIN RATE</div>
            <div
              className="stat-value font-bold"
              style={{
                fontSize: 18,
                color: winRate >= 0.5 ? '#26de81' : '#fbbf24',
                letterSpacing: '-0.02em',
              }}
            >
              {(winRate * 100).toFixed(0)}%
            </div>
          </div>
        )}
        {(wins > 0 || losses > 0) && (
          <div>
            <div className="text-[10px] text-text-muted font-medium mb-1">TRADES</div>
            <div className="stat-value font-bold" style={{ fontSize: 15, color: '#94a3b8' }}>
              <span style={{ color: '#26de81' }}>{wins}W</span>
              {' / '}
              <span style={{ color: '#ff5e7d' }}>{losses}L</span>
            </div>
          </div>
        )}
        {openRisk > 0 && (
          <div>
            <div className="text-[10px] text-text-muted font-medium mb-1">OPEN RISK</div>
            <div
              className="stat-value font-bold"
              style={{ fontSize: 15, color: '#fbbf24' }}
            >
              ${openRisk.toFixed(0)}
            </div>
          </div>
        )}
      </div>

      {/* Chart */}
      {!hasPnl ? (
        <div
          className="flex-1 flex items-center justify-center text-sm"
          style={{ color: '#475569' }}
        >
          No P&amp;L history yet
        </div>
      ) : (
        <div className="flex-1 min-h-0">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={pnl} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="pnlGradGreen" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#818cf8" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#818cf8" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="pnlGradRed" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#ff5e7d" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#ff5e7d" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 6" stroke="#2a2a3a" />
              <XAxis
                dataKey="timestamp"
                tickFormatter={v =>
                  new Date(v).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                }
                tick={{ fill: '#475569', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
                axisLine={{ stroke: '#2a2a3a' }}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                domain={[minV, maxV]}
                tick={{ fill: '#475569', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
                axisLine={{ stroke: '#2a2a3a' }}
                tickLine={false}
                tickFormatter={v => `$${v.toFixed(0)}`}
                width={52}
              />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine
                y={base}
                stroke="#3a3a4a"
                strokeDasharray="4 4"
                strokeWidth={1}
              />
              <Area
                type="monotone"
                dataKey="capital_usd"
                stroke={pnlPos ? '#818cf8' : '#ff5e7d'}
                strokeWidth={2}
                fill={pnlPos ? 'url(#pnlGradGreen)' : 'url(#pnlGradRed)'}
                dot={false}
                activeDot={{ r: 4, fill: '#818cf8', stroke: '#1a1a24', strokeWidth: 2 }}
                isAnimationActive={true}
                animationDuration={600}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
