import { CheckCircle2, XCircle, HelpCircle, ArrowUp, ArrowDown, Clock } from 'lucide-react'
import LiveChart from './LiveChart'

const TV_SYMBOL = {
  bitcoin: 'BINANCE:BTCUSDT',
  ethereum: 'BINANCE:ETHUSDT',
}

const COIN_LABEL = {
  bitcoin: 'BTC',
  ethereum: 'ETH',
}

function formatTimeLeft(seconds) {
  if (seconds === null || seconds === undefined) return null
  if (seconds <= 0) return 'closing now'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m === 0) return `${s}s left`
  return `${m}m ${s}s left`
}


function explainTrade(p) {
  const coin = COIN_LABEL[p.coin] || (p.coin || 'price').toUpperCase()
  const isYes = (p.side || '').toLowerCase() === 'yes'
  const direction = isYes ? 'above' : 'below'
  const oppDir = isYes ? 'below' : 'above'
  const strike = p.strike
  const current = p.current_price
  const winning = p.winning
  const distance = (strike && current) ? current - strike : null
  const distAbs = distance !== null ? Math.abs(distance) : null
  const distPct = (distAbs !== null && current) ? (distAbs / current) * 100 : null

  // The hope: tells the user what direction we want price to go from here
  let hope, hopeDirection
  if (winning === true) {
    // We're winning. We want it to STAY where it is.
    hope = `Need ${coin} to STAY ${direction} $${strike?.toLocaleString('en-US', { maximumFractionDigits: 2 }) || '—'} until close.`
    hopeDirection = 'stay'
  } else if (winning === false) {
    // We're losing. We need it to flip across the strike.
    if (isYes) {
      hope = `Need ${coin} to RISE +$${distAbs?.toFixed(2)} (${distPct?.toFixed(2)}%) to win.`
      hopeDirection = 'up'
    } else {
      hope = `Need ${coin} to DROP -$${distAbs?.toFixed(2)} (${distPct?.toFixed(2)}%) to win.`
      hopeDirection = 'down'
    }
  } else {
    hope = 'Waiting on price feed…'
    hopeDirection = 'stay'
  }

  // The bet: english summary of what we bet
  const bet = `We bet ${coin} will be ${direction} $${strike?.toLocaleString('en-US', { maximumFractionDigits: 2 }) || '—'} at close.`

  // Status: where price is relative to strike
  let location
  if (distance === null) {
    location = `${coin} price unknown`
  } else if (distance >= 0) {
    location = `${coin} is $${distAbs?.toFixed(2)} ABOVE strike`
  } else {
    location = `${coin} is $${distAbs?.toFixed(2)} BELOW strike`
  }

  return { bet, location, hope, hopeDirection, distance }
}


function StatusPill({ winning }) {
  if (winning === true) {
    return (
      <span
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-bold tracking-wider"
        style={{ background: 'rgba(38, 222, 129, 0.12)', color: '#26de81', border: '1px solid rgba(38, 222, 129, 0.30)' }}
      >
        <CheckCircle2 size={12} /> WINNING
      </span>
    )
  }
  if (winning === false) {
    return (
      <span
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-bold tracking-wider"
        style={{ background: 'rgba(255, 94, 125, 0.12)', color: '#ff5e7d', border: '1px solid rgba(255, 94, 125, 0.30)' }}
      >
        <XCircle size={12} /> LOSING
      </span>
    )
  }
  return (
    <span
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-bold tracking-wider"
      style={{ background: 'rgba(148, 163, 184, 0.10)', color: '#94a3b8', border: '1px solid #2a2a3a' }}
    >
      <HelpCircle size={12} /> WAITING
    </span>
  )
}

