import { MapPin } from 'lucide-react'

const CITY_FLAGS = {
  NYC: '🗽', CHI: '🌆', MIA: '🌴', LAX: '🌅', DEN: '🏔', MEM: '🎸',
}

export default function CityBoard({ cities = [] }) {
  if (!cities.length) {
    return (
      <div className="flex items-center justify-center h-full text-[11px] text-text-muted">
        No city data yet.
      </div>
    )
  }

  const maxAbs = Math.max(1, ...cities.map(c => Math.abs(c.pnl_usd)))

  return (
    <div className="flex flex-col gap-1.5">
      {cities.map(c => {
        const pos = c.pnl_usd >= 0
        const barPct = Math.min(100, (Math.abs(c.pnl_usd) / maxAbs) * 100)
        const wr = c.wins + c.losses > 0 ? (c.wins / (c.wins + c.losses)) * 100 : null
        return (
          <div
            key={c.city}
            className="relative flex items-center gap-2 px-2.5 py-1.5 rounded-md"
            style={{
              background: '#161620',
              border: `1px solid ${pos ? 'rgba(38,222,129,0.18)' : 'rgba(255,94,125,0.18)'}`,
            }}
          >
            <span style={{ fontSize: 14 }}>{CITY_FLAGS[c.city] ?? '📍'}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="stat-value text-[11px] font-bold" style={{ color: '#f8fafc' }}>
                  {c.city}
                </span>
                <span className="text-[9px] text-text-muted">
                  {c.wins}W / {c.losses}L
                  {c.open ? ` · ${c.open} open` : ''}
                </span>
                {wr != null && (
                  <span
                    className="text-[9px] font-semibold ml-auto"
                    style={{ color: wr >= 50 ? '#26de81' : '#fbbf24' }}
                  >
                    {wr.toFixed(0)}%
                  </span>
                )}
                <span
                  className="stat-value text-[11px] font-bold"
                  style={{ color: pos ? '#26de81' : '#ff5e7d', minWidth: '60px', textAlign: 'right' }}
                >
                  {pos ? '+' : '−'}${Math.abs(c.pnl_usd).toFixed(2)}
                </span>
              </div>
              <div
                className="mt-1 h-1 rounded-full overflow-hidden"
                style={{ background: '#2a2a3a' }}
              >
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${barPct}%`,
                    background: pos ? '#26de81' : '#ff5e7d',
                    boxShadow: `0 0 6px ${pos ? '#26de81' : '#ff5e7d'}60`,
                  }}
                />
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
