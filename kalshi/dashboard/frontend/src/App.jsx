import { useState, useEffect, useRef, useCallback } from 'react'
import { motion } from 'framer-motion'
import { ShieldAlert, Activity, Target, Layers, Database } from 'lucide-react'

import Header           from './components/Header'
import EquityChart      from './components/EquityChart'
import TradesTable      from './components/TradesTable'
import SignalsTable     from './components/SignalsTable'
import CalibrationPanel from './components/CalibrationPanel'
import GuardrailMeters  from './components/GuardrailMeters'
import DecisionLog      from './components/DecisionLog'

const SCAN_PERIOD = 60 // seconds

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
      className="flex flex-col gap-0.5 px-3 py-2 rounded-lg shrink-0"
      style={{ background: '#1a1a24', border: '1px solid #2a2a3a' }}
    >
      <div className="text-[9px] font-semibold text-text-muted" style={{ letterSpacing: '0.06em' }}>
        {label}
      </div>
      <div className="stat-value font-bold" style={{ fontSize: 16, color: color ?? '#f8fafc' }}>
        {value}
      </div>
      {sub && <div className="text-[9px] text-text-muted">{sub}</div>}
    </div>
  )
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  // API polling
  const { data: health       } = useApi('/api/health',            10000)
  const { data: summary      } = useApi('/api/summary',            8000)
  const { data: guardrails   } = useApi('/api/guardrails',         5000)
  const { data: equityCurve  } = useApi('/api/equity-curve',       8000)
  const { data: tradesData   } = useApi('/api/trades/verified',    5000)
  const { data: signalsData  } = useApi('/api/signals',            8000)
  const { data: calibration  } = useApi('/api/calibration',       15000)
  const { data: logData      } = useApi('/api/decision-log',       3000)

  // UI state
  const [scanning,  setScanning]  = useState(false)
  const [countdown, setCountdown] = useState(SCAN_PERIOD)
  const [pingMs,    setPingMs]    = useState(null)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  // Local fallback log
  const [localLog, setLocalLog] = useState([
    mkEntry('system', 'WeatherAlpha trading terminal initialised'),
    mkEntry('connect', 'Connecting to Kalshi API...'),
  ])
  const addLog = useCallback((type, msg) => {
    setLocalLog(prev => [mkEntry(type, msg), ...prev].slice(0, 200))
  }, [])

  const nextScanRef = useRef(Date.now() + SCAN_PERIOD * 1000)
  const scanningRef = useRef(false)

  // Merge backend + local log
  const logEntries = logData?.entries
    ? logData.entries.map((e, i) => ({
        ...e,
        id: e.id ?? `be-${i}`,
        ts: e.ts ?? e.timestamp,
      }))
    : localLog

  // ── Scan ──────────────────────────────────────────────────────────────────────
  const runScan = useCallback(async () => {
    if (scanningRef.current) return
    scanningRef.current = true
    setScanning(true)
    addLog('scan', 'Initiating market scan across all cities...')
    try {
      const r = await fetch('/api/scan', { method: 'POST' })
      const d = await r.json()
      const actions = d.actions ?? []
      if (actions.length === 0) {
        addLog('skip', 'Scan complete — no tradeable edges found')
      } else {
        actions.forEach(a => {
          if (a.action === 'traded') {
            addLog('trade', `${a.city} — ${a.side} ${a.contracts}ct @ ${a.price}c | edge ${((a.edge ?? 0) * 100).toFixed(1)}%`)
          } else if (a.action === 'blocked') {
            const reasons = Array.isArray(a.reasons) ? a.reasons.join('; ') : (a.reason ?? 'guardrail')
            addLog('block', `${a.city} — blocked: ${reasons}`)
          } else if (a.action === 'error') {
            addLog('error', `${a.city} — ${a.error}`)
          } else {
            addLog('skip', `${a.city} — ${a.action}`)
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
  const kalshiOk = health?.kalshi_connected === true
  const base     = 1000
  const pnlUsd   = summary?.total_pnl_usd ?? 0
  const capital   = base + pnlUsd
  const winRate   = summary?.win_rate ?? null
  const trades    = summary?.total_trades ?? 0
  const openRisk  = summary?.open_risk_usd ?? 0
  const pnlPos    = pnlUsd >= 0

  const tradesVerified = Array.isArray(tradesData) ? tradesData : []
  const signals = Array.isArray(signalsData) ? signalsData : []

  // ── Render ────────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: '#0f0f14' }}>

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
        className="flex items-center gap-2 px-3 py-2 border-b overflow-x-auto shrink-0"
        style={{ borderColor: '#2a2a3a', scrollbarWidth: 'none' }}
      >
        <StatCard label="CAPITAL" value={`$${capital.toFixed(2)}`} />
        <StatCard
          label="TOTAL P&L"
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
          <StatCard label="OPEN RISK" value={`$${openRisk.toFixed(0)}`} color="#fbbf24" />
        )}
        <StatCard
          label="KALSHI"
          value={kalshiOk ? 'LIVE' : 'DOWN'}
          color={kalshiOk ? '#26de81' : '#ff5e7d'}
          sub={pingMs ? `${pingMs}ms` : undefined}
        />

        {/* SQLite badge */}
        <div
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg shrink-0 ml-auto"
          style={{ background: '#1a1a24', border: '1px solid #2a2a3a' }}
        >
          <Database size={11} style={{ color: '#818cf8' }} />
          <span className="text-[9px] font-semibold" style={{ color: '#818cf8', letterSpacing: '0.04em' }}>
            SQLite VERIFIED
          </span>
        </div>
      </div>

      {/* 3-column layout */}
      <div className="flex-1 min-h-0 overflow-hidden terminal-grid">

        {/* ── LEFT COLUMN: Signals + Calibration + Guardrails ── */}
        <div className="flex flex-col gap-3 p-3 overflow-y-auto min-h-0 border-r" style={{ borderColor: '#2a2a3a' }}>

          {/* Signals */}
          <div className="card p-3 flex flex-col" style={{ minHeight: 260 }}>
            <div className="flex items-center gap-2 mb-2">
              <Activity size={13} style={{ color: '#818cf8' }} />
              <span className="text-[10px] font-semibold text-text-muted" style={{ letterSpacing: '0.08em' }}>
                SIGNALS
              </span>
              <span className="text-[9px] stat-value text-text-muted ml-auto">
                {signals.filter(s => s.actionable).length} live
              </span>
            </div>
            <div className="flex-1 min-h-0">
              <SignalsTable signals={signals} />
            </div>
          </div>

          {/* Calibration */}
          <div className="card p-3">
            <CalibrationPanel calibration={calibration} />
          </div>

          {/* Guardrails */}
          <div className="card p-3">
            <div className="flex items-center gap-2 mb-3">
              <ShieldAlert size={13} style={{ color: '#818cf8' }} />
              <span className="text-[10px] font-semibold text-text-muted" style={{ letterSpacing: '0.08em' }}>
                RISK GUARDRAILS
              </span>
            </div>
            <GuardrailMeters guardrails={guardrails} />
          </div>
        </div>

        {/* ── CENTER COLUMN: Equity Chart + Trades Table ── */}
        <div className="flex flex-col gap-3 p-3 min-h-0 overflow-hidden">

          {/* Equity Chart */}
          <div className="card p-4 shrink-0" style={{ height: 280 }}>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Layers size={13} style={{ color: '#818cf8' }} />
                <span className="text-[10px] font-semibold text-text-muted" style={{ letterSpacing: '0.08em' }}>
                  EQUITY CURVE
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="stat-value text-sm font-bold" style={{ color: pnlPos ? '#26de81' : '#ff5e7d' }}>
                  {pnlPos ? '+' : ''}${pnlUsd.toFixed(2)}
                </span>
              </div>
            </div>
            <div style={{ height: 'calc(100% - 32px)' }}>
              <EquityChart curve={equityCurve} startingCapital={base} />
            </div>
          </div>

          {/* Trades Table */}
          <div className="card p-4 flex-1 min-h-0 flex flex-col">
            <div className="flex items-center justify-between mb-2 shrink-0">
              <div className="flex items-center gap-2">
                <Database size={13} style={{ color: '#818cf8' }} />
                <span className="text-[10px] font-semibold text-text-muted" style={{ letterSpacing: '0.08em' }}>
                  TRADE LOG
                </span>
                <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded"
                  style={{ background: 'rgba(129,140,248,0.12)', color: '#818cf8', border: '1px solid rgba(129,140,248,0.25)' }}>
                  SQLite Backed
                </span>
              </div>
              <span className="stat-value text-[10px] text-text-muted">
                {tradesVerified.length} records
              </span>
            </div>
            <div className="flex-1 min-h-0 overflow-hidden">
              <TradesTable trades={tradesVerified} />
            </div>
          </div>
        </div>

        {/* ── RIGHT COLUMN: Decision Log ── */}
        <div className="flex flex-col p-3 min-h-0 overflow-hidden border-l" style={{ borderColor: '#2a2a3a' }}>
          <div className="card p-3 flex flex-col flex-1 min-h-0">
            <div className="flex items-center justify-between mb-2 shrink-0">
              <span className="text-[10px] font-semibold text-text-muted" style={{ letterSpacing: '0.08em' }}>
                DECISION LOG
              </span>
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full animate-pulse-glow" style={{ background: '#26de81' }} />
                <span className="text-[10px] font-medium" style={{ color: '#26de81' }}>LIVE</span>
              </div>
            </div>
            <div className="flex-1 min-h-0">
              <DecisionLog entries={logEntries} />
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer
        className="flex items-center justify-between px-4 py-1.5 border-t shrink-0 text-[10px] text-text-muted"
        style={{ borderColor: '#2a2a3a', background: '#0f0f14' }}
      >
        <span>WeatherAlpha Trading Terminal | Kalshi Weather Markets | Paper Mode</span>
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
