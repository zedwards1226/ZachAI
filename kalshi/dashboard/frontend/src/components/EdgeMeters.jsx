const CITIES = ['NYC','CHI','MIA','LAX','MEM','DEN']
const MIN_EDGE = 0.08  // 8%

export default function EdgeMeters({ forecasts, activeCity }) {
  const fcMap = {}
  forecasts.forEach(f => { fcMap[f.city] = f })

  return (
    <div className="space-y-1.5">
      {CITIES.map(code => {
        const fc      = fcMap[code]
        const edge    = fc?.edge ?? null
        const absEdge = edge != null ? Math.abs(edge) : null
        const side    = edge != null ? (edge >= 0 ? 'YES' : 'NO') : null
        const hasEdge = absEdge != null && absEdge >= MIN_EDGE
        const isActive = code === activeCity

        // Bar width: 0–25% edge maps to 0–100% bar
        const pct = absEdge != null ? Math.min(100, (absEdge / 0.25) * 100) : 0

        const barColor = !fc ? '#002211'
          : hasEdge      ? '#00ff41'
          : absEdge > 0.04 ? '#ffcc00'
          : '#ff0040'

        const textColor = !fc ? '#003311'
          : hasEdge      ? '#00ff41'
          : absEdge > 0.04 ? '#ffcc00'
          : '#ff0040'

        return (
          <div key={code}
               className={`px-2 py-1.5 rounded border transition-all duration-300 ${
                 isActive
                   ? 'border-[#00ff41] bg-[#010d03]'
                   : 'border-[#001a08] bg-[#050505]'
               }`}>
            {/* Header row */}
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                <span className={`text-xs font-bold ${isActive ? 'neon-text' : 'text-[#006622]'}`}
                      style={{ fontFamily: 'Orbitron' }}>
                  {code}
                </span>
                {fc?.forecast_hi_f && (
                  <span className="text-[10px] text-[#004d18]">
                    {fc.forecast_hi_f.toFixed(1)}°F hi
                  </span>
                )}
                {fc?.kalshi_strike_f && (
                  <span className="text-[10px] text-[#003311]">
                    strike {fc.kalshi_strike_f}°F
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1.5">
                {side && (
                  <span className={`text-[10px] border rounded px-1 ${
                    side === 'YES' ? 'border-[#003311] text-[#006622]' : 'border-[#4d1a00] text-[#cc5500]'
                  }`}>{side}</span>
                )}
                <span className={`text-xs font-bold`} style={{ color: textColor }}>
                  {absEdge != null
                    ? `${edge >= 0 ? '+' : '−'}${(absEdge * 100).toFixed(1)}%`
                    : '—'}
                </span>
              </div>
            </div>

            {/* Bar track */}
            <div className="w-full h-1 bg-[#010d03] rounded overflow-hidden">
              <div
                className="h-full rounded transition-all duration-700 ease-out"
                style={{
                  width: `${pct}%`,
                  backgroundColor: barColor,
                  boxShadow: hasEdge ? `0 0 6px ${barColor}` : 'none',
                }}
              />
            </div>

            {/* Threshold marker */}
            <div className="relative h-0">
              <div className="absolute top-0 w-px h-1.5 bg-[#003311]"
                   style={{ left: `${(MIN_EDGE / 0.25) * 100}%`, marginTop: '-2px' }} />
            </div>

            {/* Sub-label */}
            {fc && (
              <div className="flex justify-between text-[9px] text-[#002211] mt-1">
                <span>
                  {fc.kalshi_yes_price != null
                    ? `mkt ${fc.kalshi_yes_price}¢`
                    : 'no market'}
                </span>
                <span>
                  {fc.our_prob_yes != null
                    ? `model ${(fc.our_prob_yes * 100).toFixed(1)}%`
                    : ''}
                </span>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
