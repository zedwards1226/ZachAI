import { Menu, X, Zap, Wifi, WifiOff } from 'lucide-react'

export default function Header({
  lifetimePnl,
  todayPnl,
  kalshiOk,
  pingMs,
  countdown,
  scanning,
  onScan,
  mobileMenuOpen,
  onToggleMobile,
}) {
  const lifePos = (lifetimePnl ?? 0) >= 0
  const todayPos = (todayPnl ?? 0) >= 0
  const pingColor = !pingMs
    ? '#ff5e7d'
    : pingMs < 200
    ? '#26de81'
    : pingMs < 500
    ? '#fbbf24'
    : '#ff5e7d'

  return (
    <header
      className="flex items-center justify-between px-4 py-3 border-b shrink-0"
      style={{ background: '#0a0a10', borderColor: '#2a2a3a' }}
    >
      <div className="flex items-center gap-3">
        <button
          className="md:hidden text-text-secondary hover:text-text-primary mr-1"
          onClick={onToggleMobile}
          aria-label="Toggle menu"
        >
          {mobileMenuOpen ? <X size={18} /> : <Menu size={18} />}
        </button>
        <div className="flex items-center gap-2">
          <Zap size={20} style={{ color: '#818cf8' }} />
          <span
            className="font-bold tracking-tight"
            style={{ fontFamily: 'Inter', fontSize: 18, letterSpacing: '-0.02em', color: '#f8fafc' }}
          >
            WeatherAlpha
          </span>
          <span className="text-[10px] font-medium" style={{ color: '#64748b' }}>
            WAR ROOM
          </span>
        </div>
        <span
          className="text-[10px] font-semibold px-2 py-0.5 rounded"
          style={{
            background: 'rgba(251, 191, 36, 0.12)',
            color: '#fbbf24',
            border: '1px solid rgba(251, 191, 36, 0.25)',
            letterSpacing: '0.08em',
          }}
        >
          PAPER
        </span>
      </div>

      <div className="hidden md:flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-text-muted font-medium tracking-wider">NEXT SCAN</span>
          <span
            className="stat-value font-bold text-lg"
            style={{
              color: countdown <= 10 ? '#fbbf24' : '#818cf8',
              minWidth: '2.5ch',
              display: 'inline-block',
              textAlign: 'right',
            }}
          >
            {String(countdown).padStart(2, '0')}s
          </span>
        </div>
        <button
          onClick={onScan}
          disabled={scanning}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-200"
          style={{
            background: scanning ? 'rgba(129,140,248,0.08)' : 'rgba(129,140,248,0.15)',
            color: scanning ? '#475569' : '#818cf8',
            border: `1px solid ${scanning ? '#2a2a3a' : 'rgba(129,140,248,0.35)'}`,
            cursor: scanning ? 'not-allowed' : 'pointer',
          }}
        >
          {scanning ? (
            <>
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent animate-pulse-glow" />
              SCANNING
            </>
          ) : (
            '▶ SCAN NOW'
          )}
        </button>
      </div>

      <div className="flex items-center gap-5">
        <div className="hidden sm:block text-right leading-tight">
          <div className="text-[9px] text-text-muted font-semibold tracking-widest">TODAY</div>
          <div
            className="stat-value font-bold text-[13px]"
            style={{ color: todayPos ? '#26de81' : '#ff5e7d' }}
          >
            {todayPos ? '+' : ''}${Math.abs(todayPnl ?? 0).toFixed(2)}
          </div>
        </div>
        <div className="hidden sm:block text-right leading-tight">
          <div className="text-[9px] text-text-muted font-semibold tracking-widest">LIFETIME</div>
          <div
            className="stat-value font-bold text-[13px]"
            style={{ color: lifePos ? '#26de81' : '#ff5e7d' }}
          >
            {lifePos ? '+' : ''}${Math.abs(lifetimePnl ?? 0).toFixed(2)}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div
            className="w-2 h-2 rounded-full"
            style={{
              background: kalshiOk ? '#26de81' : '#ff5e7d',
              boxShadow: kalshiOk ? '0 0 6px #26de81' : '0 0 6px #ff5e7d',
              animation: kalshiOk ? 'pulseGlow 2s ease-in-out infinite' : 'none',
            }}
          />
          <div className="flex items-center gap-1">
            {kalshiOk ? (
              <Wifi size={13} style={{ color: '#26de81' }} />
            ) : (
              <WifiOff size={13} style={{ color: '#ff5e7d' }} />
            )}
            <span
              className="text-[11px] font-medium hidden sm:inline"
              style={{ color: kalshiOk ? '#26de81' : '#ff5e7d' }}
            >
              {kalshiOk ? 'LIVE' : 'DOWN'}
            </span>
          </div>
          {pingMs && (
            <span
              className="stat-value text-[10px] px-1.5 py-0.5 rounded"
              style={{
                color: pingColor,
                background: `${pingColor}18`,
                border: `1px solid ${pingColor}30`,
              }}
            >
              {pingMs}ms
            </span>
          )}
        </div>
      </div>
    </header>
  )
}
