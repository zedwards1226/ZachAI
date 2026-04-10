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
        fontSize: 11,
        boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
      }}
    >
      {d.timestamp && (
        <div style={{ color: '#475569', marginBottom: 4 }}>
          {new Date(d.timestamp).toLocaleString('en-US', {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
          })}
        </div>
      )}
      <div style={{ color: '#f8fafc', fontWeight: 600 }}>
        Capital: ${d.capital?.toFixed(2)}
      </div>
      <div style={{ color: d.pnl >= 0 ? '#26de81' : '#ff5e7d', marginTop: 2 }}>
        P&L: {d.pnl >= 0 ? '+' : ''}${d.pnl?.toFixed(2)}
      </div>
    </div>
  )
}

export default function EquityChart({ curve, startingCapital = 1000 }) {
  const data = curve ?? []
  const hasData = data.length > 1

  if (!hasData) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-text-muted">
        No settled trades yet
      </div>
    )
  }

  const vals = data.map(d => d.capital).filter(Boolean)
  const minV = Math.min(...vals, startingCapital) - 20
  const maxV = Math.max(...vals, startingCapital) + 20
  const latest = data[data.length - 1]
  const pnlPos = (latest?.pnl ?? 0) >= 0

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="eqGradGreen" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#26de81" stopOpacity={0.25} />
            <stop offset="95%" stopColor="#26de81" stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="eqGradRed" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#ff5e7d" stopOpacity={0.25} />
            <stop offset="95%" stopColor="#ff5e7d" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 6" stroke="#2a2a3a" />
        <XAxis
          dataKey="timestamp"
          tickFormatter={v => {
            if (!v) return ''
            return new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
          }}
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
          y={startingCapital}
          stroke="#3a3a4a"
          strokeDasharray="4 4"
          strokeWidth={1}
        />
        <Area
          type="monotone"
          dataKey="capital"
          stroke={pnlPos ? '#26de81' : '#ff5e7d'}
          strokeWidth={2}
          fill={pnlPos ? 'url(#eqGradGreen)' : 'url(#eqGradRed)'}
          dot={false}
          activeDot={{ r: 4, fill: pnlPos ? '#26de81' : '#ff5e7d', stroke: '#1a1a24', strokeWidth: 2 }}
          isAnimationActive={true}
          animationDuration={600}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
