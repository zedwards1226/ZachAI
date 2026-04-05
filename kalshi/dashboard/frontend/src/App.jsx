import { useState, useEffect, useRef, useCallback } from 'react'
import Radar        from './components/Radar'
import EdgeMeters   from './components/EdgeMeters'
import PnlChart     from './components/PnlChart'
import Guardrails   from './components/Guardrails'
import DecisionLog  from './components/DecisionLog'

const CITIES      = ['NYC', 'CHI', 'MIA', 'LAX', 'MEM', 'DEN']
const SCAN_PERIOD = 60   // seconds between auto-scans
const CITY_CYCLE  = 2800 // ms per city in radar

// ── Tiny hook: poll an endpoint ──────────────────────────────────────────────
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

// ── Log entry factory ────────────────────────────────────────────────────────
let _lid = 0
function mkEntry(type, msg) {
  return { id: ++_lid, ts: new Date().toISOString(), type, msg }
}

// ── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  // API data
  const { data: health,     error: noKalshi } = useApi('/api/health',     10000)
  const { data: forecasts }                    = useApi('/api/forecasts',   8000)
  const { data: pnlData }                      = useApi('/api/pnl',         5000)
  const { data: guardrails }                   = useApi('/api/guardrails',  5000)
  const { data: summary }                      = useApi('/api/summary',     8000)

  // Radar city cycle
  const [activeCity, setActiveCity] = useState('NYC')
  const [scanning,   setScanning]   = useState(false)

  // Countdown
  const [countdown, setCountdown]   = useState(SCAN_PERIOD)
  const nextScanRef                 = useRef(Date.now() + SCAN_PERIOD * 1000)
  const scanningRef                 = useRef(false)

  // Decision log
  const [logEntries, setLogEntries] = useState([
    mkEntry('system', 'WeatherAlpha dashboard initialised'),
    mkEntry('connect', 'Connecting to Kalshi API…'),
  ])
  const addLog = useCallback((type, msg) => {
    setLogEntries(prev => [mkEntry(type, msg), ...prev].slice(0, 200))
  }, [])

  // Kalshi ping latency
  const [pingMs, setPingMs] = useState(null)

  // ── City cycling ────────────────────────────────────────────────────────────
  useEffect(() => {
    const id = setInterval(() => {
      setActiveCity(c => CITIES[(CITIES.indexOf(c) + 1) % CITIES.length])
    }, CITY_CYCLE)
    return () => clearInterval(id)
  }, [])

  // ── Scan function ────────────────────────────────────────────────────────────
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
            addLog('trade', `${res.city} — ${res.side} ${res.contracts}ct @ ${res.price_cents}¢ | edge ${(res.edge*100).toFixed(1)}%`)
          } else if (res.blocked) {
            addLog('block', `${res.city} — blocked: ${res.reason}`)
          } else if (res.edge != null) {
            addLog('skip', `${res.city} — edge ${(res.edge*100).toFixed(1)}% (below threshold)`)
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

  // ── Countdown + auto-scan ───────────────────────────────────────────────────
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

  // ── Kalshi ping ─────────────────────────────────────────────────────────────
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

  // ── Log connection status ───────────────────────────────────────────────────
  const prevConnRef = useRef(null)
  useEffect(() => {
    const connected = health?.kalshi_connected
    if (connected === prevConnRef.current) return
    prevConnRef.current = connected
    if (connected === true)  addLog('connect', 'Kalshi API connected')
    if (connected === false) addLog('error',   'Kalshi API disconnected')
  }, [health, addLog])

  // ── Derived state ───────────────────────────────────────────────────────────
  const fcList     = forecasts?.forecasts ?? []
  const pnlSeries  = pnlData?.snapshots   ?? []
  const kalshiOk   = health?.kalshi_connected === true
  const pingColor  = !pingMs ? '#ff0040' : pingMs < 200 ? '#00ff41' : pingMs < 500 ? '#ffcc00' : '#ff0040'

  const base     = 1000
  const capital  = pnlSeries.length ? pnlSeries[pnlSeries.length - 1]?.capital_usd ?? base : base
  const pnlUsd   = capital - base
  const pnlPos   = pnlUsd >= 0

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full" style={{ background: '#050505' }}>

      {/* ── TOP BAR ──────────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-4 py-2 border-b border-[#001a08]"
              style={{ background: '#030803' }}>

        {/* Logo */}
        <div className="flex items-center gap-3">
          <div style={{
            fontFamily: 'Orbitron', color: '#00ff41',
            textShadow: '0 0 12px #00ff41, 0 0 24px rgba(0,255,65,0.4)',
            letterSpacing: '0.2em', fontSize: 15, fontWeight: 700,
          }}>
            WEATHERALPHA
          </div>
          <div className="text-[9px] text-[#003311] border border-[#001a08] rounded px-1">
            v0.1 · DEMO
          </div>
        </div>

        {/* Center: countdown */}
        <div className="flex items-center gap-2">
          <span className="text-[9px] text-[#003311]">NEXT SCAN</span>
          <span className={`font-bold ${countdown <= 10 ? 'text-[#ffcc00]' : 'text-[#006622]'}`}
                style={{
                  fontFamily: 'Orbitron', fontSize: 18,
                  textShadow: countdown <= 10 ? '0 0 8px #ffcc00' : 'none',
                }}>
            {String(countdown).padStart(2, '0')}s
          </span>
          <button
            onClick={runScan}
            disabled={scanning}
            className={`text-[9px] border rounded px-2 py-0.5 transition-all duration-200 ${
              scanning
                ? 'border-[#003311] text-[#003311] cursor-not-allowed'
                : 'border-[#006622] text-[#00ff41] hover:border-[#00ff41] cursor-pointer'
            } ${scanning ? '' : 'scan-pulse'}`}>
            {scanning ? '● SCANNING' : '▶ SCAN'}
          </button>
        </div>

        {/* Right: P&L + Kalshi status */}
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-[8px] text-[#003311]">P&amp;L TODAY</div>
            <div className="font-bold" style={{
              fontFamily: 'Orbitron', fontSize: 14,
              color: pnlPos ? '#00ff41' : '#ff0040',
              textShadow: pnlPos ? '0 0 8px #00ff41' : '0 0 8px #ff0040',
            }}>
              {pnlPos ? '+' : ''}{pnlUsd.toFixed(2)}
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <div className={`w-1.5 h-1.5 rounded-full ${kalshiOk ? 'bg-[#00ff41]' : 'bg-[#ff0040]'} ${kalshiOk ? 'glow-pulse' : ''}`} />
            <div className="text-[9px]" style={{ color: kalshiOk ? '#006622' : '#cc0030' }}>
              KALSHI {kalshiOk ? 'LIVE' : 'DOWN'}
            </div>
            {pingMs && (
              <div className="text-[8px] border rounded px-1"
                   style={{ color: pingColor, borderColor: pingColor + '44' }}>
                {pingMs}ms
              </div>
            )}
          </div>
        </div>
      </header>

      {/* ── MAIN GRID ────────────────────────────────────────────────────────── */}
      <div className="flex-1 min-h-0 grid gap-2 p-2"
           style={{ gridTemplateColumns: '1fr 1.4fr 1fr' }}>

        {/* ── COL 1: Radar + Edge Meters ─── */}
        <div className="flex flex-col gap-2 min-h-0">

          <div className="neon-card rounded p-2 flex flex-col gap-1">
            <div className="flex justify-between items-center">
              <span className="text-[9px] text-[#003311] tracking-widest" style={{ fontFamily: 'Orbitron' }}>
                MARKET RADAR
              </span>
              <span className="text-[8px] text-[#002211]">{activeCity}</span>
            </div>
            <Radar forecasts={fcList} activeCity={activeCity} scanning={scanning} />
          </div>

          <div className="neon-card rounded p-2 flex-1 overflow-y-auto">
            <div className="text-[9px] text-[#003311] tracking-widest mb-2" style={{ fontFamily: 'Orbitron' }}>
              EDGE ANALYSIS
            </div>
            <EdgeMeters forecasts={fcList} activeCity={activeCity} />
          </div>
        </div>

        {/* ── COL 2: P&L Chart + Guardrails ─── */}
        <div className="flex flex-col gap-2 min-h-0">

          <div className="neon-card rounded p-2 flex-1 min-h-0">
            <div className="text-[9px] text-[#003311] tracking-widest mb-1" style={{ fontFamily: 'Orbitron' }}>
              CAPITAL CURVE
            </div>
            <div style={{ height: 'calc(100% - 20px)' }}>
              <PnlChart pnl={pnlSeries} summary={summary} />
            </div>
          </div>

          <div className="neon-card rounded p-2">
            <div className="text-[9px] text-[#003311] tracking-widest mb-2" style={{ fontFamily: 'Orbitron' }}>
              RISK GUARDRAILS
            </div>
            <Guardrails guardrails={guardrails} />
          </div>
        </div>

        {/* ── COL 3: Decision Log ─── */}
        <div className="neon-card rounded p-2 flex flex-col min-h-0">
          <div className="flex justify-between items-center mb-2">
            <span className="text-[9px] text-[#003311] tracking-widest" style={{ fontFamily: 'Orbitron' }}>
              DECISION LOG
            </span>
            <span className="text-[8px] text-[#002211] blink">■ LIVE</span>
          </div>
          <div className="flex-1 min-h-0">
            <DecisionLog entries={logEntries} />
          </div>
        </div>
      </div>

      {/* ── STATUS BAR ───────────────────────────────────────────────────────── */}
      <footer className="flex justify-between items-center px-4 py-1 border-t border-[#001a08] text-[8px] text-[#002211]"
              style={{ background: '#030803' }}>
        <span>WEATHERALPHA · KALSHI WEATHER MARKETS · DEMO MODE</span>
        <span>{new Date().toLocaleString()}</span>
        <span className="blink">■</span>
      </footer>
    </div>
  )
}
