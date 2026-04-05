const CITY_NAMES = {
  NYC: 'New York',
  CHI: 'Chicago',
  MIA: 'Miami',
  LAX: 'Los Angeles',
  MEM: 'Memphis',
  DEN: 'Denver',
}

function EdgeBadge({ edge }) {
  if (edge == null) return null
  const abs = Math.abs(edge * 100).toFixed(1)
  const color = Math.abs(edge) >= 0.08
    ? 'text-[#00ff41] border-[#00ff41]'
    : 'text-[#006622] border-[#003311]'
  const side = edge >= 0 ? 'YES' : 'NO'
  return (
    <span className={`text-[10px] border rounded px-1.5 py-0.5 ${color}`}>
      {side} +{abs}%
    </span>
  )
}

export default function ForecastsPanel({ forecasts }) {
  return (
    <div className="neon-card rounded bg-[#080808] p-4 min-h-[260px]">
      <h2 className="text-xs font-bold tracking-widest mb-3 neon-text flex items-center gap-2">
        <span>▶</span> CITY FORECASTS
        <span className="ml-auto text-[10px] text-[#003311]">Open-Meteo</span>
      </h2>

      {forecasts.length === 0 ? (
        <p className="text-[#004d18] text-xs mt-8 text-center">— no forecasts yet — trigger a scan —</p>
      ) : (
        <div className="space-y-2">
          {forecasts.map(f => (
            <div key={f.city} className="border border-[#002211] rounded p-2 bg-[#040d06]">
              <div className="flex items-center justify-between mb-1">
                <div>
                  <span className="text-xs text-[#00ff41] font-bold">{f.city}</span>
                  <span className="text-[10px] text-[#004d18] ml-2">{CITY_NAMES[f.city]}</span>
                </div>
                <EdgeBadge edge={f.edge} />
              </div>

              <div className="flex gap-4 text-xs">
                <span className="text-[#006622]">
                  Hi: <span className="text-[#00cc33]">{f.forecast_hi_f?.toFixed(1)}°F</span>
                </span>
                <span className="text-[#006622]">
                  Lo: <span className="text-[#00cc33]">{f.forecast_lo_f?.toFixed(1)}°F</span>
                </span>
                {f.kalshi_strike_f && (
                  <span className="text-[#006622]">
                    Strike: <span className="text-[#00aa33]">{f.kalshi_strike_f}°F</span>
                  </span>
                )}
              </div>

              {f.our_prob_yes != null && f.kalshi_yes_price != null && (
                <div className="flex gap-4 text-[10px] text-[#004d18] mt-1">
                  <span>Our: {(f.our_prob_yes * 100).toFixed(1)}%</span>
                  <span>Mkt: {f.kalshi_yes_price?.toFixed(0)}¢</span>
                  {f.kalshi_market_id && (
                    <span className="truncate text-[#002211]">{f.kalshi_market_id}</span>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
