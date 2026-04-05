const CHECKS = [
  { key: 'daily_trades',       label: 'DAILY TRADES',   max: 10,   unit: '',  format: v => v },
  { key: 'daily_pnl_usd',      label: 'DAILY LOSS',     max: 200,  unit: '$', format: v => Math.abs(v).toFixed(0), danger: true },
  { key: 'consecutive_losses', label: 'CONSEC LOSSES',  max: 5,    unit: '',  format: v => v },
  { key: 'open_risk_usd',      label: 'OPEN RISK',      max: 500,  unit: '$', format: v => v?.toFixed(0) },
]

function GuardrailBar({ label, value, max, unit, danger }) {
  const raw   = value ?? 0
  const abs   = Math.abs(raw)
  const pct   = Math.min(100, (abs / max) * 100)
  const hot   = pct >= 80
  const warn  = pct >= 60

  const color  = hot  ? '#ff0040'
               : warn ? '#ffcc00'
               :        '#00ff41'

  return (
    <div className={`px-2 py-1.5 rounded border transition-all duration-300 ${
      hot ? 'red-card' : 'border-[#001a08]'
    }`}
         style={{ background: '#050505' }}>
      <div className="flex justify-between items-center mb-1">
        <span className="text-[9px]" style={{ color: hot ? '#ff0040' : '#004d18', fontFamily: 'Share Tech Mono' }}>
          {label}
        </span>
        <span className="text-[10px] font-bold" style={{ color, fontFamily: 'Orbitron' }}>
          {unit}{value != null ? (danger ? Math.abs(raw).toFixed(0) : raw) : '—'}
          <span className="text-[8px] ml-1" style={{ color: '#003311' }}>/ {unit}{max}</span>
        </span>
      </div>

      {/* Track */}
      <div className="w-full h-1.5 rounded overflow-hidden" style={{ background: '#010d03' }}>
        <div
          className={`h-full rounded transition-all duration-700 ease-out ${hot ? 'danger-pulse' : ''}`}
          style={{
            width: `${pct}%`,
            backgroundColor: color,
            boxShadow: hot  ? `0 0 8px ${color}, 0 0 16px ${color}` :
                       warn ? `0 0 4px ${color}` : 'none',
          }}
        />
      </div>

      {/* Tick marks at 60% and 80% */}
      <div className="relative h-0">
        <div className="absolute w-px h-2 bg-[#ffcc0060]" style={{ left: '60%', top: '-1px' }} />
        <div className="absolute w-px h-2 bg-[#ff004060]"  style={{ left: '80%', top: '-1px' }} />
      </div>
    </div>
  )
}

export default function Guardrails({ guardrails }) {
  const g = guardrails ?? {}

  return (
    <div className="space-y-1.5">
      {CHECKS.map(c => (
        <GuardrailBar
          key={c.key}
          label={c.label}
          value={g[c.key] ?? 0}
          max={c.max}
          unit={c.unit}
          danger={c.danger}
        />
      ))}

      {/* Status row */}
      <div className="flex justify-between items-center pt-1 text-[9px]" style={{ color: '#003311' }}>
        <span>GUARDRAIL STATUS</span>
        <span className={g.trading_halted ? 'text-[#ff0040]' : 'text-[#00ff41]'}>
          {g.trading_halted ? '⊘ HALTED' : '◉ ACTIVE'}
        </span>
      </div>
    </div>
  )
}
