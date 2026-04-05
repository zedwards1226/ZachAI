import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="bg-[#050505] border border-[#003311] rounded p-2 text-xs">
      <p className="text-[#006622]">{new Date(d.timestamp).toLocaleString()}</p>
      <p className="text-[#00ff41]">Capital: ${d.capital_usd?.toFixed(2)}</p>
      {d.open_risk > 0 && (
        <p className="text-yellow-400">At Risk: ${d.open_risk?.toFixed(2)}</p>
      )}
    </div>
  )
}

export default function PnlChart({ pnl, summary }) {
  const hasPnl = pnl && pnl.length > 1

  return (
    <div className="neon-card rounded bg-[#080808] p-4 min-h-[260px]">
      <h2 className="text-xs font-bold tracking-widest mb-3 neon-text flex items-center gap-2">
        <span>▶</span> P&L CURVE
        {summary && (
          <span className="ml-auto text-xs">
            <span className="text-[#006622]">W/L: </span>
            <span className="text-[#00ff41]">{summary.wins}</span>
            <span className="text-[#006622]">/</span>
            <span className="text-red-400">{summary.losses}</span>
            <span className="text-[#006622] ml-3">Win%: </span>
            <span className="text-[#00ff41]">{(summary.win_rate * 100).toFixed(0)}%</span>
          </span>
        )}
      </h2>

      {!hasPnl ? (
        <p className="text-[#004d18] text-xs mt-10 text-center">
          — no P&L history yet —
        </p>
      ) : (
        <ResponsiveContainer width="100%" height={180}>
          <AreaChart data={pnl} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <defs>
              <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#00ff41" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#00ff41" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="timestamp"
              tickFormatter={v => new Date(v).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}
              tick={{ fill: '#006622', fontSize: 10 }}
              axisLine={{ stroke: '#003311' }}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fill: '#006622', fontSize: 10 }}
              axisLine={{ stroke: '#003311' }}
              tickLine={false}
              tickFormatter={v => `$${v}`}
              width={55}
            />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine y={1000} stroke="#003311" strokeDasharray="4 4" />
            <Area
              type="monotone"
              dataKey="capital_usd"
              stroke="#00ff41"
              strokeWidth={1.5}
              fill="url(#pnlGrad)"
              dot={false}
              activeDot={{ r: 3, fill: '#00ff41' }}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}

      {summary && (
        <div className="flex gap-4 text-[10px] text-[#006622] mt-2 border-t border-[#001a08] pt-2">
          <span>Total P&L: <span className={summary.total_pnl_usd >= 0 ? 'text-[#00ff41]' : 'text-red-400'}>
            ${summary.total_pnl_usd?.toFixed(2)}
          </span></span>
          <span>Open risk: <span className="text-yellow-400">${summary.open_risk_usd?.toFixed(2)}</span></span>
          <span>Trades: <span className="text-[#00cc33]">{summary.total_trades}</span></span>
        </div>
      )}
    </div>
  )
}