function PositionCard({ p }) {
  const winning = p.winning  // true / false / null
  const borderColor = winning === true ? '#26de81' : winning === false ? '#ff5e7d' : '#2a2a3a'
  const sideColor = p.side === 'yes' ? '#26de81' : '#ff5e7d'
  const tvSymbol = TV_SYMBOL[p.coin] || 'BINANCE:BTCUSDT'

  return (
    <div
      className="rounded-xl border overflow-hidden gradient-card animate-fade-in-up"
      style={{ borderColor, borderLeftWidth: 4, borderLeftColor: borderColor }}
    >
      <div className="flex items-start justify-between px-4 py-3" style={{ borderBottom: '1px solid #2a2a3a' }}>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] font-bold" style={{ color: '#64748b' }}>#{p.id}</span>
            <span
              className="font-mono text-sm font-semibold truncate"
              style={{ color: '#f8fafc', fontFamily: '"JetBrains Mono", monospace' }}
            >
              {p.market_ticker}
            </span>
            <span className="font-bold text-xs" style={{ color: sideColor }}>
              {p.side.toUpperCase()} @ {p.price_cents}¢
            </span>
            <span className="text-xs" style={{ color: '#64748b' }}>· {p.strategy}</span>
          </div>
          {p.market_subtitle && (
            <div className="text-xs mt-1" style={{ color: '#94a3b8' }}>{p.market_subtitle}</div>
          )}
        </div>
        <StatusPill winning={winning} />
      </div>

      {/* Plain-English explanation block */}
      <div className="px-4 py-3" style={{ borderBottom: '1px solid #1a1a24' }}>
        {(() => {
          const ex = explainTrade(p)
          const HopeIcon = ex.hopeDirection === 'up' ? ArrowUp : ex.hopeDirection === 'down' ? ArrowDown : null
          const hopeColor =
            ex.hopeDirection === 'up' ? '#26de81' :
            ex.hopeDirection === 'down' ? '#ff5e7d' :
            (winning === true ? '#26de81' : winning === false ? '#ff5e7d' : '#94a3b8')
          const timeLeft = formatTimeLeft(p.seconds_to_close)
          return (
            <>
              <div className="text-sm leading-snug" style={{ color: '#f8fafc' }}>
                {ex.bet}
              </div>
              <div className="text-xs mt-1.5" style={{ color: '#94a3b8' }}>
                {ex.location} · stake ${p.stake_usd.toFixed(2)}
              </div>
              <div className="flex items-center gap-1.5 mt-2 text-sm font-medium" style={{ color: hopeColor }}>
                {HopeIcon && <HopeIcon size={14} />}
                <span>{ex.hope}</span>
              </div>
              {timeLeft && (
                <div className="flex items-center gap-1.5 mt-1.5 text-xs" style={{ color: '#64748b' }}>
                  <Clock size={11} /> {timeLeft}
                </div>
              )}
            </>
          )
        })()}
      </div>

      <div className="px-2 pb-2 pt-1">
        <LiveChart symbol={tvSymbol} interval="1" height={300} containerId={`tv-pos-${p.id}`} />
        <div className="px-2 pt-1 text-[10px] text-right" style={{ color: '#64748b' }}>
          Live {p.coin === 'ethereum' ? 'ETH' : 'BTC'} via TradingView · strike ${p.strike?.toLocaleString('en-US', { maximumFractionDigits: 2 }) || '—'}
        </div>
      </div>
    </div>
  )
}

function pickRecentSymbol(recentEntries) {
  // Look at the most recent activity; if any ticker contains ETH, use ETH; else BTC.
  const e = (recentEntries || []).find((x) => x.message)
  if (e && /ETH/i.test(e.message)) return { symbol: 'BINANCE:ETHUSDT', label: 'ETH' }
  return { symbol: 'BINANCE:BTCUSDT', label: 'BTC' }
}


export default function OpenPositions({ positions, recentEntries }) {
  const { symbol, label } = pickRecentSymbol(recentEntries)
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <div
          className="text-[10px] font-bold tracking-[0.14em] uppercase"
          style={{ color: '#94a3b8' }}
        >
          Open Positions
        </div>
        <span className="text-[10px]" style={{ color: '#64748b' }}>
          {positions.length} active
        </span>
      </div>

      {positions.length === 0 ? (
        <div
          className="rounded-xl gradient-card border overflow-hidden"
          style={{ borderColor: '#2a2a3a' }}
        >
          <div className="px-4 py-3" style={{ borderBottom: '1px solid #2a2a3a' }}>
            <div className="text-sm" style={{ color: '#94a3b8' }}>
              No open positions — watching live {label}.
            </div>
            <div className="text-xs mt-1" style={{ color: '#64748b' }}>
              Tracking the asset of your last trade. When a position opens, this switches to that position's coin live.
            </div>
          </div>
          <div className="px-2 pb-2 pt-2">
            <LiveChart symbol={symbol} interval="1" height={360} containerId={`tv-watch-${label}`} />
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {positions.map((p) => (
            <PositionCard key={p.id} p={p} />
          ))}
        </div>
      )}
    </div>
  )
}
