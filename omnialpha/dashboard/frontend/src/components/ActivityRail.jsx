import { CheckCircle2, XCircle, Search, AlertCircle, Activity } from 'lucide-react'

const SECTOR_DOT = {
  crypto: '#fbbf24',
  sports: '#38bdf8',
  politics: '#ff5e7d',
  economics: '#26de81',
  weather: '#818cf8',
  other: '#94a3b8',
}

function Entry({ e }) {
  const dot = SECTOR_DOT[e.sector] || '#94a3b8'
  const ts = e.ts ? new Date(e.ts).toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', hour12: false,
  }) : ''

  let Icon = Activity
  let color = '#94a3b8'
  if (e.kind === 'win') { Icon = CheckCircle2; color = '#26de81' }
  else if (e.kind === 'loss') { Icon = XCircle; color = '#ff5e7d' }
  else if (e.kind === 'entry') { Icon = Search; color = '#fbbf24' }
  else if (e.kind === 'error') { Icon = AlertCircle; color = '#ff5e7d' }

  return (
    <div
      className="flex items-start gap-2 px-3 py-2 animate-fade-in-up"
      style={{ borderBottom: '1px solid #1a1a24' }}
    >
      <div
        className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0"
        style={{ background: dot }}
        title={e.sector}
      />
      <Icon size={12} style={{ color, marginTop: 3 }} className="shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 text-[11px]">
          <span className="font-mono" style={{ color: '#64748b', fontFamily: '"JetBrains Mono", monospace' }}>
            {ts}
          </span>
          {e.pnl_usd !== null && e.pnl_usd !== undefined && (
            <span className="font-mono font-bold" style={{ color }}>
              {e.pnl_usd >= 0 ? '+' : ''}${e.pnl_usd.toFixed(2)}
            </span>
          )}
        </div>
        <div className="text-xs leading-snug mt-0.5" style={{ color: '#d4d4d4' }}>
          {e.message}
        </div>
      </div>
    </div>
  )
}

export default function ActivityRail({ entries }) {
  return (
    <div className="rounded-xl gradient-card border overflow-hidden" style={{ borderColor: '#2a2a3a' }}>
      <div className="flex items-center gap-2 px-3 py-2.5" style={{ borderBottom: '1px solid #2a2a3a' }}>
        <div className="flex items-center gap-1.5">
          <div
            className="w-1.5 h-1.5 rounded-full animate-pulse-glow"
            style={{ background: '#26de81' }}
          />
          <span className="text-[9px] font-bold tracking-[0.16em]" style={{ color: '#26de81' }}>
            LIVE
          </span>
        </div>
        <span className="text-[10px] font-bold tracking-[0.14em] uppercase" style={{ color: '#94a3b8' }}>
          Bot Activity
        </span>
      </div>

      <div style={{ maxHeight: 600, overflowY: 'auto' }}>
        {entries.length === 0 ? (
          <div className="px-4 py-6 text-xs text-center" style={{ color: '#64748b' }}>
            Waiting for first entry…
          </div>
        ) : (
          entries.map((e, i) => <Entry key={`${e.id || i}-${e.ts}`} e={e} />)
        )}
      </div>
    </div>
  )
}
