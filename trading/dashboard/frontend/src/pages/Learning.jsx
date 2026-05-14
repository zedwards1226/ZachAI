import { useApi, api, fmt } from '../api.js'
import { Brain, TrendingUp, TrendingDown, FileText, Check } from 'lucide-react'

function StatusBadge({ status }) {
  const tone =
    status === 'applied' ? 'bg-profit/20 text-profit' :
    status === 'pending' ? 'bg-warn/15 text-warn' :
    status === 'rejected' ? 'bg-loss/20 text-loss' :
                            'bg-bg-panel text-text-secondary'
  return <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${tone}`}>{status || '—'}</span>
}

function EntryRow({ e }) {
  const isProposal = e.entry_type === 'proposal'
  const isDigest = e.entry_type === 'digest'
  const Icon = isDigest ? FileText : (e.proposed_value > e.current_value ? TrendingUp : TrendingDown)
  const iconTone =
    isDigest ? 'text-accent' :
    e.proposed_value > e.current_value ? 'text-profit' :
                                          'text-loss'

  return (
    <div className="border-b border-border-light last:border-b-0 px-3 py-3 flex gap-3">
      <Icon size={18} className={`mt-0.5 flex-shrink-0 ${iconTone}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap mb-1">
          <span className="text-xs font-mono text-text-muted">{e.date}</span>
          <span className="text-xs uppercase text-text-secondary">{e.entry_type}</span>
          {e.knob && (
            <span className="text-sm font-semibold text-text-primary font-mono">{e.knob}</span>
          )}
          {isProposal && (
            <span className="text-xs font-mono">
              <span className="text-loss">{e.current_value}</span>
              <span className="text-text-muted mx-1">→</span>
              <span className="text-profit">{e.proposed_value}</span>
            </span>
          )}
          <span className="flex-1" />
          <StatusBadge status={e.status} />
          {e.applied_at && <Check size={12} className="text-profit" />}
        </div>
        {e.reasoning && (
          <div className="text-sm text-text-secondary whitespace-pre-line">{e.reasoning}</div>
        )}
        {e.sample_size && e.confidence !== null && (
          <div className="text-xs text-text-muted mt-1">
            sample n={e.sample_size}{e.confidence !== null && ` · confidence ${(e.confidence * 100).toFixed(0)}%`}
            {e.source && ` · ${e.source}`}
          </div>
        )}
      </div>
    </div>
  )
}

export default function Learning() {
  const { data, error } = useApi(() => api.learning(30), [])

  if (error) return <div className="text-loss text-sm mt-4">Error: {error}</div>
  if (!data) return <div className="text-text-muted text-sm mt-4">Loading…</div>

  const entries = data.entries || []
  const proposals = entries.filter(e => e.entry_type === 'proposal')
  const digests = entries.filter(e => e.entry_type === 'digest')
  const applied = proposals.filter(e => e.status === 'applied').length

  return (
    <div className="mt-4 space-y-4">
      <section className="grid grid-cols-3 gap-3">
        <div className="gradient-card border border-border rounded-lg p-3">
          <div className="text-xs uppercase text-text-muted">Proposals (30d)</div>
          <div className="text-xl font-bold mt-1 text-text-primary">{proposals.length}</div>
        </div>
        <div className="gradient-card border border-border rounded-lg p-3">
          <div className="text-xs uppercase text-text-muted">Auto-applied</div>
          <div className="text-xl font-bold mt-1 text-profit">{applied}</div>
        </div>
        <div className="gradient-card border border-border rounded-lg p-3">
          <div className="text-xs uppercase text-text-muted">Digests</div>
          <div className="text-xl font-bold mt-1 text-accent">{digests.length}</div>
        </div>
      </section>

      <section className="gradient-card border border-border rounded-lg overflow-hidden">
        <div className="px-3 py-2 border-b border-border-light flex items-center gap-2">
          <Brain size={16} className="text-accent" />
          <h2 className="text-sm font-semibold">Learning Agent — last 30 days</h2>
        </div>
        {entries.length === 0 ? (
          <div className="p-4 text-text-muted text-sm">No learning activity in last 30 days.</div>
        ) : (
          entries.map((e) => <EntryRow key={e.id} e={e} />)
        )}
      </section>
    </div>
  )
}
