import { useApi, api, fmt } from '../api.js'
import { Check, X, AlertTriangle } from 'lucide-react'

function GateRow({ name, ok, msg }) {
  return (
    <div className="flex items-start gap-2 py-1">
      {ok ? <Check size={16} className="text-profit mt-0.5 flex-shrink-0" /> :
            <X size={16} className="text-loss mt-0.5 flex-shrink-0" />}
      <div className="flex-1 min-w-0">
        <div className="text-sm text-text-primary">{name}</div>
        <div className="text-xs text-text-secondary truncate">{msg || '—'}</div>
      </div>
    </div>
  )
}

export default function Live() {
  const { data, error } = useApi(api.live, [], 15000)  // refresh every 15s on Live tab

  if (error) return <div className="text-loss text-sm">Error: {error}</div>
  if (!data) return <div className="text-text-muted text-sm">Loading…</div>

  const arm = data.arm_status || {}
  const checks = arm.checks || {}
  const warnings = arm.warnings || {}
  const positions = data.open_positions || []

  return (
    <div className="space-y-4 mt-4">
      {/* Arm status panel */}
      <section className="gradient-card border border-border rounded-lg p-4">
        <h2 className="text-lg font-semibold mb-3">Arm Status — {arm.date || '—'}</h2>
        {data.armed_today ? (
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-profit/15 text-profit text-sm font-medium mb-3">
            <Check size={14} /> ARMED · source: {arm.source || '—'}
          </div>
        ) : (
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-loss/15 text-loss text-sm font-medium mb-3">
            <X size={14} /> NOT ARMED
            {arm.blocker && <span className="text-text-secondary text-xs">— {arm.blocker}</span>}
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">
          <div>
            <div className="text-xs uppercase tracking-wider text-text-muted mb-1">Hard checks</div>
            {Object.entries(checks).map(([k, v]) => (
              <GateRow key={k} name={k.replace('_', '/')} ok={v?.ok} msg={v?.msg} />
            ))}
          </div>
          <div>
            <div className="text-xs uppercase tracking-wider text-text-muted mb-1">Warnings</div>
            {Object.entries(warnings).map(([k, msg]) => (
              <div key={k} className="flex items-start gap-2 py-1">
                {msg ? <AlertTriangle size={16} className="text-warn mt-0.5 flex-shrink-0" /> :
                       <Check size={16} className="text-profit/60 mt-0.5 flex-shrink-0" />}
                <div className="flex-1">
                  <div className="text-sm text-text-primary">{k}</div>
                  <div className="text-xs text-text-secondary">{msg || 'ok'}</div>
                </div>
              </div>
            ))}
          </div>
          <div>
            <div className="text-xs uppercase tracking-wider text-text-muted mb-1">Armed at</div>
            <div className="text-sm font-mono text-text-primary">{fmt.time(arm.armed_at)}</div>
          </div>
        </div>
      </section>

      {/* Open positions */}
      <section className="gradient-card border border-border rounded-lg p-4">
        <h2 className="text-lg font-semibold mb-3">
          Open Positions {positions.length > 0 && <span className="text-accent text-sm font-normal">({positions.length})</span>}
        </h2>
        {positions.length === 0 ? (
          <div className="text-text-muted text-sm">No open positions — bot is flat.</div>
        ) : (
          <div className="space-y-2">
            {positions.map((p) => {
              const isLong = p.direction === 'LONG'
              return (
                <div key={p.trade_id} className="border border-border-light rounded p-3">
                  <div className="flex items-center gap-3 mb-1">
                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${isLong ? 'bg-profit/20 text-profit' : 'bg-loss/20 text-loss'}`}>
                      {p.direction}
                    </span>
                    <span className="font-mono text-sm text-text-primary">#{p.trade_id}</span>
                    <span className="text-xs text-text-muted">opened {fmt.time(p.opened_at)}</span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                    <div><span className="text-text-muted">Entry:</span> <span className="font-mono">{p.entry?.toFixed(2)}</span></div>
                    <div><span className="text-text-muted">Stop:</span> <span className="font-mono text-loss">{p.stop?.toFixed(2)}</span></div>
                    <div><span className="text-text-muted">T1:</span> <span className="font-mono">{p.target_1?.toFixed(2)}</span></div>
                    <div><span className="text-text-muted">T2:</span> <span className="font-mono text-profit">{p.target_2?.toFixed(2)}</span></div>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
                    {p.t1_hit && <span className="px-1.5 py-0.5 rounded bg-profit/15 text-profit">T1 hit</span>}
                    {p.pre_t1_be_armed && <span className="px-1.5 py-0.5 rounded bg-accent/15 text-accent">Pre-T1 BE</span>}
                    {p.stall_locked && <span className="px-1.5 py-0.5 rounded bg-warn/15 text-warn">Stall lock</span>}
                    {p.virtual_stop !== null && p.virtual_stop !== undefined && (
                      <span className="px-1.5 py-0.5 rounded bg-bg-panel border border-border">
                        vstop {p.virtual_stop?.toFixed(2)}
                      </span>
                    )}
                    {p.mfe_price !== null && p.mfe_price !== undefined && (
                      <span className="px-1.5 py-0.5 rounded bg-bg-panel border border-border">
                        MFE {p.mfe_price?.toFixed(2)}
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}
