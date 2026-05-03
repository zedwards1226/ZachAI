import { LineChart, Line, ResponsiveContainer, YAxis } from 'recharts'
import { Layers } from 'lucide-react'
import LiveScan from './LiveScan'

const SECTOR_COLOR = {
  crypto: '#fbbf24',
  sports: '#38bdf8',
  politics: '#ff5e7d',
  economics: '#26de81',
  weather: '#818cf8',
  other: '#94a3b8',
}

function MicroCurve({ values, positive }) {
  if (!values || values.length < 2) {
    return (
      <div className="text-[10px] text-center pt-2" style={{ color: '#64748b' }}>
        no closed trades yet
      </div>
    )
  }
  const data = values.map((v, i) => ({ i, v }))
  const color = positive ? '#26de81' : '#ff5e7d'
  return (
    <ResponsiveContainer width="100%" height={48}>
      <LineChart data={data} margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
        <YAxis hide domain={['auto', 'auto']} />
        <Line
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

function StrategyCard({ s }) {
  const positive = (s.pnl_usd ?? 0) >= 0
  const pnlColor = positive ? '#26de81' : '#ff5e7d'
  const sectorColor = SECTOR_COLOR[s.sector] || '#94a3b8'

  return (
    <div className="rounded-xl gradient-card border p-3 flex flex-col" style={{ borderColor: '#2a2a3a' }}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: sectorColor }} />
            <span
              className="text-[10px] uppercase tracking-wider truncate"
              style={{ color: '#94a3b8' }}
            >
              {s.sector}
            </span>
          </div>
          <div
            className="font-mono text-xs mt-0.5 truncate"
            style={{ color: '#f8fafc', fontFamily: '"JetBrains Mono", monospace' }}
            title={s.strategy}
          >
            {s.strategy}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="font-mono font-bold text-sm" style={{ color: pnlColor }}>
            {positive ? '+' : ''}${(s.pnl_usd ?? 0).toFixed(2)}
          </div>
          <div className="text-[10px]" style={{ color: '#64748b' }}>
            {s.wins ?? 0}W/{s.losses ?? 0}L
            {(s.win_rate_pct !== null && s.win_rate_pct !== undefined) ? ` · ${s.win_rate_pct.toFixed(0)}%` : ''}
          </div>
        </div>
      </div>
      <div className="mt-1">
        <MicroCurve values={s.curve} positive={positive} />
      </div>
      <div className="flex items-center justify-between text-[10px] mt-1" style={{ color: '#64748b' }}>
        <span>open {s.open ?? 0}</span>
        <span>n={s.n ?? 0}</span>
      </div>
    </div>
  )
}

export default function StrategyCards({ strategies, liveScan }) {
  return (
    <div className="rounded-xl gradient-card border overflow-hidden" style={{ borderColor: '#2a2a3a' }}>
      <div className="flex items-center gap-2 px-4 py-3" style={{ borderBottom: '1px solid #2a2a3a' }}>
        <Layers size={14} style={{ color: '#818cf8' }} />
        <span className="text-[10px] font-bold tracking-[0.14em] uppercase" style={{ color: '#94a3b8' }}>
          Strategies
        </span>
        <span className="text-[10px] ml-auto" style={{ color: '#64748b' }}>
          {strategies.length}
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 p-3">
        {/* Live-scan tile slots into the strategies grid as the first cell so
            the empty spot becomes a useful "what's the bot doing right now"
            view instead of dead air. */}
        {liveScan !== undefined && <LiveScan scan={liveScan} />}
        {strategies.map((s) => (
          <StrategyCard key={s.strategy} s={s} />
        ))}
        {strategies.length === 0 && liveScan === undefined && (
          <div className="px-4 py-6 text-xs text-center col-span-full" style={{ color: '#64748b' }}>
            No strategies running yet.
          </div>
        )}
      </div>
    </div>
  )
}
