import { TrendingUp, TrendingDown, Target, Activity } from 'lucide-react'

function Tile({ label, value, sub, color, icon: Icon, big }) {
  return (
    <div
      className="flex items-start gap-3 px-5 py-4 rounded-xl gradient-card border animate-fade-in-up"
      style={{ borderColor: color ? `${color}55` : '#2a2a3a' }}
    >
      {Icon && (
        <div
          className="rounded-lg p-2 mt-1"
          style={{ background: `${color || '#818cf8'}15` }}
        >
          <Icon size={16} style={{ color: color || '#818cf8' }} />
        </div>
      )}
      <div className="flex-1 min-w-0">
        <div
          className="text-[10px] font-bold tracking-[0.14em] uppercase"
          style={{ color: '#64748b' }}
        >
          {label}
        </div>
        <div
          className="font-mono font-bold leading-tight mt-1"
          style={{
            fontSize: big ? 26 : 20,
            color: color ?? '#f8fafc',
            letterSpacing: '-0.01em',
            fontFamily: '"JetBrains Mono", monospace',
          }}
        >
          {value}
        </div>
        {sub && (
          <div className="text-xs mt-1" style={{ color: '#94a3b8' }}>
            {sub}
          </div>
        )}
      </div>
    </div>
  )
}

export default function HeroTiles({ summary }) {
  const cap = summary?.capital_usd ?? 100
  const today = summary?.today_pnl_usd ?? 0
  const todayPct = summary?.starting_capital_usd ? (today / summary.starting_capital_usd) * 100 : 0
  const todayColor = today > 0 ? '#26de81' : today < 0 ? '#ff5e7d' : '#94a3b8'
  const wr = summary?.win_rate_pct ?? null
  const closed = (summary?.wins ?? 0) + (summary?.losses ?? 0)
  const open = summary?.open_positions ?? 0

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <Tile
        label="Bankroll"
        value={`$${cap.toLocaleString('en-US', { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`}
        sub={summary ? null : '—'}
        icon={Target}
        color="#818cf8"
        big
      />
      <Tile
        label="Today P&L"
        value={`${today >= 0 ? '+' : ''}$${today.toFixed(2)}`}
        sub={summary ? `${todayPct >= 0 ? '+' : ''}${todayPct.toFixed(2)}%` : '—'}
        icon={today >= 0 ? TrendingUp : TrendingDown}
        color={todayColor}
      />
      <Tile
        label="Win Rate"
        value={wr === null || closed === 0 ? '—' : `${wr.toFixed(1)}%`}
        sub={closed > 0 ? `${summary?.wins}W / ${summary?.losses}L` : 'no closed trades'}
        icon={Activity}
        color="#fbbf24"
      />
      <Tile
        label="Open"
        value={`${open}`}
        sub={open === 0 ? 'no positions' : 'positions'}
        icon={Target}
        color="#38bdf8"
      />
    </div>
  )
}
