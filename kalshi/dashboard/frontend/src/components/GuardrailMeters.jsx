import * as Progress from '@radix-ui/react-progress'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'

const CHECKS = [
  { key: 'daily_trades',       label: 'Daily Trades',    max: 10,  unit: '',  isDanger: false },
  { key: 'daily_pnl_usd',      label: 'Daily Loss',      max: 200, unit: '$', isDanger: true  },
  { key: 'consecutive_losses', label: 'Consec. Losses',  max: 5,   unit: '',  isDanger: false },
  { key: 'open_risk_usd',      label: 'Open Risk',       max: 500, unit: '$', isDanger: false },
]

function GuardrailBar({ label, value, max, unit, isDanger }) {
  const raw  = value ?? 0
  const abs  = Math.abs(raw)
  const pct  = Math.min(100, (abs / max) * 100)
  const hot  = pct >= 80
  const warn = pct >= 60

  const color = hot  ? '#ff5e7d'
              : warn ? '#fbbf24'
              :        '#26de81'

  const trackBg = hot  ? 'rgba(255, 94, 125, 0.1)'
                : warn ? 'rgba(251, 191, 36, 0.1)'
                :        'rgba(38, 222, 129, 0.08)'

  const displayVal = isDanger ? abs.toFixed(0) : raw

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span
          className="text-[11px] font-medium"
          style={{ color: hot ? '#ff5e7d' : '#94a3b8' }}
        >
          {label}
        </span>
        <span className="stat-value text-[11px] font-semibold" style={{ color }}>
          {unit}{displayVal != null ? displayVal : '—'}
          <span className="text-text-muted font-normal ml-1">
            / {unit}{max}
          </span>
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
            transition: 'width 0.7s cubic-bezier(0.4, 0, 0.2, 1)',
            boxShadow: hot ? `0 0 8px ${color}` : warn ? `0 0 4px ${color}` : 'none',
          }}
        />
      </Progress.Root>

      {/* Threshold tick marks */}
      <div className="relative h-1.5">
        <div
          className="absolute top-0 w-px h-1.5"
          style={{ left: '60%', background: 'rgba(251,191,36,0.5)' }}
        />
        <div
          className="absolute top-0 w-px h-1.5"
          style={{ left: '80%', background: 'rgba(255,94,125,0.5)' }}
        />
      </div>
    </div>
  )
}

export default function GuardrailMeters({ guardrails }) {
  const g = guardrails ?? {}
  const halted = g.trading_halted === true
  const inWindow = g.trade_window_open !== false

  return (
    <div className="flex flex-col gap-4">

      {/* Halted banner */}
      {halted && (
        <div
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold"
          style={{
            background: 'rgba(255, 94, 125, 0.12)',
            border: '1px solid rgba(255, 94, 125, 0.35)',
            color: '#ff5e7d',
          }}
        >
          <AlertTriangle size={14} />
          TRADING HALTED — guardrail limit reached
        </div>
      )}

      {/* Progress bars */}
      <div className="flex flex-col gap-3">
        {CHECKS.map(c => (
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

      {/* Status row */}
      <div
        className="flex items-center justify-between pt-2 border-t text-[11px]"
        style={{ borderColor: '#2a2a3a' }}
      >
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
              background: inWindow ? '#26de81' : '#475569',
              boxShadow: inWindow ? '0 0 4px #26de81' : 'none',
            }}
          />
          <span className="text-text-muted">
            {inWindow ? 'Trade window open' : 'Outside trade window'}
          </span>
        </div>
      </div>
    </div>
  )
}
