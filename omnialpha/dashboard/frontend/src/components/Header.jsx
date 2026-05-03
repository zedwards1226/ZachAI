import { useEffect, useState } from 'react'
import { Zap, Wifi, WifiOff } from 'lucide-react'

export default function Header({ paperMode, kalshiOk }) {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const tz = 'America/New_York'
  const timeStr = now.toLocaleTimeString('en-US', {
    timeZone: tz,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })

  return (
    <header
      className="flex items-center justify-between px-4 md:px-8 py-3 border-b shrink-0"
      style={{ background: '#0a0a10', borderColor: '#2a2a3a' }}
    >
      <div className="flex items-center gap-3 min-w-0">
        <Zap size={20} style={{ color: '#818cf8' }} className="shrink-0" />
        <span
          className="font-bold tracking-tight truncate"
          style={{ fontSize: 18, letterSpacing: '-0.02em', color: '#f8fafc' }}
        >
          OmniAlpha
        </span>
        <span
          className="text-[10px] font-medium hidden sm:inline tracking-[0.18em]"
          style={{ color: '#64748b' }}
        >
          WAR ROOM
        </span>
        <span
          className="text-[10px] font-semibold px-2 py-0.5 rounded shrink-0"
          style={{
            background: paperMode ? 'rgba(251, 191, 36, 0.12)' : 'rgba(255, 94, 125, 0.15)',
            color: paperMode ? '#fbbf24' : '#ff5e7d',
            border: `1px solid ${paperMode ? 'rgba(251, 191, 36, 0.25)' : 'rgba(255, 94, 125, 0.30)'}`,
            letterSpacing: '0.08em',
          }}
        >
          {paperMode ? 'PAPER' : 'LIVE'}
        </span>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        {kalshiOk === true && (
          <div className="flex items-center gap-1.5">
            <Wifi size={12} style={{ color: '#26de81' }} />
            <span className="text-[10px] tracking-wider" style={{ color: '#26de81' }}>
              KALSHI
            </span>
          </div>
        )}
        {kalshiOk === false && (
          <div className="flex items-center gap-1.5">
            <WifiOff size={12} style={{ color: '#ff5e7d' }} />
            <span className="text-[10px] tracking-wider" style={{ color: '#ff5e7d' }}>
              KALSHI
            </span>
          </div>
        )}
        <span
          className="font-mono text-sm"
          style={{ color: '#94a3b8', fontFamily: '"JetBrains Mono", monospace' }}
        >
          {timeStr} ET
        </span>
      </div>
    </header>
  )
}
