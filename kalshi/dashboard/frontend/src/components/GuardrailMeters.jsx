import { useState } from 'react'
import * as Progress from '@radix-ui/react-progress'
import { AlertTriangle, CheckCircle2, Clock, Unlock } from 'lucide-react'

function GuardrailBar({ label, value, max, unit, isDanger }) {
  const raw  = value ?? 0
  const abs  = Math.abs(raw)
  const pct  = Math.min(100, max > 0 ? (abs / max) * 100 : 0)
  const hot  = pct >= 80
  const warn = pct >= 60

  const color  = hot ? '#ff5e7d' : warn ? '#fbbf24' : '#26de81'
  const trackBg = hot  ? 'rgba(255,94,125,0.1)'
                : warn ? 'rgba(251,191,36,0.1)'
                :        'rgba(38,222,129,0.08)'

  const displayVal = isDanger ? abs.toFixed(0) : raw

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] font-medium" style={{ color: hot ? '#ff5e7d' : '#94a3b8' }}>
          {label}
        </span>
        <span className="stat-value text-[11px] font-semibold" style={{ color }}>
          {unit}{displayVal != null ? displayVal : '—'}
          <span className="text-text-muted font-normal ml-1">/ {unit}{max}</span>
        </span>
      </div>

      <Progress.Root
        value={pct}
        className="relative overflow-hidden rounded-full"
        style={{
          height: 6,
          background: trackBg,
          border: `1px solid ${hot ? 'rgba(255,94,125,0.2)' : warn ? 'rgba(251,191,36,0.15)' : 'rgba(38,222,129,0.1)'}`,
        }}
      >
        <Progress.Indicator
          style={{
            height: '100%',
            width: `${pct}%`,
            background: color,
            borderRadius: 'inherit',
            transition: 'width 0.7s cubic-bezier(0.4,0,0.2,1)',
            boxShadow: hot ? `0 0 8px ${color}` : warn ? `0 0 4px ${color}` : 'none',
          }}
        />
      </Progress.Root>

      <div className="relative h-1.5">
        <div className="absolute top-0 w-px h-1.5" style={{ left: '60%', background: 'rgba(251,191,36,0.5)' }} />
        <div className="absolute top-0 w-px h-1.5" style={{ left: '80%', background: 'rgba(255,94,125,0.5)' }} />
      </div>
    </div>
  )
}

export default function GuardrailMeters({ guardrails }) {
  const g = guardrails ?? {}
  const halted   = g.halted === true
  const inWindow = g.trade_window_active === true
  const override = g.window_override === true
  const [toggling, setToggling] = useState(false)

  async function toggleOverride() {
    setToggling(true)
    try {
      await fetch('/api/guardrails/window-override', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !override }),
      })
    } finally {
      setToggling(false)
    }
  }

  const checks = [
    { key: 'daily_trades',        label: 'Daily Trades',   max: g.max_daily_trades      ?? 5,   unit: '',  isDanger: false },
    { key: 'daily_pnl_usd',       label: 'Daily Loss',     max: g.max_daily_loss        ?? 150, unit: '$', isDanger: true  },
    { key: 'consecutive_losses',  label: 'Consec. Losses', max: g.max_consecutive_losses ?? 3,   unit: '',  isDanger: false },
    { key: 'capital_at_risk_usd', label: 'Capital at Risk',max: g.max_capital_at_risk   ?? 400, unit: '$', isDanger: false },
  ]

  return (
    <div className="flex flex-col gap-4">
      {halted && (
        <div
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold"
          style={{ background: 'rgba(255,94,125,0.12)', border: '1px solid rgba(255,94,125,0.35)', color: '#ff5e7d' }}
        >
          <AlertTriangle size={14} />
          TRADING HALTED — {g.halt_reason ?? 'guardrail limit reached'}
        </div>
      )}

      <div className="flex flex-col gap-3">
        {checks.map(c => (
          <GuardrailBar
            key={c.key}
            label={c.label}
            value={g[c.key] ?? 0}
            max={c.max}
            unit={c.unit}
            isDanger={c.isDanger}
          />
        ))}
      </div>

      <div
        className="flex flex-col gap-2 pt-2 border-t"
        style={{ borderColor: '#2a2a3a' }}
      >
        {/* Status row */}
        <div className="flex items-center justify-between text-[11px]">
          <div className="flex items-center gap-1.5">
            {halted ? (
              <AlertTriangle size={12} style={{ color: '#ff5e7d' }} />
            ) : (
              <CheckCircle2 size={12} style={{ color: '#26de81' }} />
            )}
            <span style={{ color: halted ? '#ff5e7d' : '#26de81', fontWeight: 600 }}>
              {halted ? 'HALTED' : 'ACTIVE'}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <div
              className="w-1.5 h-1.5 rounded-full"
              style={{
                background: (inWindow || override) ? '#26de81' : '#475569',
                boxShadow: (inWindow || override) ? '0 0 4px #26de81' : 'none',
              }}
            />
            <span className="text-text-muted">
              {override ? 'Override active' : (g.trade_window_msg ?? (inWindow ? 'Trade window open' : 'Outside trade window'))}
            </span>
          </div>
        </div>

        {/* Trade window override button */}
        <button
          onClick={toggleOverride}
          disabled={toggling}
          className="flex items-center justify-center gap-1.5 w-full py-1.5 rounded-lg text-[11px] font-semibold transition-all"
          style={{
            background: override
              ? 'rgba(251,191,36,0.12)'
              : 'rgba(129,140,248,0.10)',
            color: override ? '#fbbf24' : '#818cf8',
            border: `1px solid ${override ? 'rgba(251,191,36,0.3)' : 'rgba(129,140,248,0.25)'}`,
            cursor: toggling ? 'wait' : 'pointer',
            opacity: toggling ? 0.6 : 1,
          }}
        >
          {override ? <Unlock size={11} /> : <Clock size={11} />}
          {override ? 'OVERRIDE ON — click to disable' : 'Override trade window (paper only)'}
        </button>
      </div>
    </div>
  )
}
