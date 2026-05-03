import { CheckCircle2, XCircle, HelpCircle } from 'lucide-react'
import LiveChart from './LiveChart'

const TV_SYMBOL = {
  bitcoin: 'BINANCE:BTCUSDT',
  ethereum: 'BINANCE:ETHUSDT',
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

      <div className="px-4 pt-3 pb-1 grid grid-cols-3 gap-3 text-xs">
        <div>
          <div className="text-[10px] tracking-[0.12em] uppercase" style={{ color: '#64748b' }}>Strike</div>
          <div className="font-mono font-semibold mt-0.5" style={{ color: '#f8fafc' }}>
            {p.strike ? `$${p.strike.toLocaleString('en-US', { maximumFractionDigits: 2 })}` : '—'}
          </div>
        </div>
        <div>
          <div className="text-[10px] tracking-[0.12em] uppercase" style={{ color: '#64748b' }}>
            {p.coin?.toUpperCase() || 'PRICE'} now
          </div>
          <div className="font-mono font-semibold mt-0.5" style={{ color: '#f8fafc' }}>
            {p.current_price ? `$${p.current_price.toLocaleString('en-US', { maximumFractionDigits: 2 })}` : '—'}
          </div>
        </div>
        <div>
          <div className="text-[10px] tracking-[0.12em] uppercase" style={{ color: '#64748b' }}>Stake</div>
          <div className="font-mono font-semibold mt-0.5" style={{ color: '#fbbf24' }}>
            ${p.stake_usd.toFixed(2)}
          </div>
        </div>
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
