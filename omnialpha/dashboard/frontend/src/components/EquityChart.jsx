import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine } from 'recharts'
import { TrendingUp } from 'lucide-react'

export default function EquityChart({ points, startingCapital = 100 }) {
  const data = (points || []).map((p) => ({
    ts: p.ts,
    label: new Date(p.ts).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }),
    capital: p.capital_usd,
    pnl: p.capital_usd - startingCapital,
  }))

  const latest = data.length > 0 ? data[data.length - 1].capital : startingCapital
  const change = latest - startingCapital
  const positive = change >= 0
  const fillColor = positive ? '#26de81' : '#ff5e7d'

  // y-axis padding
  let yMin = startingCapital, yMax = startingCapital
  if (data.length > 0) {
    yMin = Math.min(...data.map(d => d.capital), startingCapital)
    yMax = Math.max(...data.map(d => d.capital), startingCapital)
    const pad = Math.max((yMax - yMin) * 0.15, 1)
    yMin -= pad
    yMax += pad
  }

  return (
    <div className="rounded-xl gradient-card border overflow-hidden" style={{ borderColor: '#2a2a3a' }}>
      <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid #2a2a3a' }}>
        <div className="flex items-center gap-2">
          <TrendingUp size={14} style={{ color: '#818cf8' }} />
          <span className="text-[10px] font-bold tracking-[0.14em] uppercase" style={{ color: '#94a3b8' }}>
            Equity Curve
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="font-mono" style={{ color: '#94a3b8' }}>
            ${latest.toLocaleString('en-US', { maximumFractionDigits: 2, minimumFractionDigits: 2 })}
          </span>
          <span className="font-mono font-bold" style={{ color: fillColor }}>
            {positive ? '+' : ''}${change.toFixed(2)}
          </span>
        </div>
      </div>
      <div style={{ height: 200 }} className="px-2 py-2">
        {data.length < 2 ? (
          <div className="flex items-center justify-center h-full text-xs" style={{ color: '#64748b' }}>
            Building equity history… (snapshot every 60s)
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={fillColor} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={fillColor} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#64748b' }} stroke="#2a2a3a" minTickGap={50} />
              <YAxis
                domain={[yMin, yMax]}
                tick={{ fontSize: 10, fill: '#64748b' }}
                stroke="#2a2a3a"
                width={60}
                tickFormatter={(v) => `$${v.toFixed(0)}`}
              />
              <Tooltip
                contentStyle={{ background: '#0a0a10', border: '1px solid #2a2a3a', fontSize: 12 }}
                labelStyle={{ color: '#94a3b8' }}
                formatter={(v) => [`$${v.toFixed(2)}`, 'capital']}
              />
              <ReferenceLine
                y={startingCapital}
                stroke="#475569"
                strokeDasharray="3 3"
                label={{ value: 'start', fill: '#64748b', fontSize: 9, position: 'right' }}
              />
              <Area
                type="monotone"
                dataKey="capital"
                stroke={fillColor}
                strokeWidth={2}
                fill="url(#equityFill)"
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
