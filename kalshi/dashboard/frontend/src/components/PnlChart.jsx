import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine, CartesianGrid,
} from 'recharts'

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div style={{
      background: '#050505',
      border: '1px solid #00ff4155',
      borderRadius: 2,
      padding: '6px 10px',
      fontSize: 11,
      fontFamily: 'Share Tech Mono',
    }}>
      <div style={{ color: '#006622' }}>
        {new Date(d.timestamp).toLocaleTimeString()}
      </div>
      <div style={{ color: '#00ff41' }}>
        ${d.capital_usd?.toFixed(2)}
      </div>
      {d.open_risk > 0 && (
        <div style={{ color: '#ffcc00' }}>risk ${d.open_risk?.toFixed(2)}</div>
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

  // Domain: center around base
  const vals    = hasPnl ? pnl.map(p => p.capital_usd).filter(Boolean) : [base]
  const minV    = Math.min(...vals, base) - 20
  const maxV    = Math.max(...vals, base) + 20

  return (
    <div className="flex flex-col gap-2 h-full">
      {/* Stats row */}
      <div className="flex gap-4 text-xs px-1">
        <div>
          <div className="text-[#003311] text-[9px]">CAPITAL</div>
          <div className="font-bold" style={{ fontFamily: 'Orbitron', color: '#00ff41', fontSize: 13 }}>
            ${(latest ?? base).toFixed(2)}
          </div>
        </div>
        <div>
          <div className="text-[#003311] text-[9px]">P&L</div>
          <div className="font-bold" style={{
            fontFamily: 'Orbitron', fontSize: 13,
            color: pnlPos ? '#00ff41' : '#ff0040',
            textShadow: pnlPos ? '0 0 8px #00ff41' : '0 0 8px #ff0040',
          }}>
            {pnlPos ? '+' : ''}{pnlUsd.toFixed(2)}
          </div>
        </div>
        {summary && (
          <>
            <div>
              <div className="text-[#003311] text-[9px]">WINS</div>
              <div style={{ color: '#00ff41', fontSize: 12 }}>{summary.wins}</div>
            </div>
            <div>
              <div className="text-[#003311] text-[9px]">LOSSES</div>
              <div style={{ color: '#ff0040', fontSize: 12 }}>{summary.losses}</div>
            </div>
            <div>
              <div className="text-[#003311] text-[9px]">WIN%</div>
              <div style={{ color: summary.win_rate >= 0.5 ? '#00ff41' : '#ffcc00', fontSize: 12 }}>
                {(summary.win_rate * 100).toFixed(0)}%
              </div>
            </div>
            <div>
              <div className="text-[#003311] text-[9px]">RISK</div>
              <div style={{ color: '#ffcc00', fontSize: 12 }}>
                ${summary.open_risk_usd?.toFixed(0)}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Chart */}
      {!hasPnl ? (
        <div className="flex-1 flex items-center justify-center text-[#002211] text-xs">
          — no P&L history —
        </div>
      ) : (
        <div className="flex-1 min-h-0">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={pnl} margin={{ top: 4, right: 6, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#00ff41" stopOpacity={pnlPos ? 0.35 : 0.05} />
                  <stop offset="95%" stopColor="#00ff41" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="pnlGradRed" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#ff0040" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#ff0040" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="2 4" stroke="#001a08" />
              <XAxis
                dataKey="timestamp"
                tickFormatter={v => new Date(v).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}
                tick={{ fill: '#004d18', fontSize: 9 }}
                axisLine={{ stroke: '#002211' }}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                domain={[minV, maxV]}
                tick={{ fill: '#004d18', fontSize: 9 }}
                axisLine={{ stroke: '#002211' }}
                tickLine={false}
                tickFormatter={v => `$${v.toFixed(0)}`}
                width={48}
              />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine y={base} stroke="#003311" strokeDasharray="4 3" strokeWidth={1} />
              <Area
                type="monotone"
                dataKey="capital_usd"
                stroke={pnlPos ? '#00ff41' : '#ff0040'}
                strokeWidth={1.5}
                fill={pnlPos ? 'url(#pnlGrad)' : 'url(#pnlGradRed)'}
                dot={false}
                activeDot={{ r: 3, fill: '#00ff41', stroke: 'none' }}
                isAnimationActive={true}
                animationDuration={800}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
