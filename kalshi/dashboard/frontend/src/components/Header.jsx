import { useState } from 'react'
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
  paperMode,        // true = paper, false = live
  onModeToggle,     // async (toLive: bool) => void
}) {
  const [toggling, setToggling] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const handleBadgeClick = () => {
    if (toggling) return
    setConfirmOpen(true)
  }
  const handleConfirm = async () => {
    setConfirmOpen(false)
    setToggling(true)
    try {
      // paperMode true means we're currently paper → flip to_live=true
      await onModeToggle(paperMode === true)
    } finally {
      // Re-enable after ~75s (the bot's restart window)
      setTimeout(() => setToggling(false), 75000)
    }
  }
  const handleCancel = () => setConfirmOpen(false)

  // Three visual states: PAPER (yellow), LIVE (red+pulse), RESTARTING (grey)
  const isPaper = paperMode === true
  const isLive  = paperMode === false
  const badgeStyle = toggling
    ? { background: 'rgba(100,116,139,0.12)', color: '#94a3b8', border: '1px solid rgba(100,116,139,0.35)' }
    : isLive
    ? { background: 'rgba(255,94,125,0.15)', color: '#ff5e7d', border: '1px solid rgba(255,94,125,0.45)', boxShadow: '0 0 10px rgba(255,94,125,0.4)' }
    : { background: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.25)' }
  const badgeLabel = toggling ? 'RESTARTING…' : isLive ? '⚡ LIVE' : 'PAPER'
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
        <div className="flex items-center gap-2 min-w-0">
          <Zap size={20} style={{ color: '#818cf8' }} className="shrink-0" />
          <span
            className="font-bold tracking-tight truncate"
            style={{ fontFamily: 'Inter', fontSize: 18, letterSpacing: '-0.02em', color: '#f8fafc' }}
          >
            Zack's Weather Bot
          </span>
          <span className="text-[10px] font-medium hidden sm:inline" style={{ color: '#64748b' }}>
            WAR ROOM
          </span>
        </div>
        <button
          onClick={handleBadgeClick}
          disabled={toggling || paperMode == null}
          title={
            toggling
              ? 'Bot restarting — please wait'
              : isLive
              ? 'Click to switch to PAPER mode (stop live trading)'
              : 'Click to switch to LIVE mode (real money)'
          }
          className="text-[10px] font-semibold px-2 py-0.5 rounded shrink-0 transition-all hover:scale-105"
          style={{
            ...badgeStyle,
            letterSpacing: '0.08em',
            cursor: toggling ? 'wait' : 'pointer',
          }}
        >
          {badgeLabel}
        </button>
      </div>

      {/* Mode-flip confirmation modal */}
      {confirmOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.7)' }}
          onClick={handleCancel}
        >
          <div
            onClick={e => e.stopPropagation()}
            className="rounded-xl p-5 max-w-md w-full"
            style={{
              background: 'linear-gradient(135deg, #13131d, #1a1a26)',
              border: `1px solid ${isPaper ? '#ff5e7d' : '#fbbf24'}55`,
              boxShadow: `0 0 30px ${isPaper ? '#ff5e7d' : '#fbbf24'}33`,
            }}
          >
            <div className="text-base font-bold mb-2" style={{ color: isPaper ? '#ff5e7d' : '#fbbf24' }}>
              {isPaper ? '⚠️ Switch to LIVE mode?' : '🟡 Switch back to PAPER mode?'}
            </div>
            <div className="text-[12px] leading-relaxed mb-4" style={{ color: '#cbd5e1' }}>
              {isPaper ? (
                <>
                  This will edit <code>kalshi/.env</code> to <code>PAPER_MODE=false</code> and restart the bot.
                  <br /><br />
                  <b style={{ color: '#ff5e7d' }}>Next order will use REAL MONEY from your Kalshi account.</b>
                  <br /><br />
                  All guardrails (daily loss cap, max trades, capital-at-risk) still apply.
                  Restart takes ~60s — bot will reconnect via the watchdog automatically.
                </>
              ) : (
                <>
                  This will edit <code>kalshi/.env</code> to <code>PAPER_MODE=true</code> and restart the bot.
                  No new live orders will fire. Existing open positions on Kalshi remain — they settle naturally.
                </>
              )}
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={handleCancel}
                className="px-3 py-1.5 rounded text-[11px] font-semibold"
                style={{ background: '#1a1a26', color: '#94a3b8', border: '1px solid #2a2a3a' }}
              >
                CANCEL
              </button>
              <button
                onClick={handleConfirm}
                className="px-3 py-1.5 rounded text-[11px] font-bold"
                style={{
                  background: isPaper ? 'rgba(255,94,125,0.15)' : 'rgba(251,191,36,0.15)',
                  color: isPaper ? '#ff5e7d' : '#fbbf24',
                  border: `1px solid ${isPaper ? '#ff5e7d' : '#fbbf24'}55`,
                }}
              >
                {isPaper ? 'GO LIVE' : 'GO PAPER'}
              </button>
            </div>
          </div>
        </div>
      )}

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
        <div className="hidden lg:block text-right leading-tight">
          <div className="text-[9px] text-text-muted font-semibold tracking-widest">TODAY</div>
          <div
            className="stat-value font-bold text-[13px]"
            style={{ color: todayPos ? '#26de81' : '#ff5e7d' }}
          >
            {todayPos ? '+' : ''}${Math.abs(todayPnl ?? 0).toFixed(2)}
          </div>
        </div>
        <div className="hidden lg:block text-right leading-tight">
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
              className="stat-value text-[10px] px-1.5 py-0.5 rounded hidden sm:inline"
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
