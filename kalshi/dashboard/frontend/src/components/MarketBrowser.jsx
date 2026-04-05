import { useState, useMemo } from 'react'
import { Search, ChevronDown, ChevronUp } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

const CATEGORY_CITIES = ['All', 'NYC', 'CHI', 'MIA', 'LAX', 'DEN', 'MEM']

function useMarkets() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)

  const fetch_ = () => {
    setLoading(true)
    fetch('/api/markets/all')
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }

  // Fetch on mount
  useState(() => { fetch_() }, [])

  return { data, loading, refetch: fetch_ }
}

function MarketRow({ market, isExpanded, onToggle }) {
  const yesPrice = market.yes_price ?? market.kalshi_yes_price ?? null
  const noPrice  = yesPrice != null ? (100 - yesPrice) : null

  return (
    <>
      <tr
        onClick={onToggle}
        className="border-b cursor-pointer transition-colors"
        style={{
          borderColor: '#1a1a24',
          background: isExpanded ? 'rgba(129, 140, 248, 0.06)' : 'transparent',
        }}
        onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.03)' }}
        onMouseLeave={e => { e.currentTarget.style.background = isExpanded ? 'rgba(129, 140, 248, 0.06)' : 'transparent' }}
      >
        <td className="py-2.5 px-3">
          <span className="stat-value text-xs font-semibold text-text-primary">
            {market.ticker ?? market.series_ticker ?? '—'}
          </span>
        </td>
        <td className="py-2.5 px-3">
          <span className="stat-value text-xs text-text-secondary">
            {market.strike_f ?? market.kalshi_strike_f ?? '—'}°F
          </span>
        </td>
        <td className="py-2.5 px-3">
          {yesPrice != null ? (
            <span className="stat-value text-xs font-semibold" style={{ color: '#26de81' }}>
              {yesPrice}%
            </span>
          ) : (
            <span className="text-text-muted text-xs">—</span>
          )}
        </td>
        <td className="py-2.5 px-3">
          {noPrice != null ? (
            <span className="stat-value text-xs font-semibold" style={{ color: '#ff5e7d' }}>
              {noPrice}%
            </span>
          ) : (
            <span className="text-text-muted text-xs">—</span>
          )}
        </td>
        <td className="py-2.5 px-3">
          <span className="stat-value text-xs text-text-muted">
            {market.volume ?? '—'}
          </span>
        </td>
        <td className="py-2.5 px-3">
          <div className="flex items-center gap-2">
            <span
              className="text-[10px] font-semibold px-2 py-0.5 rounded"
              style={{
                background: 'rgba(129, 140, 248, 0.12)',
                color: '#818cf8',
                border: '1px solid rgba(129, 140, 248, 0.25)',
              }}
            >
              VIEW
            </span>
            {isExpanded ? (
              <ChevronUp size={12} className="text-text-muted" />
            ) : (
              <ChevronDown size={12} className="text-text-muted" />
            )}
          </div>
        </td>
      </tr>

      {/* Expanded detail row */}
      {isExpanded && (
        <tr style={{ background: 'rgba(129, 140, 248, 0.04)' }}>
          <td colSpan={6} className="px-4 py-3">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div>
                <div className="text-text-muted mb-1">Ticker</div>
                <div className="stat-value text-text-primary font-semibold">
                  {market.ticker ?? '—'}
                </div>
              </div>
              <div>
                <div className="text-text-muted mb-1">Strike</div>
                <div className="stat-value text-text-primary">
                  {market.strike_f ?? market.kalshi_strike_f ?? '—'}°F
                </div>
              </div>
              <div>
                <div className="text-text-muted mb-1">YES / NO</div>
                <div className="stat-value">
                  <span style={{ color: '#26de81' }}>{yesPrice ?? '—'}%</span>
                  {' / '}
                  <span style={{ color: '#ff5e7d' }}>{noPrice ?? '—'}%</span>
                </div>
              </div>
              <div>
                <div className="text-text-muted mb-1">Volume</div>
                <div className="stat-value text-text-secondary">
                  {market.volume ?? '—'}
                </div>
              </div>
              {market.close_time && (
                <div>
                  <div className="text-text-muted mb-1">Closes</div>
                  <div className="stat-value text-text-secondary">
                    {new Date(market.close_time).toLocaleString()}
                  </div>
                </div>
              )}
              {market.title && (
                <div className="col-span-2">
                  <div className="text-text-muted mb-1">Title</div>
                  <div className="text-text-secondary leading-snug">{market.title}</div>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

export default function MarketBrowser() {
  const [search, setSearch]     = useState('')
  const [category, setCategory] = useState('All')
  const [expanded, setExpanded] = useState(null)
  const [markets, setMarkets]   = useState([])
  const [loaded, setLoaded]     = useState(false)
  const [error, setError]       = useState(false)

  // Fetch once on mount
  useState(() => {
    fetch('/api/markets/all')
      .then(r => r.json())
      .then(d => {
        const list = Array.isArray(d) ? d : d.markets ?? d.results ?? []
        setMarkets(list)
        setLoaded(true)
      })
      .catch(() => { setError(true); setLoaded(true) })
  }, [])

  const filtered = useMemo(() => {
    let list = markets
    if (category !== 'All') {
      list = list.filter(m => {
        const t = (m.ticker ?? m.series_ticker ?? '').toUpperCase()
        return t.includes(category)
      })
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      list = list.filter(m =>
        (m.ticker ?? '').toLowerCase().includes(q) ||
        (m.title ?? '').toLowerCase().includes(q) ||
        (m.city ?? '').toLowerCase().includes(q)
      )
    }
    return list
  }, [markets, category, search])

  return (
    <div className="flex flex-col gap-4">

      {/* Controls */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Search */}
        <div
          className="relative flex-1"
        >
          <Search
            size={13}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none"
          />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search ticker, city…"
            className="w-full pl-8 pr-3 py-2 text-sm rounded-lg text-text-primary placeholder-text-muted outline-none transition-colors"
            style={{
              background: '#141420',
              border: '1px solid #2a2a3a',
              fontFamily: 'Inter, sans-serif',
            }}
            onFocus={e => { e.target.style.borderColor = '#818cf8' }}
            onBlur={e => { e.target.style.borderColor = '#2a2a3a' }}
          />
        </div>

        {/* Category buttons */}
        <div className="flex gap-1.5 overflow-x-auto pb-1">
          {CATEGORY_CITIES.map(city => (
            <button
              key={city}
              onClick={() => setCategory(city)}
              className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
              style={{
                background: category === city ? 'rgba(129, 140, 248, 0.2)' : 'rgba(255,255,255,0.04)',
                color: category === city ? '#818cf8' : '#475569',
                border: `1px solid ${category === city ? 'rgba(129, 140, 248, 0.4)' : '#2a2a3a'}`,
              }}
            >
              {city}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div
        className="rounded-xl overflow-hidden"
        style={{ border: '1px solid #2a2a3a' }}
      >
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr style={{ background: '#141420', borderBottom: '1px solid #2a2a3a' }}>
                {['Ticker', 'Strike', 'YES %', 'NO %', 'Volume', 'Action'].map(h => (
                  <th
                    key={h}
                    className="py-2.5 px-3 text-left text-[10px] font-semibold text-text-muted"
                    style={{ letterSpacing: '0.06em' }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {!loaded ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-text-muted text-sm">
                    Loading markets…
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-sm" style={{ color: '#ff5e7d' }}>
                    Failed to load market data
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-text-muted text-sm">
                    No markets found
                  </td>
                </tr>
              ) : (
                filtered.map((m, i) => (
                  <MarketRow
                    key={m.ticker ?? i}
                    market={m}
                    isExpanded={expanded === (m.ticker ?? i)}
                    onToggle={() => setExpanded(prev =>
                      prev === (m.ticker ?? i) ? null : (m.ticker ?? i)
                    )}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Footer */}
        <div
          className="flex items-center justify-between px-3 py-2 text-[10px] text-text-muted border-t"
          style={{ borderColor: '#1a1a24', background: '#141420' }}
        >
          <span>{filtered.length} of {markets.length} markets</span>
          <span>Kalshi Weather Markets</span>
        </div>
      </div>
    </div>
  )
}
