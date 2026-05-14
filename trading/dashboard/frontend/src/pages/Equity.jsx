import { useApi, api, fmt } from '../api.js'
import {
  ResponsiveContainer, ComposedChart, Bar, Line, XAxis, YAxis,
  Tooltip, CartesianGrid, ReferenceLine,
} from 'recharts'

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="bg-bg-panel border border-border rounded-md px-3 py-2 shadow-lg text-xs">
      <div className="font-semibold text-text-primary mb-1">{label}</div>
      <div className="text-text-secondary">Trades: <span className="font-mono">{p.trades}</span> ({p.wins}W / {p.losses}L)</div>
      <div className={p.daily_pnl >= 0 ? 'text-profit' : 'text-loss'}>
        Daily: <span className="font-mono">{fmt.usd(p.daily_pnl)}</span>
      </div>
      <div className={p.cumulative_pnl >= 0 ? 'text-profit' : 'text-loss'}>
        Cumulative: <span className="font-mono">{fmt.usd(p.cumulative_pnl)}</span>
      </div>
    </div>
  )
}

export default function Equity() {
  const { data, error } = useApi(api.equity, [])

  if (error) return <div className="text-loss text-sm mt-4">Error: {error}</div>
  if (!data) return <div className="text-text-muted text-sm mt-4">Loading…</div>

  const points = data.points || []
  const totalTrades = points.reduce((s, p) => s + p.trades, 0)
  const totalWins = points.reduce((s, p) => s + p.wins, 0)
  const totalPnl = points.length ? points[points.length - 1].cumulative_pnl : 0
  const best = points.reduce((m, p) => p.daily_pnl > m ? p.daily_pnl : m, -Infinity)
  const worst = points.reduce((m, p) => p.daily_pnl < m ? p.daily_pnl : m, Infinity)

  return (
    <div className="mt-4 space-y-4">
      <section className="gradient-card border border-border rounded-lg p-4">
        <h2 className="text-lg font-semibold mb-1">Equity Curve — last 30 days</h2>
        <p className="text-xs text-text-muted mb-3">
          Bars = daily P&L · Line = cumulative
        </p>
        {points.length === 0 ? (
          <div className="text-text-muted text-sm py-8 text-center">No trades in last 30 days.</div>
        ) : (
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer>
              <ComposedChart data={points} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2a3f" />
                <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 11 }} stroke="#1f2a3f"
                  tickFormatter={(s) => s.slice(5)} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} stroke="#1f2a3f"
                  tickFormatter={(v) => `$${v}`} />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: '#1f2a3f55' }} />
                <ReferenceLine y={0} stroke="#475569" />
                <Bar dataKey="daily_pnl">
                  {points.map((p, i) => (
                    <rect key={i} fill={p.daily_pnl >= 0 ? '#26de8155' : '#ff5e7d55'} />
                  ))}
                </Bar>
                <Line type="monotone" dataKey="cumulative_pnl" stroke="#60a5fa" strokeWidth={2.5} dot={{ r: 3, fill: '#60a5fa' }} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      <section className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="gradient-card border border-border rounded-lg p-3">
          <div className="text-xs uppercase text-text-muted">Total P&L (30d)</div>
          <div className={`text-xl font-bold mt-1 ${totalPnl >= 0 ? 'text-profit' : 'text-loss'}`}>
            {fmt.usd(totalPnl)}
          </div>
        </div>
        <div className="gradient-card border border-border rounded-lg p-3">
          <div className="text-xs uppercase text-text-muted">Total Trades</div>
          <div className="text-xl font-bold mt-1 text-text-primary">
            {totalTrades}
          </div>
          <div className="text-xs text-text-muted mt-0.5">
            {totalTrades > 0 ? `${(totalWins / totalTrades * 100).toFixed(0)}% WR` : '—'}
          </div>
        </div>
        <div className="gradient-card border border-border rounded-lg p-3">
          <div className="text-xs uppercase text-text-muted">Best Day</div>
          <div className="text-xl font-bold mt-1 text-profit">
            {points.length ? fmt.usd(best) : '—'}
          </div>
        </div>
        <div className="gradient-card border border-border rounded-lg p-3">
          <div className="text-xs uppercase text-text-muted">Worst Day</div>
          <div className="text-xl font-bold mt-1 text-loss">
            {points.length && worst !== Infinity ? fmt.usd(worst) : '—'}
          </div>
        </div>
      </section>
    </div>
  )
}
