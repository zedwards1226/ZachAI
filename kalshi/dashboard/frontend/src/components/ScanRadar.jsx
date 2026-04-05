import { useMemo } from 'react'

// Geographic-ish positions on 300×300 radar
const CITY_POS = {
  NYC: { x: 228, y:  88 },
  CHI: { x: 138, y:  78 },
  MIA: { x: 220, y: 202 },
  LAX: { x:  60, y: 155 },
  MEM: { x: 172, y: 188 },
  DEN: { x:  94, y: 140 },
}

const SECTOR = 'M 150 150 L 150 15 A 135 135 0 0 1 227 57 Z'

export default function ScanRadar({ forecasts, activeCity, scanning }) {
  const fcMap = useMemo(() => {
    const m = {}
    forecasts.forEach(f => { m[f.city] = f })
    return m
  }, [forecasts])

  return (
    <div className="relative w-full aspect-square max-w-[260px] mx-auto select-none">
      <svg viewBox="0 0 300 300" className="w-full h-full">
        <defs>
          <radialGradient id="sweepGradNew" cx="150" cy="150" r="135"
            fx="150" fy="150" gradientUnits="userSpaceOnUse">
            <stop offset="0%"   stopColor="#818cf8" stopOpacity="0.5" />
            <stop offset="80%"  stopColor="#818cf8" stopOpacity="0.06" />
            <stop offset="100%" stopColor="#818cf8" stopOpacity="0" />
          </radialGradient>

          <radialGradient id="bgGradNew" cx="50%" cy="50%" r="50%">
            <stop offset="0%"   stopColor="#141420" />
            <stop offset="100%" stopColor="#0f0f14" />
          </radialGradient>

          <clipPath id="radarClipNew">
            <circle cx="150" cy="150" r="136" />
          </clipPath>

          <filter id="glowNew">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <filter id="strongGlowNew">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* Background */}
        <circle cx="150" cy="150" r="140" fill="url(#bgGradNew)" />

        <g clipPath="url(#radarClipNew)">
          {/* Grid lines */}
          <line x1="15"  y1="150" x2="285" y2="150" stroke="#2a2a3a" strokeWidth="0.5" />
          <line x1="150" y1="15"  x2="150" y2="285" stroke="#2a2a3a" strokeWidth="0.5" />
          <line x1="54"  y1="54"  x2="246" y2="246" stroke="#1e1e2e" strokeWidth="0.5" />
          <line x1="246" y1="54"  x2="54"  y2="246" stroke="#1e1e2e" strokeWidth="0.5" />

          {/* Rings */}
          {[35, 68, 101, 134].map(r => (
            <circle key={r} cx="150" cy="150" r={r}
              fill="none" stroke="#2a2a3a" strokeWidth="0.75" />
          ))}

          {/* Sweep blade */}
          <g className="radar-blade">
            <path d={SECTOR} fill="url(#sweepGradNew)" />
            <line x1="150" y1="150" x2="150" y2="14"
              stroke="#818cf8" strokeWidth="1.5" opacity="0.8"
              filter="url(#glowNew)" />
          </g>

          {/* City dots */}
          {Object.entries(CITY_POS).map(([code, pos]) => {
            const isActive = code === activeCity
            const fc       = fcMap[code]
            const hasEdge  = fc?.edge != null && Math.abs(fc.edge) >= 0.08
            const dotColor = hasEdge ? '#26de81' : isActive ? '#818cf8' : '#3a3a4a'
            const r        = isActive ? 5.5 : 4

            return (
              <g key={code} filter={isActive ? 'url(#strongGlowNew)' : undefined}>
                {isActive && (
                  <circle cx={pos.x} cy={pos.y} r={5}
                    fill="none" stroke="#818cf8" strokeWidth="1"
                    className="city-ping" />
                )}
                <circle cx={pos.x} cy={pos.y} r={r} fill={dotColor} />
                <text
                  x={pos.x + 7}
                  y={pos.y + 4}
                  fill={isActive ? '#f8fafc' : '#475569'}
                  fontSize={isActive ? 9 : 8}
                  fontFamily="Inter, sans-serif"
                  fontWeight={isActive ? '600' : '400'}
                >
                  {code}
                </text>
                {fc?.forecast_hi_f && isActive && (
                  <text
                    x={pos.x + 7}
                    y={pos.y + 14}
                    fill="#818cf8"
                    fontSize="7"
                    fontFamily="JetBrains Mono, monospace"
                  >
                    {fc.forecast_hi_f.toFixed(0)}°F
                  </text>
                )}
              </g>
            )
          })}
        </g>

        {/* Outer ring */}
        <circle cx="150" cy="150" r="136"
          fill="none" stroke="#818cf8" strokeWidth="1" opacity="0.4"
          filter="url(#glowNew)" />

        {/* Center */}
        <circle cx="150" cy="150" r="3" fill="#818cf8" filter="url(#glowNew)" />

        {/* Compass labels */}
        <text x="8"   y="18"  fill="#2a2a3a" fontSize="7" fontFamily="Inter, sans-serif">N</text>
        <text x="8"   y="290" fill="#2a2a3a" fontSize="7" fontFamily="Inter, sans-serif">S</text>
        <text x="278" y="155" fill="#2a2a3a" fontSize="7" fontFamily="Inter, sans-serif">E</text>
        <text x="12"  y="155" fill="#2a2a3a" fontSize="7" fontFamily="Inter, sans-serif">W</text>

        {scanning && (
          <text x="150" y="294" textAnchor="middle"
            fill="#818cf8" fontSize="7" fontFamily="Inter, sans-serif"
            className="animate-pulse-glow">
            SCANNING
          </text>
        )}
      </svg>
    </div>
  )
}
