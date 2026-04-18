import { useState, useEffect, useRef, useCallback } from 'react'
import { ShieldAlert, Activity, Target, Layers, Database, Zap, TrendingUp, MapPin, FileText } from 'lucide-react'

import Header           from './components/Header'
import EquityChart      from './components/EquityChart'
import TradesTable      from './components/TradesTable'
import SignalsTable     from './components/SignalsTable'
import CalibrationPanel from './components/CalibrationPanel'
import GuardrailMeters  from './components/GuardrailMeters'
import DecisionLog      from './components/DecisionLog'
import PositionsPanel   from './components/PositionsPanel'
import CityBoard        from './components/CityBoard'

const SCAN_PERIOD = 60

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

let _lid = 0
const mkEntry = (type, msg) => ({ id: ++_lid, ts: new Date().toISOString(), type, msg })

function HeroCard({ label, value, sub, color, glow, big }) {
  return (
    <div
      className="flex flex-col px-4 py-3 rounded-xl shrink-0 relative overflow-hidden"
      style={{
        background: 'linear-gradient(135deg, #13131d 0%, #1a1a26 100%)',
        border: `1px solid ${glow ? `${color}55` : '#2a2a3a'}`,
        boxShadow: glow ? `0 0 20px ${color}22, inset 0 0 20px ${color}08` : 'none',
        minWidth: big ? 180 : 120,
      }}
    >
      <div
        className="text-[9px] font-bold tracking-[0.12em]"
        style={{ color: '#64748b' }}
      >
        {label}
      </div>
      <div
        className="stat-value font-bold leading-none mt-1"
        style={{ fontSize: big ? 28 : 20, color: color ?? '#f8fafc', letterSpacing: '-0.02em' }}
      >
        {value}
      </div>
      {sub && (
        <div className="text-[10px] mt-1" style={{ color: '#94a3b8' }}>
          {sub}
        </div>
      )}
    </div>
  )
}

function SectionHeader({ icon: Icon, title, right, color = '#818cf8' }) {
  return (
    <div className="flex items-center gap-2 mb-2 shrink-0">
      <Icon size={13} style={{ color }} />
      <span
        className="text-[10px] font-bold tracking-[0.12em]"
        style={{ color: '#94a3b8' }}
      >
        {title}
      </span>
      {right && <div className="ml-auto flex items-center gap-1.5">{right}</div>}
    </div>
  )
}

function LiveBadge() {
  return (
    <>
      <div
        className="w-1.5 h-1.5 rounded-full animate-pulse-glow"
        style={{ background: '#26de81' }}
      />
      <span className="text-[9px] font-bold tracking-wider" style={{ color: '#26de81' }}>
        LIVE
      </span>
    </>
  )
}

