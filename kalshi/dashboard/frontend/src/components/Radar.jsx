import { useMemo } from 'react'

// Geographic-ish positions on 300x300 radar centered at 150,150
const CITY_POS = {
  NYC: { x: 228, y: 88,  label: 'NYC', full: 'New York'    },
  CHI: { x: 138, y: 78,  label: 'CHI', full: 'Chicago'     },
  MIA: { x: 220, y: 202, label: 'MIA', full: 'Miami'       },
  LAX: { x: 60,  y: 155, label: 'LAX', full: 'Los Angeles' },
  MEM: { x: 172, y: 188, label: 'MEM', full: 'Memphis'     },
  DEN: { x: 94,  y: 140, label: 'DEN', full: 'Denver'      },
}

// Sweep sector path: 35° wedge pointing up from center
const SECTOR = 'M 150 150 L 150 15 A 135 135 0 0 1 227 57 Z'

export default function Radar({ forecasts, activeCity, scanning }) {
  const fcMap = useMemo(() => {
    const m = {}
    forecasts.forEach(f => { m[f.city] = f })
    return m
  }, [forecasts])

  return (
    <div className="relative w-full aspect-square max-w-[280px] mx-auto select-none">
      <svg viewBox="0 0 300 300" className="w-full h-full">
        <defs>
          {/* Radar sweep fill — radial from center */}
          <radialGradient id="sweepGrad" cx="150" cy="150" r="135"
                          fx="150" fy="150" gradientUnits="userSpaceOnUse">
            <stop offset="0%"   stopColor="#00ff41" stopOpacity="0.55" />
            <stop offset="85%"  stopColor="#00ff41" stopOpacity="0.08" />
            <stop offset="100%" stopColor="#00ff41" stopOpacity="0"    />
          </radialGradient>

          {/* Outer ring fade */}
          <radialGradient id="bgGrad" cx="50%" cy="50%" r="50%">
            <stop offset="0%"   stopColor="#010d03" />
            <stop offset="100%" stopColor="#020906" />
          </radialGradient>

          {/* Clip to circle */}
          <clipPath id="radarClip">
            <circle cx="150" cy="150" r="136" />
          </clipPath>

          {/* Glow filter */}
          <filter id="glow">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <filter id="strongGlow">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* Background */}
        <circle cx="150" cy="150" r="140" fill="url(#bgGrad)" />

        {/* Clip group */}
        <g clipPath="url(#radarClip)">
          {/* Grid lines (diagonal) */}
          <line x1="15" y1="150" x2="285" y2="150" stroke="#001a08" strokeWidth="0.5" />
          <line x1="150" y1="15" x2="150" y2="285" stroke="#001a08" strokeWidth="0.5" />
          <line x1="54"  y1="54"  x2="246" y2="246" stroke="#000f04" strokeWidth="0.5" />
          <line x1="246" y1="54"  x2="54"  y2="246" stroke="#000f04" strokeWidth="0.5" />

          {/* Rings */}
          {[35, 68, 101, 134].map(r => (
            <circle key={r} cx="150" cy="150" r={r}
                    fill="none" stroke="#001a08" strokeWidth="0.75" />
          ))}

          {/* Range labels */}
          {['25mi','50mi','75mi'].map((lbl, i) => (
            <text key={lbl} x="152" y={150 - [35,68,101][i] + 4}
                  fill="#003311" fontSize="6" fontFamily="Share Tech Mono">{lbl}</text>
          ))}

          {/* Sweep blade — rotates via CSS */}
          <g className="radar-blade">
            <path d={SECTOR} fill="url(#sweepGrad)" />
            {/* Leading edge line */}
            <line x1="150" y1="150" x2="150" y2="14"
                  stroke="#00ff41" strokeWidth="1.5" opacity="0.9"
                  filter="url(#glow)" />
          </g>

          {/* City dots */}
          {Object.entries(CITY_POS).map(([code, pos]) => {
            const isActive  = code === activeCity
            const fc        = fcMap[code]
            const hasEdge   = fc?.edge != null && Math.abs(fc.edge) >= 0.08
            const dotColor  = hasEdge ? '#00ff41' : isActive ? '#00cc33' : '#004d18'
            const r         = isActive ? 5.5 : 4

            return (
              <g key={code} filter={isActive ? 'url(#strongGlow)' : undefined}>
                {/* Ping ring for active city */}
                {isActive && (
                  <circle cx={pos.x} cy={pos.y} r={5}
                          fill="none" stroke="#00ff41" strokeWidth="1"
                          className="city-ping" />
                )}
                {/* Main dot */}
                <circle cx={pos.x} cy={pos.y} r={r} fill={dotColor} />
                {/* Label */}
                <text x={pos.x + 7} y={pos.y + 4}
                      fill={isActive ? '#00ff41' : '#003d14'}
                      fontSize={isActive ? 9 : 8}
                      fontFamily="Share Tech Mono"
                      fontWeight={isActive ? 'bold' : 'normal'}>
                  {code}
                </text>
                {/* Temp if available */}
                {fc?.forecast_hi_f && isActive && (
                  <text x={pos.x + 7} y={pos.y + 13}
                        fill="#006622" fontSize="7" fontFamily="Share Tech Mono">
                    {fc.forecast_hi_f.toFixed(0)}°F
                  </text>
                )}
              </g>
            )
          })}
        </g>

        {/* Outer ring border */}
        <circle cx="150" cy="150" r="136" fill="none"
                stroke="#00ff41" strokeWidth="1.5" opacity="0.6"
                filter="url(#glow)" />

        {/* Center cross */}
        <circle cx="150" cy="150" r="3" fill="#00ff41" filter="url(#glow)" />
        <line x1="146" y1="150" x2="154" y2="150" stroke="#00ff41" strokeWidth="0.5" />
        <line x1="150" y1="146" x2="150" y2="154" stroke="#00ff41" strokeWidth="0.5" />

        {/* Corner labels */}
        <text x="8"   y="18"  fill="#003311" fontSize="7" fontFamily="Orbitron">N</text>
        <text x="8"   y="290" fill="#003311" fontSize="7" fontFamily="Orbitron">S</text>
        <text x="278" y="155" fill="#003311" fontSize="7" fontFamily="Orbitron">E</text>
        <text x="12"  y="155" fill="#003311" fontSize="7" fontFamily="Orbitron">W</text>

        {/* Scanning indicator */}
        {scanning && (
          <text x="150" y="296" textAnchor="middle"
                fill="#00ff41" fontSize="7" fontFamily="Share Tech Mono"
                className="blink">
            ● SCANNING
          </text>
        )}
      </svg>
    </div>
  )
}
