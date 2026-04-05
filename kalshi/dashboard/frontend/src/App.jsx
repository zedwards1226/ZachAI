import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { BarChart2, Cloud, History, TrendingUp, ShieldAlert, Layers } from 'lucide-react'

import Header          from './components/Header'
import CityCard        from './components/CityCard'
import PnlChart        from './components/PnlChart'
import GuardrailMeters from './components/GuardrailMeters'
import DecisionLog     from './components/DecisionLog'
import MarketBrowser   from './components/MarketBrowser'
import ScanRadar       from './components/ScanRadar'

const CITIES      = ['NYC', 'CHI', 'MIA', 'LAX', 'MEM', 'DEN']
const SCAN_PERIOD = 60    // seconds
const CITY_CYCLE  = 2800  // ms per city

// ── Poll hook ────────────────────────────────────────────────────────────────
function useApi(path, interval = 5000) {
  const [data, setData]   = useState(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let alive = true
    const go = async () => {
      try {
        const r = await fetch(path)
        if (r.ok) { setData(await r.json()); setError(false) }
        else setError(true)
      } catch { setError(true) }
    }
    go()
    const id = setInterval(() => { if (alive) go() }, interval)
    return () => { alive = false; clearInterval(id) }
  }, [path, interval])

  return { data, error }
}

// ── Log entry factory ─────────────────────────────────────────────────────────
let _lid = 0
function mkEntry(type, msg) {
  return { id: ++_lid, ts: new Date().toISOString(), type, msg }
}

// ── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({ label, value, color, sub }) {
  return (
    <div
      className="flex flex-col gap-1 px-4 py-3 rounded-xl shrink-0"
      style={{ background: '#1a1a24', border: '1px solid #2a2a3a' }}
    >
      <div className="text-[10px] font-medium text-text-muted" style={{ letterSpacing: '0.06em' }}>
        {label}
      </div>
      <div
        className="stat-value font-bold"
        style={{ fontSize: 18, color: color ?? '#f8fafc', letterSpacing: '-0.02em' }}
      >
        {value}
      </div>
      {sub && (
        <div className="text-[10px] text-text-muted">{sub}</div>
      )}
    </div>
  )
}

// ── Tab bar ───────────────────────────────────────────────────────────────────
const TABS = [
  { id: 'weather', label: 'Weather',  Icon: Cloud     },
  { id: 'markets', label: 'Markets',  Icon: BarChart2 },
  { id: 'history', label: 'History',  Icon: History   },
]