export default function App() {
  const { data: health      } = useApi('/api/health',            10000)
  const { data: statusData  } = useApi('/api/status',             8000)
  const { data: summary     } = useApi('/api/summary',            6000)
  const { data: today       } = useApi('/api/today',              6000)
  const { data: byCity      } = useApi('/api/by-city',            8000)
  const { data: guardrails  } = useApi('/api/guardrails',         5000)
  const { data: equityCurve } = useApi('/api/equity-curve',       8000)
  const { data: tradesData  } = useApi('/api/trades/verified',    5000)
  const { data: signalsData } = useApi('/api/signals',            8000)
  const { data: calibration } = useApi('/api/calibration',       15000)
  const { data: logData     } = useApi('/api/decision-log',       3000)
  const { data: posData     } = useApi('/api/positions',          5000)

  const [scanning,  setScanning]  = useState(false)
  const [countdown, setCountdown] = useState(SCAN_PERIOD)
  const [pingMs,    setPingMs]    = useState(null)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [activeTab, setActiveTab] = useState('trading')

  const [localLog, setLocalLog] = useState([
    mkEntry('system', 'WeatherAlpha War Room online'),
  ])
  const addLog = useCallback((type, msg) => {
    setLocalLog(prev => [mkEntry(type, msg), ...prev].slice(0, 200))
  }, [])

  const nextScanRef = useRef(Date.now() + SCAN_PERIOD * 1000)
  const scanningRef = useRef(false)

  const logEntries = logData?.entries
    ? logData.entries.map((e, i) => ({ ...e, id: e.id ?? `be-${i}`, ts: e.ts ?? e.timestamp }))
    : localLog

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

  const prevConnRef = useRef(null)
  useEffect(() => {
    const connected = health?.kalshi_connected
    if (connected === prevConnRef.current) return
    prevConnRef.current = connected
    if (connected === true)  addLog('connect', 'Kalshi API connected')
    if (connected === false) addLog('error',   'Kalshi API disconnected')
  }, [health, addLog])

  // Derived
  const kalshiOk        = health?.kalshi_connected === true
  const capital         = statusData?.capital_usd ?? 80
  const lifetimePnl     = summary?.total_pnl_usd ?? 0
  const startingCapital = capital - lifetimePnl
  const pctGain         = startingCapital > 0 ? (lifetimePnl / startingCapital) * 100 : 0
  const todayPnl        = today?.pnl_today_usd ?? 0
  const winRate         = summary?.win_rate ?? null
  const wins            = summary?.wins ?? 0
  const losses          = summary?.losses ?? 0
  const trades          = summary?.total_trades ?? 0
  const openRisk        = summary?.open_risk_usd ?? 0
  const unrealized      = posData?.total_unrealized_pnl ?? 0
  const lifePos         = lifetimePnl >= 0
  const todayPos        = todayPnl >= 0
  const unrealPos       = unrealized >= 0

  const tradesVerified = Array.isArray(tradesData) ? tradesData : []
  const signals        = Array.isArray(signalsData) ? signalsData : []
  const cities         = Array.isArray(byCity) ? byCity : []

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: '#0a0a10' }}>

      <Header
        lifetimePnl={lifetimePnl}
        todayPnl={todayPnl}
        kalshiOk={kalshiOk}
        pingMs={pingMs}
        countdown={countdown}
        scanning={scanning}
        onScan={runScan}
        mobileMenuOpen={mobileMenuOpen}
        onToggleMobile={() => setMobileMenuOpen(v => !v)}
      />

      {/* HERO STRIP */}
      <div
        className="flex items-stretch gap-2 px-3 py-3 border-b overflow-x-auto shrink-0"
        style={{ borderColor: '#2a2a3a', scrollbarWidth: 'thin' }}
      >
        <HeroCard
          label="BANKROLL"
          value={`$${capital.toFixed(2)}`}
          sub={`from $${startingCapital.toFixed(0)} start`}
          color="#f8fafc"
          big
        />
        <HeroCard
          label="LIFETIME P&L"
          value={`${lifePos ? '+' : '−'}$${Math.abs(lifetimePnl).toFixed(2)}`}
          sub={`${pctGain >= 0 ? '+' : ''}${pctGain.toFixed(1)}% return`}
          color={lifePos ? '#26de81' : '#ff5e7d'}
          glow
          big
        />
        <HeroCard
          label="TODAY"
          value={`${todayPos ? '+' : '−'}$${Math.abs(todayPnl).toFixed(2)}`}
          sub={today ? `${today.trades_today} new · ${today.wins_today}W/${today.losses_today}L` : '—'}
          color={todayPnl === 0 ? '#94a3b8' : (todayPos ? '#26de81' : '#ff5e7d')}
        />
        <HeroCard
          label="UNREALIZED"
          value={`${unrealPos ? '+' : '−'}$${Math.abs(unrealized).toFixed(2)}`}
          sub={`${posData?.positions?.length ?? 0} open · $${openRisk.toFixed(0)} at risk`}
          color={unrealized === 0 ? '#94a3b8' : (unrealPos ? '#26de81' : '#ff5e7d')}
        />
        <HeroCard
          label="WIN RATE"
          value={winRate != null ? `${(winRate * 100).toFixed(0)}%` : '—'}
          sub={`${wins}W / ${losses}L · ${trades} total`}
          color={winRate == null ? '#94a3b8' : winRate >= 0.5 ? '#26de81' : '#fbbf24'}
        />
        <HeroCard
          label="KALSHI FEED"
          value={kalshiOk ? 'LIVE' : 'DOWN'}
          sub={pingMs ? `${pingMs}ms roundtrip` : 'no ping'}
          color={kalshiOk ? '#26de81' : '#ff5e7d'}
          glow={kalshiOk}
        />
      </div>

      {/* MAIN GRID */}
      <div className="flex-1 min-h-0 overflow-hidden terminal-grid">

        {/* LEFT: Cities + Signals + Guardrails */}
        <div
          className={`flex flex-col gap-3 p-3 overflow-y-auto min-h-0 border-r ${activeTab !== 'signals' ? 'hidden md:flex' : 'flex'}`}
          style={{ borderColor: '#2a2a3a' }}
        >
          <div className="card p-3">
            <SectionHeader icon={MapPin} title="CITY SCOREBOARD" right={<LiveBadge />} />
            <CityBoard cities={cities} />
          </div>

          <div className="card p-3 flex flex-col" style={{ minHeight: 220 }}>
            <SectionHeader
              icon={Activity}
              title="LIVE SIGNALS"
              right={<span className="text-[10px] font-semibold" style={{ color: '#818cf8' }}>
                {signals.filter(s => s.actionable).length} actionable
              </span>}
            />
            <div className="flex-1 min-h-0">
              <SignalsTable signals={signals} />
            </div>
          </div>

          <div className="card p-3">
            <SectionHeader icon={ShieldAlert} title="RISK GUARDRAILS" />
            <GuardrailMeters guardrails={guardrails} />
          </div>

          <div className="card p-3">
            <SectionHeader icon={Target} title="MODEL CALIBRATION" />
            <CalibrationPanel calibration={calibration} />
          </div>
        </div>

        {/* CENTER: Positions + Chart + Trades */}
        <div className={`flex flex-col gap-3 p-3 min-h-0 overflow-y-auto ${activeTab !== 'trading' ? 'hidden md:flex' : 'flex'}`}>

          <div className="card p-4 shrink-0" style={{ height: 280 }}>
            <div className="flex items-center justify-between mb-2 shrink-0">
              <div className="flex items-center gap-2">
                <TrendingUp size={13} style={{ color: '#26de81' }} />
                <span className="text-[10px] font-bold tracking-[0.12em]" style={{ color: '#94a3b8' }}>
                  EQUITY CURVE
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[9px] font-semibold tracking-wider" style={{ color: '#64748b' }}>
                  FROM ${startingCapital.toFixed(0)}
                </span>
                <span
                  className="stat-value text-lg font-bold"
                  style={{ color: lifePos ? '#26de81' : '#ff5e7d' }}
                >
                  {lifePos ? '+' : '−'}${Math.abs(lifetimePnl).toFixed(2)}
                </span>
              </div>
            </div>
            <div style={{ height: 'calc(100% - 32px)' }}>
              <EquityChart curve={equityCurve} startingCapital={startingCapital} />
            </div>
          </div>

          <div className="card flex flex-col shrink-0" style={{ minHeight: 240, maxHeight: 400 }}>
            <PositionsPanel
              positions={posData?.positions}
              totalUnrealizedPnl={posData?.total_unrealized_pnl}
            />
          </div>

          <div className="card p-4 shrink-0" style={{ minHeight: 200 }}>
            <SectionHeader
              icon={Database}
              title="TRADE LOG"
              right={
                <>
                  <span
                    className="text-[9px] font-semibold px-1.5 py-0.5 rounded"
                    style={{ background: 'rgba(129,140,248,0.12)', color: '#818cf8', border: '1px solid rgba(129,140,248,0.25)' }}
                  >
                    SQLite Verified
                  </span>
                  <span className="text-[9px]" style={{ color: '#64748b' }}>
                    {tradesVerified.length} records
                  </span>
                </>
              }
            />
            <TradesTable trades={tradesVerified} />
          </div>
        </div>

        {/* RIGHT: Decision Log */}
        <div
          className={`flex flex-col p-3 min-h-0 overflow-hidden border-l ${activeTab !== 'log' ? 'hidden md:flex' : 'flex'}`}
          style={{ borderColor: '#2a2a3a' }}
        >
          <div className="card p-3 flex flex-col flex-1 min-h-0">
            <SectionHeader icon={FileText} title="DECISION FEED" right={<LiveBadge />} />
            <div className="flex-1 min-h-0">
              <DecisionLog entries={logEntries} />
            </div>
          </div>
        </div>
      </div>

      {/* Mobile bottom tab bar */}
      <div
        className="md:hidden flex items-center border-t shrink-0"
        style={{ borderColor: '#2a2a3a', background: '#0a0a10' }}
      >
        {[
          { id: 'signals', label: 'CITIES',  Icon: MapPin   },
          { id: 'trading', label: 'TRADING', Icon: Target   },
          { id: 'log',     label: 'FEED',    Icon: FileText },
        ].map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className="flex-1 flex flex-col items-center gap-0.5 py-2.5"
            style={{
              color: activeTab === id ? '#818cf8' : '#475569',
              background: 'none',
              border: 'none',
              borderTop: activeTab === id ? '2px solid #818cf8' : '2px solid transparent',
              cursor: 'pointer',
            }}
          >
            <Icon size={16} />
            <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.06em' }}>{label}</span>
          </button>
        ))}
        <button
          onClick={runScan}
          disabled={scanning}
          className="flex flex-col items-center gap-0.5 py-2.5 px-4"
          style={{
            color: scanning ? '#475569' : '#26de81',
            background: 'none',
            border: 'none',
            borderTop: '2px solid transparent',
            cursor: scanning ? 'not-allowed' : 'pointer',
          }}
        >
          <Zap size={16} />
          <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.06em' }}>
            {scanning ? '...' : `${String(countdown).padStart(2,'0')}s`}
          </span>
        </button>
      </div>

      <footer
        className="hidden md:flex items-center justify-between px-4 py-1.5 border-t shrink-0 text-[10px]"
        style={{ borderColor: '#2a2a3a', background: '#0a0a10', color: '#64748b' }}
      >
        <span>WeatherAlpha War Room · Kalshi Weather Markets · Paper Mode</span>
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