function TabBar({ activeTab, onTab }) {
  return (
    <div
      className="flex gap-1 px-2 border-b shrink-0"
      style={{ borderColor: '#2a2a3a' }}
    >
      {TABS.map(({ id, label, Icon }) => {
        const active = activeTab === id
        return (
          <button
            key={id}
            onClick={() => onTab(id)}
            className="relative flex items-center gap-1.5 px-4 py-3 text-sm font-medium transition-colors"
            style={{ color: active ? '#818cf8' : '#475569' }}
          >
            <Icon size={14} />
            {label}
            {active && (
              <motion.div
                layoutId="tabIndicator"
                className="absolute bottom-0 left-0 right-0 h-0.5 rounded-t"
                style={{ background: '#818cf8' }}
                transition={{ type: 'spring', stiffness: 400, damping: 30 }}
              />
            )}
          </button>
        )
      })}
    </div>
  )
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  // API polling
  const { data: health     } = useApi('/api/health',       10000)
  const { data: forecasts  } = useApi('/api/forecasts',     8000)
  const { data: pnlData    } = useApi('/api/pnl',           5000)
  const { data: guardrails } = useApi('/api/guardrails',    5000)
  const { data: summary    } = useApi('/api/summary',       8000)
  const { data: logData    } = useApi('/api/decision-log',  3000)

  // UI state
  const [activeTab,      setActiveTab]      = useState('weather')
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [activeCity,     setActiveCity]     = useState('NYC')
  const [scanning,       setScanning]       = useState(false)
  const [countdown,      setCountdown]      = useState(SCAN_PERIOD)
  const [pingMs,         setPingMs]         = useState(null)

  // Local fallback log (used when backend /api/decision-log unavailable)
  const [localLog, setLocalLog] = useState([
    mkEntry('system',  'WeatherAlpha dashboard initialised'),
    mkEntry('connect', 'Connecting to Kalshi API…'),
  ])
  const addLog = useCallback((type, msg) => {
    setLocalLog(prev => [mkEntry(type, msg), ...prev].slice(0, 200))
  }, [])

  const nextScanRef = useRef(Date.now() + SCAN_PERIOD * 1000)
  const scanningRef = useRef(false)

  // Merge backend + local log
  const logEntries = logData?.entries
    ? logData.entries.map((e, i) => ({ ...e, id: e.id ?? `be-${i}` }))
    : localLog

  // ── City cycling ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const id = setInterval(() => {
      setActiveCity(c => CITIES[(CITIES.indexOf(c) + 1) % CITIES.length])
    }, CITY_CYCLE)
    return () => clearInterval(id)
  }, [])

  // ── Scan ──────────────────────────────────────────────────────────────────────
  const runScan = useCallback(async () => {
    if (scanningRef.current) return
    scanningRef.current = true
    setScanning(true)
    addLog('scan', 'Initiating market scan across all cities…')
    try {
      const r = await fetch('/api/scan', { method: 'POST' })
      const d = await r.json()
      if (d.results) {
        d.results.forEach(res => {
          if (res.trade_placed) {
            addLog('trade', `${res.city} — ${res.side} ${res.contracts}ct @ ${res.price_cents}¢ | edge ${(res.edge * 100).toFixed(1)}%`)
          } else if (res.blocked) {
            addLog('block', `${res.city} — blocked: ${res.reason}`)
          } else if (res.edge != null) {
            addLog('skip', `${res.city} — edge ${(res.edge * 100).toFixed(1)}% (below threshold)`)
          } else {
            addLog('skip', `${res.city} — ${res.reason ?? 'no opportunity'}`)
          }
        })
      }
    } catch (e) {
      addLog('error', `Scan failed: ${e.message}`)
    } finally {
      scanningRef.current = false
      setScanning(false)
    }
  }, [addLog])

  // ── Countdown + auto-scan ────────────────────────────────────────────────────
  useEffect(() => {
    const tick = setInterval(() => {
      const secs = Math.max(0, Math.round((nextScanRef.current - Date.now()) / 1000))
      setCountdown(secs)
      if (secs === 0) {
        nextScanRef.current = Date.now() + SCAN_PERIOD * 1000
        runScan()
      }
    }, 500)
    return () => clearInterval(tick)
  }, [runScan])

  // ── Ping ─────────────────────────────────────────────────────────────────────
  useEffect(() => {
    const measure = async () => {
      const t0 = performance.now()
      try {
        const r = await fetch('/api/health')
        if (r.ok) setPingMs(Math.round(performance.now() - t0))
        else setPingMs(null)
      } catch { setPingMs(null) }
    }
    measure()
    const id = setInterval(measure, 10000)
    return () => clearInterval(id)
  }, [])

  // ── Log Kalshi connection changes ────────────────────────────────────────────
  const prevConnRef = useRef(null)
  useEffect(() => {
    const connected = health?.kalshi_connected
    if (connected === prevConnRef.current) return
    prevConnRef.current = connected
    if (connected === true)  addLog('connect', 'Kalshi API connected')
    if (connected === false) addLog('error',   'Kalshi API disconnected')
  }, [health, addLog])

  // ── Derived values ────────────────────────────────────────────────────────────
  const fcList    = forecasts?.forecasts ?? []
  const pnlSeries = pnlData?.snapshots   ?? []
  const kalshiOk  = health?.kalshi_connected === true

  const base     = 1000
  const capital  = pnlSeries.length ? (pnlSeries[pnlSeries.length - 1]?.capital_usd ?? base) : base
  const pnlUsd   = capital - base
  const winRate  = summary?.win_rate ?? null
  const trades   = (summary?.wins ?? 0) + (summary?.losses ?? 0)
  const openRisk = summary?.open_risk_usd ?? 0

  const pnlPos = pnlUsd >= 0

  // ── Render ────────────────────────────────────────────────────────────────────
  return (
    <div
      className="flex flex-col h-full overflow-hidden"
      style={{ background: '#0f0f14' }}
    >
      {/* Header */}
      <Header
        pnlUsd={pnlUsd}
        kalshiOk={kalshiOk}
        pingMs={pingMs}
        countdown={countdown}
        scanning={scanning}
        onScan={runScan}
        mobileMenuOpen={mobileMenuOpen}
        onToggleMobile={() => setMobileMenuOpen(v => !v)}
      />

      {/* Stats row */}
      <div
        className="flex items-center gap-3 px-4 py-3 border-b overflow-x-auto shrink-0"
        style={{ borderColor: '#2a2a3a', scrollbarWidth: 'none' }}
      >
        <StatCard
          label="CAPITAL"
          value={`$${capital.toFixed(2)}`}
          color="#f8fafc"
        />
        <StatCard
          label="TODAY P&L"
          value={`${pnlPos ? '+' : ''}$${pnlUsd.toFixed(2)}`}
          color={pnlPos ? '#26de81' : '#ff5e7d'}
        />
        {winRate != null && (
          <StatCard
            label="WIN RATE"
            value={`${(winRate * 100).toFixed(0)}%`}
            color={winRate >= 0.5 ? '#26de81' : '#fbbf24'}
          />
        )}
        <StatCard
          label="TRADES"
          value={trades}
          color="#94a3b8"
          sub={`${summary?.wins ?? 0}W / ${summary?.losses ?? 0}L`}
        />
        {openRisk > 0 && (
          <StatCard
            label="OPEN RISK"
            value={`$${openRisk.toFixed(0)}`}
            color="#fbbf24"
          />
        )}
        <StatCard
          label="TRADE WINDOW"
          value={guardrails?.trade_window_open === false ? 'CLOSED' : 'OPEN'}
          color={guardrails?.trade_window_open === false ? '#ff5e7d' : '#26de81'}
        />
        <StatCard
          label="KALSHI"
          value={kalshiOk ? 'LIVE' : 'DOWN'}
          color={kalshiOk ? '#26de81' : '#ff5e7d'}
          sub={pingMs ? `${pingMs}ms` : undefined}
        />
      </div>

      {/* Tabs */}
      <TabBar activeTab={activeTab} onTab={setActiveTab} />

      {/* Tab content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <AnimatePresence mode="wait">
          {activeTab === 'weather' && (
            <motion.div
              key="weather"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.2 }}
              className="h-full overflow-y-auto"
            >
              {/* Weather layout: city grid | pnl chart | decision log */}
              <div
                className="h-full grid gap-4 p-4"
                style={{ gridTemplateColumns: '1fr 1.3fr 1fr' }}
              >
                {/* Col 1: City cards */}
                <div className="flex flex-col gap-3 overflow-y-auto min-h-0">
                  <div className="flex items-center justify-between mb-1">
                    <h2 className="text-xs font-semibold text-text-muted" style={{ letterSpacing: '0.08em' }}>
                      CITY FORECASTS
                    </h2>
                    {scanning && (
                      <span
                        className="text-[10px] font-semibold animate-pulse-glow"
                        style={{ color: '#818cf8' }}
                      >
                        SCANNING…
                      </span>
                    )}
                  </div>

                  {/* Radar (compact) */}
                  <div
                    className="card p-3"
                    style={{ border: '1px solid #2a2a3a' }}
                  >
                    <div className="text-[10px] font-semibold text-text-muted mb-2" style={{ letterSpacing: '0.06em' }}>
                      MARKET RADAR
                    </div>
                    <ScanRadar forecasts={fcList} activeCity={activeCity} scanning={scanning} />
                  </div>

                  {/* City cards grid */}
                  <div className="grid grid-cols-1 gap-2">
                    {CITIES.map(code => {
                      const fc = fcList.find(f => f.city === code)
                      return (
                        <CityCard
                          key={code}
                          forecast={fc ? fc : { city: code }}
                          isActive={code === activeCity}
                          scanning={scanning && code === activeCity}
                        />
                      )
                    })}
                  </div>
                </div>

                {/* Col 2: P&L chart + guardrails */}
                <div className="flex flex-col gap-4 min-h-0 overflow-y-auto">
                  <div className="card p-4 flex-1 min-h-0" style={{ minHeight: 280 }}>
                    <div className="text-[10px] font-semibold text-text-muted mb-3" style={{ letterSpacing: '0.08em' }}>
                      CAPITAL CURVE
                    </div>
                    <div style={{ height: 'calc(100% - 28px)' }}>
                      <PnlChart pnl={pnlSeries} summary={summary} />
                    </div>
                  </div>

                  <div className="card p-4 shrink-0">
                    <div className="flex items-center gap-2 mb-3">
                      <ShieldAlert size={13} style={{ color: '#818cf8' }} />
                      <div className="text-[10px] font-semibold text-text-muted" style={{ letterSpacing: '0.08em' }}>
                        RISK GUARDRAILS
                      </div>
                    </div>
                    <GuardrailMeters guardrails={guardrails} />
                  </div>
                </div>

                {/* Col 3: Decision log */}
                <div className="card p-4 flex flex-col min-h-0">
                  <div className="flex items-center justify-between mb-3">
                    <div className="text-[10px] font-semibold text-text-muted" style={{ letterSpacing: '0.08em' }}>
                      DECISION LOG
                    </div>
                    <div className="flex items-center gap-1.5">
                      <div
                        className="w-1.5 h-1.5 rounded-full animate-pulse-glow"
                        style={{ background: '#26de81' }}
                      />
                      <span className="text-[10px] font-medium" style={{ color: '#26de81' }}>
                        LIVE
                      </span>
                    </div>
                  </div>
                  <div className="flex-1 min-h-0">
                    <DecisionLog entries={logEntries} />
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {activeTab === 'markets' && (
            <motion.div
              key="markets"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.2 }}
              className="h-full overflow-y-auto p-4"
            >
              <div className="max-w-5xl mx-auto">
                <div className="flex items-center gap-2 mb-4">
                  <BarChart2 size={16} style={{ color: '#818cf8' }} />
                  <h2 className="font-semibold text-text-primary">Market Browser</h2>
                </div>
                <MarketBrowser />
              </div>
            </motion.div>
          )}

          {activeTab === 'history' && (
            <motion.div
              key="history"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.2 }}
              className="h-full overflow-y-auto p-4"
            >
              <div className="max-w-5xl mx-auto">
                <div className="flex items-center gap-2 mb-4">
                  <History size={16} style={{ color: '#818cf8' }} />
                  <h2 className="font-semibold text-text-primary">Trade History</h2>
                </div>

                {/* P&L chart full width */}
                <div className="card p-4 mb-4" style={{ height: 320 }}>
                  <div className="text-[10px] font-semibold text-text-muted mb-3" style={{ letterSpacing: '0.08em' }}>
                    CAPITAL CURVE
                  </div>
                  <div style={{ height: 'calc(100% - 28px)' }}>
                    <PnlChart pnl={pnlSeries} summary={summary} />
                  </div>
                </div>

                {/* Decision log full width */}
                <div className="card p-4" style={{ minHeight: 400 }}>
                  <div className="text-[10px] font-semibold text-text-muted mb-3" style={{ letterSpacing: '0.08em' }}>
                    FULL DECISION LOG
                  </div>
                  <div style={{ height: 360 }}>
                    <DecisionLog entries={logEntries} />
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Footer */}
      <footer
        className="flex items-center justify-between px-4 py-2 border-t shrink-0 text-[10px] text-text-muted"
        style={{ borderColor: '#2a2a3a', background: '#0f0f14' }}
      >
        <span>WeatherAlpha · Kalshi Weather Markets · Paper Mode</span>
        <span className="stat-value">{new Date().toLocaleString()}</span>
        <div className="flex items-center gap-1.5">
          <div
            className="w-1.5 h-1.5 rounded-full"
            style={{
              background: kalshiOk ? '#26de81' : '#ff5e7d',
              animation: 'pulseGlow 2s ease-in-out infinite',
            }}
          />
          <span>{kalshiOk ? 'Connected' : 'Disconnected'}</span>
        </div>
      </footer>
    </div>
  )
}
